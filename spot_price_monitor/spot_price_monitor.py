#!/usr/bin/python
'''Exposes Prometheus metrics for current spot prices.'''

import re
import time
import json
import argparse
import logging
from datetime import datetime

import boto3
import requests
from botocore.exceptions import ClientError
from kubernetes import client, config
from prometheus_client import start_http_server, Gauge, Counter

logger = logging.getLogger(__name__) # noqa pylint: disable=C0103

EC2_PRICING_API = 'https://raw.githubusercontent.com/powdahound/ec2instances.info/master/www/instances.json'
ALLOWED_PRODUCTS = [
    'Linux/UNIX',
    'SUSE Linux',
    'Windows',
    'Linux/UNIX (Amazon VPC)',
    'SUSE Linux (Amazon VPC)',
    'Windows (Amazon VPC)'
    ]


def get_zones_from_k8s(k8s_client):
    '''Returns a list of unique availability zones used in the cluster'''

    nodes = k8s_client.list_node(watch=False)
    availability_zones = set([])
    for node in nodes.items:
        availability_zones.add(
            node.metadata.labels['failure-domain.beta.kubernetes.io/zone']
            )
    return list(availability_zones)


def matches_label(label, node_labels):
    '''
    Returns true if the label provided is the node metadata labels. Supports
    both new and node-role label schema. Old depreciated in v1.15, removed in
    1.16. Support for both is intended to ease the transition.
    '''

    # determine if the label is new or old schema
    split = label.split("=", 2)

    if len(split) == 1:  # no '='
        return label in node_labels
    if len(split) == 2:  # one '='
        label_key = split[0]
        label_val = split[1]

        val = node_labels[label_key]
        return val == label_val

    return False


def get_instance_types_from_k8s(k8s_client, label):
    '''Returns a list of unique instance types used in the cluster'''

    nodes = k8s_client.list_node(watch=False)
    instance_types = set([])
    for node in nodes.items:
        if matches_label(label, node.metadata.labels):
            instance_types.add(
                node.metadata.labels['beta.kubernetes.io/instance-type']
                )
    return list(instance_types)


def get_spot_prices(ec2_client, instance_types, availability_zones, products):
    '''Returns a list of spot prices by instance type and availability zone'''

    response = ec2_client.describe_spot_price_history(
        Filters=[
            {
                'Name': 'availability-zone',
                'Values': availability_zones
            },
        ],
        InstanceTypes=instance_types,
        StartTime=datetime.now(),
        ProductDescriptions=products
    )
    return response['SpotPriceHistory']


def get_ondemand_price_metrics(num_of_retries=5, time_interval=2, timeout=5):
    '''Returns a dict of on-demand spot prices'''

    response = get_ondemand_prices_from_api(num_of_retries, time_interval, timeout)
    parsed_json = json.loads(response.text)
    on_demand_prices = {}
    for instance_type in parsed_json:
        for region in instance_type['pricing']:
            if region not in on_demand_prices:
                on_demand_prices[region] = {}
            if 'linux' in instance_type['pricing'][region] and 'ondemand' in instance_type['pricing'][region]['linux']:
                price = instance_type['pricing'][region]['linux']['ondemand']
                on_demand_prices[region][instance_type['instance_type']] = price

    logger.debug("Ondemand prices:\n %s", on_demand_prices)

    return on_demand_prices


def get_ondemand_prices_from_api(num_of_retries, time_interval, timeout):
    '''Fetches a list of ondemand prices from the EC2_PRICING_API'''
    for _ in range(num_of_retries):
        try:
            logger.debug("Downloading daily ondemand prices")
            response = requests.get(EC2_PRICING_API, timeout=timeout)

            if response.status_code != 200:
                logger.error("Failed to download ondemand prices. Status code for page %d", response.status_code)
                raise Exception("Failed to download ondemand prices")

            return response
        except requests.exceptions.RequestException as exception:
            logger.error("Failed to download ondemand prices. Exception: %s. Retrying...", str(exception))
            time.sleep(time_interval)

    # Should only get here once num_of_retries is exceeded
    logger.error("Maximum retries hit")
    raise Exception("Failed to get ondemand prices after %d tries.", )


def get_args():
    '''Processes command line arguments'''
    parser = argparse.ArgumentParser(
        description='''Monitors kubernetes for spot instances and exposes the
        current spot prices as prometheus metrics'''
    )

    parser.add_argument('--running-in-cluster', type=bool, default=False,
                        help='''Will load kubernetes config from the pod
                        environment if running within the cluster, else loads a
                        kubeconfig from the running environemnt (Default:
                        False)''')
    parser.add_argument('-l', '--spot-label', type=str, required=False,
                        help='''Specifies the label that identifies nodes as
                        spot instances.''',
                        default='kubernetes.io/role=spot-worker')
    parser.add_argument('-i', '--scrape-interval', type=int, default=60,
                        help='''How often (in seconds) should the prices be
                        scraped from AWS (Default: 60)''')
    parser.add_argument('-m', '--metrics-port', type=int, default=8000,
                        help='''Port to expose prometheus metrics on (Default:
                        8000)''')
    parser.add_argument('-r', '--region', type=str, default='us-east-1',
                        help='''The region that the cluster is running
                        in (Default: us-east-1)''')
    parser.add_argument('--on-demand', action="store_true", default=False,
                        help='''Will enable ondemand prices''')
    parser.add_argument('-v', '--verbose', action="store_true", default=False,
                        help='''Enable verbose output''')
    parser.add_argument('-p', '--products', type=str, nargs='+', default=['Linux/UNIX'],
                        help='''List of product (descriptions) to use for filtering, separated
                        by spaces, e.g. `-p "Linux/UNIX" "Linux/UNIX (Amazon VPC)"`
                        (Default: Linux/UNIX)''')

    return parser.parse_args()


