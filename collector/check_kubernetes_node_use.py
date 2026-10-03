#!/usr/bin/env python3
"""Find out afterwards whether Kubernetes runs had their nodes to themselves.

For runs that are already in VIVO without "node use" (rm:nodeUse). Prometheus
must still have the pod records of the time of the run; runs older than its
retention time are reported as "no data" and left out.

Two kinds of input:

  1. Runs listed in a file exported from VIVO (Site Admin > SPARQL Query, the
     query is in docs/NODE_USE.md, result format CSV or TSV) with the columns
     run, start, end, hosts:

       check_kubernetes_node_use.py --runs runs.csv --namespace NAMESPACE

     Every pod of NAMESPACE counts as part of the run.

  2. The *.metrics.json files the collector wrote next to the run's Turtle
     file; they name the run's pods exactly:

       check_kubernetes_node_use.py RUN.metrics.json [...]

The result is printed and written as Turtle (default node-use.ttl), one
rm:nodeUse statement per run. Upload that file in VIVO with Site Admin >
Add/Remove RDF data > "add mixed RDF", format Turtle. Nothing is sent to VIVO
by this script.
"""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from . import collect_nextflow_run_metadata as core
except ImportError:  # started as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import collect_nextflow_run_metadata as core  # type: ignore[no-redef]

BERLIN = core.BERLIN_TZ


def parse_time(text: str) -> datetime:
    """Time of a run as stored in VIVO; without a UTC offset it is Berlin time."""
    value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=BERLIN)


def runs_from_table(path: Path, namespace: str) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    delimiter = "\t" if "\t" in text.splitlines()[0] else ","
    runs = []
    for row in csv.DictReader(text.splitlines(), delimiter=delimiter):
        # values may be plain or written as in SPARQL results: <uri>, "text"^^<datatype>
        clean = {(key or "").strip().lstrip("?"): (value or "").split("^^")[0].strip().strip('"').strip("<>")
                 for key, value in row.items()}
        if not clean.get("run"):
            continue
        runs.append({
            "run": clean["run"], "start": parse_time(clean["start"]), "end": parse_time(clean["end"]),
            "nodes": clean.get("hosts", "").split(), "pods": None, "namespace": namespace,
        })
    return runs


def run_from_metrics(path: Path, driver_pod: str) -> Dict[str, Any]:
    audit = json.loads(path.read_text(encoding="utf-8"))
    pods = audit.get("pod_metrics", {})
    return {
        "run": audit["run_uri"],
        "start": parse_time(audit["resource_accounting_start_utc"]),
        "end": parse_time(audit["resource_accounting_end_utc"]),
        "nodes": core.unique(metrics.get("node_name") for metrics in pods.values()),
        "pods": [*pods.keys(), driver_pod], "namespace": None,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("metrics", nargs="*", type=Path, help="*.metrics.json files written by the collector")
    parser.add_argument("--runs", type=Path, help="CSV or TSV exported from VIVO: run, start, end, hosts")
    parser.add_argument("--namespace", help="Kubernetes namespace of the runs listed in --runs")
    parser.add_argument("--prom-url", default=core.PROM_URL_DEFAULT)
    parser.add_argument("--driver-pod", default=core.DEFAULT_DRIVER_POD)
    parser.add_argument("--max-other-cpus", type=float, default=core.NODE_USE_MAX_OTHER_CPUS_DEFAULT)
    parser.add_argument("--ontology-uri", default="http://example.org/ontology/run-metadata#")
    parser.add_argument("--output", type=Path, default=Path("node-use.ttl"))
    args = parser.parse_args(argv)
    if not args.metrics and not args.runs:
        parser.error("give --runs FILE --namespace NAMESPACE or one or more *.metrics.json files")
    if args.runs and not args.namespace:
        parser.error("--runs needs --namespace")

    runs = [run_from_metrics(path, args.driver_pod) for path in args.metrics]
    if args.runs:
        runs += runs_from_table(args.runs, args.namespace)
    core.ensure_prometheus_reachable(args.prom_url)

    lines = [f"@prefix rm: <{args.ontology_uri}> .", ""]
    found = 0
    for run in runs:
        name = run["run"].rstrip("/").rsplit("/", 1)[-1]
        result = None
        if run["nodes"]:
            result = core.kubernetes_node_use(
                args.prom_url, run["nodes"], run["pods"], run["start"], run["end"],
                args.max_other_cpus, run["namespace"])
        if result is None:
            print(f"no data        {name}  (no Kubernetes pod records for its nodes and time)")
            continue
        found += 1
        others = ", ".join(f"{ns} {seconds / result['window_seconds']:.2f}"
                           for ns, seconds in result["other_cpu_seconds_by_namespace"].items() if seconds > 0)
        print(f"{'exclusive' if result['exclusive'] else 'non-exclusive':13}  {name}\n"
              f"               run {result['run_cpus']:.2f} CPUs, other workloads {result['other_cpus']:.2f} CPUs"
              f"{' (' + others + ')' if others else ''}, node daemons {result['node_daemon_cpus']:.2f} CPUs, "
              f"{len(result['nodes'])} node(s)")
        lines.append(f"{core.ttl_uri(run['run'])} rm:nodeUse {core.ttl_literal(result['text'])} .")
    if found:
        args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n{found} of {len(runs)} run(s) written to {args.output}")
    else:
        print(f"\nNo run could be checked; {args.output} was not written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
