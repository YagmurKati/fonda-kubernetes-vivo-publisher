# Node use of a run: exclusive or non-exclusive

A run's page in VIVO has the field **node use** (`rm:nodeUse`). It says whether
the run had its compute nodes to itself, which matters when runs are compared:
energy, CPU time and duration of a run on a busy node are not comparable with
those of a run on an idle one. The workflow page uses it for the "Node use"
tick boxes above the plots.

| Value starts with | Meaning |
|---|---|
| `exclusive` | Nothing else used the run's nodes while it ran. |
| `non-exclusive` | Other workloads used the run's nodes at the same time. |

## How it is decided on Kubernetes

The collector asks Prometheus for every pod that was on the run's nodes during
the run (`kube_pod_info`) and for the CPU time of each of them
(`container_cpu_usage_seconds_total`). Pods are sorted into three groups:

- **the run**: its task pods and the engine's driver pod;
- **node daemons**: pods that run on every node or belong to the node itself
  (created by a DaemonSet, or static pods), for example the network plugin and
  the monitoring agents. They are there for every run and are not counted;
- **other workloads**: everything else.

The CPU time of the other workloads divided by the length of the run is the
average number of CPUs they kept busy. The run is `exclusive` when that is at
most 0.5 CPUs (`--node-use-max-other-cpus`), otherwise `non-exclusive`. The
measured number is part of the value:

    exclusive (other workloads used 0.03 CPUs on average on the run's 3 nodes)
    non-exclusive (other workloads used 12.40 CPUs on average on the run's 3 nodes)

This is a measurement of what happened, not of how the cluster is set up. A
run on a node reserved for one person is `exclusive` because nobody else could
use the node; a run on shared nodes is `exclusive` too when the nodes happened
to be idle otherwise. Details (CPUs of the run, of the daemons and of the other
workloads per namespace) are in the run's `*.metrics.json` under `node_use`.

If Prometheus has no pod records for the run's nodes, the field is left out.

## The field in VIVO

Create it once (Site Admin > Data property hierarchy > Add new data property):

| | |
|---|---|
| Public name | node use |
| Local name | `nodeUse` (namespace `http://example.org/ontology/run-metadata#`) |
| Domain class | Workflow Run |
| Range datatype | string |

## Runs that are already in VIVO

`collector/check_kubernetes_node_use.py` works out the node use of published
runs, as long as Prometheus still has the data of that time (its retention
time, often 15 days).

1. In VIVO, Site Admin > SPARQL Query, run this query and save the result as
   CSV, for example `runs.csv`:

   ```sparql
   PREFIX rm: <http://example.org/ontology/run-metadata#>
   SELECT ?run ?start ?end (GROUP_CONCAT(DISTINCT STR(?host); separator=" ") AS ?hosts)
   WHERE {
     ?run rm:startTime ?start ; rm:endTime ?end ; rm:executionHost ?host .
     FILTER NOT EXISTS { ?run rm:nodeUse ?known }
   }
   GROUP BY ?run ?start ?end
   ```

2. Make Prometheus reachable on your computer. Service and namespace are the
   ones in `PROM_URL` of your `publisher.env`; for the FONDA cluster:

   ```bash
   kubectl -n monitoring port-forward svc/prometheus-kube-prometheus-prometheus 19090:9090
   ```

   In a second terminal, in the repository, run the check with the Kubernetes
   namespace the runs used (`NS` in `publisher.env`):

   ```bash
   python3 collector/check_kubernetes_node_use.py --runs runs.csv --namespace NAMESPACE
   ```

   Every pod of that namespace counts as part of the run. Runs on other
   systems and runs Prometheus has no data for are listed as "no data".

3. Upload the resulting `node-use.ttl` in VIVO: Site Admin > Add/Remove RDF
   data > "add mixed RDF", format Turtle. To undo, upload the same file with
   "remove mixed RDF".

When the `*.metrics.json` file of a run is at hand, give that instead of
`--runs`; it names the run's pods exactly.
