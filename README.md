# Spot Price Monitor

## Table of contents
* [Introduction](#introduction)
* [Usage](#usage)
* [Related](#related)
* [Communication](#communication)
* [Contributing](#contributing)
* [License](#license)

## Introduction

Reads instance types and availability zones from Kubernetes labels to expose as
Prometheus metrics, the current spot prices of spot instances within a cluster.

## Usage

### Deploy to Kubernetes
A docker image is available at `quay.io/pusher/k8s-spot-price-monitor`.
These images are currently built on pushes to master. Releases will be tagged.

Sample Kubernetes manifests are available in the [deploy](deploy/) folder.

To deploy in clusters using RBAC, please apply all of the manifests (Deployment, ClusterRole, ClusterRoleBinding and ServiceAccount) in the [deploy](deploy/) folder but uncomment the `serviceAccountName` in the [Deployment](deploy/deployment.yaml).

#### Requirements

For the K8s Spot Price Monitor to filter spot instances as expected;
you will need an identifying label on your spot instances.

We add a label `node-role.kubernetes.io/spot-worker` to our spot instances and
hence this is the default for the `spot-label` flag.

To achieve this, add the following flag to your Kubelet:
```
--node-labels="node-role.kubernetes.io/spot-worker=true"
```

Since the script uses a built-in, well-known label for looking up instance types
(`beta.kubernetes.io/instance-type`), this project supports K8s v1.7+.

##### IAM
To fetch Spot Prices, the Spot Price Monitor will need the following IAM role policy.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Stmt1519813867626",
      "Action": [
        "ec2:DescribeSpotPriceHistory"
      ],
      "Effect": "Allow",
      "Resource": "*"
    }
  ]
}
```

### Product descriptions
For EC2 Classic accounts the default `Linux/UNIX` product description will only
work for non-VPC instance types, and for VPC accounts it will only work for VPC
instance types.

It's possible to override the product descriptions with the `-p`/`--products`
flag to work around this:

```
spot_price_monitor.py --products "Linux/UNIX" "Linux/UNIX (Amazon VPC)"
```

### Flags
```
usage: spot_price_monitor.py [-h] [--running-in-cluster RUNNING_IN_CLUSTER]
                             [-l SPOT_LABEL] [-i SCRAPE_INTERVAL]
                             [-m METRICS_PORT] [-r REGION]
                             [-p PRODUCTS [PRODUCTS ...]]

Monitors kubernetes for spot instances and exposes the current spot prices as
prometheus metrics

optional arguments:
  -h, --help            show this help message and exit
  --running-in-cluster RUNNING_IN_CLUSTER
                        Will load kubernetes config from the pod environment
                        if running within the cluster, else loads a kubeconfig
                        from the running environemnt (Default: False)
  -l LABEL, --spot-label LABEL
                        Specifies the label applied to all spot instances in
                        the cluster to identify these from other types of
                        instances (Default: node-role.kubernetes.io/spot-
                        worker)
  -i SCRAPE_INTERVAL, --scrape-interval SCRAPE_INTERVAL
                        How often (in seconds) should the prices be scraped
                        from AWS (Default: 60)
  -m METRICS_PORT, --metrics-port METRICS_PORT
                        Port to expose prometheus metrics on (Default: 8000)
  -r REGION, --region REGION
                        The region that the cluster is running in (Default:
                        us-east-1)
  -p PRODUCTS [PRODUCTS ...], --products PRODUCTS [PRODUCTS ...]
                        List of product (descriptions) to use for filtering
                        (Default: Linux/UNIX)
```

## Related
- [K8s Spot Rescheduler](https://github.com/pusher/k8s-spot-rescheduler): Move nodes from on-demand instances to spot instances when space is available.
- [K8s Spot Termination Handler](https://github.com/pusher/k8s-spot-termination-handler): Gracefully drain spot instances when they are issued with a termination notice.

## Communication

* Found a bug? Please open an issue.
* Have a feature request. Please open an issue.
* If you want to contribute, please submit a pull request

## Contributing
Please see our [Contributing](CONTRIBUTING.md) guidelines.

## License
This project is licensed under Apache 2.0 and a copy of the license is available [here](LICENSE).
