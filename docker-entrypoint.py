import argparse
from kubernetes import client, config
import boto3
from botocore.exceptions import ClientError
from prometheus_client import start_http_server, Gauge, Counter
from datetime import datetime
from time import sleep


def get_labels_from_k8s(client, args):
    ''' Returns a list of unique instance types and unique availability zones
    used in the cluster'''
    nodes = client.list_node(label_selector=args.label,
                             watch=False
                             )
    instance_types = set([])
    availability_zones = set([])
    for node in nodes.items:
        instance_types.add(
            node.metadata.labels['beta.kubernetes.io/instance-type']
            )
        availability_zones.add(
            node.metadata.labels['failure-domain.beta.kubernetes.io/zone']
            )
    return list(instance_types), list(availability_zones)


def get_spot_prices(client, instance_types, availability_zones):
    ''' Returns a list of spot prices by instance type and availability zone'''
    response = client.describe_spot_price_history(
        Filters=[
            {
                'Name': 'availability-zone',
                'Values': availability_zones
            },
        ],
        InstanceTypes=instance_types,
        StartTime=datetime.now(),
        ProductDescriptions=['Linux/UNIX']
    )
    return response['SpotPriceHistory']


def get_args():
    ''' Processes command line arguments'''
    parser = argparse.ArgumentParser(
        description='''Monitors kubernetes for spot instances and exposes the
        current spot prices as prometheus metrics'''
    )

    parser.add_argument('--running-in-cluster', type=bool, default=False,
                        help='''Will load kubernetes config from the pod
                        environment if running within the cluster, else loads a
                        kubeconfig from the running environemnt (Default:
                        False)''')
    parser.add_argument('-l', '--label', type=str,
                        default='node-role.kubernetes.io/spot-worker',
                        help='''Specifies the label applied to all spot
                        instances in the cluster to identify these from other
                        types of instances (Default:
                        node-role.kubernetes.io/spot-worker)''')
    parser.add_argument('-i', '--scrape-interval', type=int, default=60,
                        help='''How often (in seconds) should the prices be
                        scraped from AWS (Default: 60)''')
    parser.add_argument('-p', '--prom-port', type=int, default=8000,
                        help='''Port to expose prometheus metrics on (Default:
                        8000)''')
    parser.add_argument('-r', '--region', type=str, default='us-east-1',
                        help='''The region that the cluster is running
                        in (Default: us-east-1)''')

    return parser.parse_args()


def update_spot_price_metrics(metric, prices):
    ''' Updates prometheus gauge based on input list of prices'''
    for price in prices:
        metric.labels(
            instance_type=price['InstanceType'],
            availability_zone=price['AvailabilityZone']
            ).set(price['SpotPrice'])


if __name__ == '__main__':
    args = get_args()

    if args.running_in_cluster:
        config.incluster_config.load_incluster_config()
    else:
        config.load_kube_config()

    v1 = client.CoreV1Api()
    ec2 = boto3.client('ec2', args.region)
    start_http_server(8000)

    s = Gauge('aws_spot_price_dollars_per_hour',
              'Reports the AWS spot price of node types used in the cluster',
              ['instance_type', 'availability_zone']
              )
    error = Counter('aws_spot_price_request_errors',
                    'Reports errors while calling the AWS api.',
                    ['code']
                    )

    backoff_multiplier = 1
    while(True):
        types, zones = get_labels_from_k8s(v1, args)
        try:
            spot_prices = get_spot_prices(ec2, types, zones)
            backoff_multiplier = 1
        except ClientError as e:
            error.label(code=e.response['Error']['Code']).inc()
            if e.response['Error']['Code'] == 'RequestLimitExceeded':
                backoff_multiplier *= 2
        update_spot_price_metrics(s, spot_prices)
        sleep(args.scrape_interval * backoff_multiplier)