def update_spot_price_metrics(metric, prices):
    '''Updates prometheus gauge based on input list of prices'''

    for price in prices:
        metric.labels(
            instance_type=price['InstanceType'],
            availability_zone=price['AvailabilityZone']
            ).set(price['SpotPrice'])


def update_ondemand_price_metrics(metric, prices, types, zones):
    '''Updates a Prometheus gauge with on demand prices'''

    for zone in zones:
        region = re.sub(r"[a-z]$", "", zone)
        for instance_type in types:
            metric.labels(
                instance_type=instance_type,
                availability_zone=zone
            ).set(prices[region][instance_type])


def update_ondemand_prices(last_ondemand_update, on_demand_spot_gauge, spot_prices, spot_error):
    '''Refresh ondemand prices once a day'''
    if last_ondemand_update + 86400 < time.time():
        try:
            last_ondemand_update = time.time()
            price_zones = {}
            price_instance_types = {}
            for price in spot_prices:
                price_zones[price['AvailabilityZone']] = 1
                price_instance_types[price['InstanceType']] = 1
            ondemand_prices = get_ondemand_price_metrics()
            update_ondemand_price_metrics(
                on_demand_spot_gauge,
                ondemand_prices,
                price_instance_types.keys(), price_zones.keys())
            return last_ondemand_update
        except Exception as exception:  # noqa pylint: disable=broad-except
            logger.error("Ondemand prices load failed. I won't retry for another day. Error: %s", str(exception))
            spot_error.labels(code='ondemand_failure').inc()  # noqa pylint: disable=E1101
    else:
        return last_ondemand_update


def load_config(running_in_cluster):
    '''Load the correct Kubernetes config based on in-cluster or not'''
    if running_in_cluster:
        config.incluster_config.load_incluster_config()
    else:
        config.load_kube_config()


def check_allowed_products(products):
    '''Raises and error if an invalid product is requested'''
    for product in products:
        if product not in ALLOWED_PRODUCTS:
            raise ValueError('invalid product {}, expected one of {}'.format(product, ALLOWED_PRODUCTS))


def main():
    '''Main'''
    args = get_args()

    if len(args.spot_label.split("=", 2)) > 2:
        raise ValueError("""the spot node label is not correctly formatted:
         expected '<label_name>' or '<label_name>=<label_value>', but got {}""".format(args.spot_label))

    logging_level = logging.DEBUG if args.verbose else logging.WARN
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging_level)

    check_allowed_products(args.products)
    load_config(args.running_in_cluster)

    k8s_client = client.CoreV1Api()
    ec2 = boto3.client('ec2', args.region)
    start_http_server(args.metrics_port)

    on_demand_spot_gauge = None
    spot_gauge = Gauge(
        'aws_spot_price_dollars_per_hour',
        'Reports the AWS spot price of node types used in the cluster',
        ['instance_type', 'availability_zone']
    )
    spot_error = Counter(
        'aws_spot_price_request_errors',
        'Reports errors while calling the AWS api.',
        ['code']
    )
    if args.on_demand:
        on_demand_spot_gauge = Gauge(
            'aws_on_demand_dollars_per_hour',
            'Reports the AWS ondemand of node types used in the cluster',
            ['instance_type', 'availability_zone']
        )

    last_ondemand_update = 0
    backoff_multiplier = 1

    spot_prices = []
    while True:
        zones = get_zones_from_k8s(k8s_client)
        try:
            types = get_instance_types_from_k8s(k8s_client, args.spot_label)
            spot_prices = get_spot_prices(ec2, types, zones, args.products)
            backoff_multiplier = 1
        except ClientError as exception:
            spot_error.labels(exception.response['Error']['Code']).inc() # noqa pylint: disable=E1101
            if exception.response['Error']['Code'] == 'RequestLimitExceeded':
                logger.error("RequestLimitExceeded. Doubling backoff multiplier. Error: %s", str(exception))
                backoff_multiplier *= 2
        update_spot_price_metrics(spot_gauge, spot_prices)

        if args.on_demand:
            last_ondemand_update = update_ondemand_prices(
                last_ondemand_update,
                on_demand_spot_gauge,
                spot_prices,
                spot_error
            )

        time.sleep(args.scrape_interval * backoff_multiplier)


if __name__ == '__main__':
    main()
