# Spot Price Monitor

Reads instance types and availability zones from Kubernetes labels to provide metrics for the current spot prices of spot instances within a cluster.

## Usage
```
usage: docker-entrypoint.py [-h] [--running-in-cluster RUNNING_IN_CLUSTER]
                            [-l LABEL] [-i SCRAPE_INTERVAL] [-p PROM_PORT]
                            [-r REGION]

Monitors kubernetes for spot instances and exposes the current spot prices as
prometheus metrics

optional arguments:
  -h, --help            show this help message and exit
  --running-in-cluster RUNNING_IN_CLUSTER
                        Will load kubernetes config from the pod environment
                        if running within the cluster, else loads a kubeconfig
                        from the running environemnt (Default: False)
  -l LABEL, --label LABEL
                        Specifies the label applied to all spot instances in
                        the cluster to identify these from other types of
                        instances (Default: node-role.kubernetes.io/spot-
                        worker)
  -i SCRAPE_INTERVAL, --scrape-interval SCRAPE_INTERVAL
                        How often (in seconds) should the prices be scraped
                        from AWS (Default: 60)
  -p PROM_PORT, --prom-port PROM_PORT
                        Port to expose prometheus metrics on (Default: 8000)
  -r REGION, --region REGION
                        The region that the cluster is running in (Default:
                        us-east-1)
```
