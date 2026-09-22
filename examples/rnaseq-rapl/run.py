#!/usr/bin/env python3
"""Prepare a fresh run, submit it, and export only its retained evidence."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
NODES = ("hu-worker-c34", "hu-worker-c39", "hu-worker-c41")
LABEL = "fonda.hu-berlin.de/run-id"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n")


def kubectl(namespace, *args):
    return subprocess.check_output(["kubectl", "--request-timeout=60s", "-n", namespace, *args])


def prepare(root, rid, namespace, node):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,40}[a-z0-9]", rid):
        raise ValueError("Use a fresh lowercase run ID, 2–42 letters, digits or hyphens")
    if not re.fullmatch(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?", namespace):
        raise ValueError("Invalid namespace")
    if node not in NODES:
        raise ValueError("Node is outside the allowed prototyping nodes")
    root.mkdir(parents=True, exist_ok=False)
    replacements = {"__RUN_ID__": rid, "__RUN_NAME__": rid.replace("-", "_"),
                    "__NAMESPACE__": namespace, "__NODE__": node}

    def render(text):
        for key, value in replacements.items():
            text = text.replace(key, value)
        return text

    runtime = {p.name: render(p.read_text()) for p in sorted((HERE / "runtime").iterdir()) if p.is_file()}
    for name, text in runtime.items():
        save(root / "runtime" / name, text)
    for path in sorted((HERE / "templates").glob("*.json")):
        obj = json.loads(render(path.read_text()))
        if path.name == "base.resources.json":
            for item in obj["items"]:
                if item["kind"] == "ConfigMap":
                    item["data"] = runtime
        save(root / "manifests" / path.name, obj)
    save(root / "run-plan.json", dict(run_id=rid, namespace=namespace, node=node,
         job=rid, pvc=rid + "-work", reader_job=rid + "-evidence"))
    print(f"Prepared {root}; no cluster resources created yet.")


def start(root, plan):
    ns, node = plan["namespace"], plan["node"]
    info = json.loads(kubectl(ns, "get", "node", node, "-o", "json"))
    if info["metadata"]["labels"].get("usedby") != "prototyping" or info["spec"].get("unschedulable"):
        raise ValueError("Selected node is not available for prototyping")
    if not any(c["type"] == "Ready" and c["status"] == "True" for c in info["status"]["conditions"]):
        raise ValueError("Selected node is not Ready")
    # create (never apply) refuses collisions and never updates another run.
    for name in ("base.resources.json", "workflow.job.json"):
        print(kubectl(ns, "create", "-f", str(root / "manifests" / name)).decode(), end="")
    print("Submitted. Retain the PVC and pods until evidence export is verified.")


EXPORT = """import tarfile, sys, pathlib
with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz') as archive:
    for name in ['run', 'rapl', 'provenance', 'results', 'source-backups']:
        archive.add('/workspace/' + name, arcname=name)
    for path in sorted(pathlib.Path('/workspace/work').glob('*/*/.*')):
        if path.is_file() and not path.is_symlink() and (path.name.startswith('.command') or path.name == '.exitcode'):
            archive.add(path, arcname='task-records/' + str(path.relative_to('/workspace/work')), recursive=False)
"""


def capture(root, plan, reader):
    ns, rid = plan["namespace"], plan["run_id"]
    pod = json.loads(kubectl(ns, "get", "pod", reader, "-o", "json"))
    if (pod["metadata"].get("labels", {}).get("job-name") != plan["reader_job"]
            or pod["spec"]["nodeName"] != plan["node"]):
        raise ValueError("Reader does not belong to this run on the selected node")
    if not any(v.get("persistentVolumeClaim", {}).get("claimName") == plan["pvc"]
               and v["persistentVolumeClaim"].get("readOnly") for v in pod["spec"]["volumes"]):
        raise ValueError("Reader must mount this run's PVC read-only")
    evidence = root / "evidence"
    evidence.mkdir(exist_ok=False)
    cluster = evidence / "cluster"
    cluster.mkdir()
    for resource in ("jobs", "pods", "pvc", "serviceaccounts", "roles", "rolebindings", "configmaps"):
        save(cluster / (resource + ".json"), kubectl(ns, "get", resource, "-l", LABEL + "=" + rid, "-o", "json").decode())
    pods = json.loads((cluster / "pods.json").read_text())["items"]
    for item in pods:
        if item["metadata"]["name"] == reader:
            continue
        for container in item["spec"].get("initContainers", []) + item["spec"]["containers"]:
            name = item["metadata"]["name"]
            save(cluster / (name + "--" + container["name"] + ".log"),
                 kubectl(ns, "logs", name, "-c", container["name"]).decode())
    archive = root / (rid + "-results.tar.gz")
    with archive.open("xb") as stream:
        subprocess.run(["kubectl", "-n", ns, "exec", reader, "-c", "reader", "--", "python3", "-c", EXPORT],
                       stdout=stream, check=True)
    dest = evidence / "completed-run"
    dest.mkdir()
    with tarfile.open(archive) as stream:
        stream.extractall(dest, filter="data")
    print(f"Exported {dest}; validate and build metadata next.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("directory", type=Path)
    prep.add_argument("--run-id", required=True)
    prep.add_argument("--namespace", default="yagmur")
    prep.add_argument("--node", choices=NODES, default=NODES[0])
    for action in ("start", "capture"):
        cmd = sub.add_parser(action)
        cmd.add_argument("directory", type=Path)
        if action == "capture":
            cmd.add_argument("--reader-pod", required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.directory, args.run_id, args.namespace, args.node)
    else:
        plan = json.loads((args.directory / "run-plan.json").read_text())
        if plan["node"] not in NODES:
            raise ValueError("Node is outside the allowed nodes")
        if args.action == "start":
            start(args.directory, plan)
        else:
            capture(args.directory, plan, args.reader_pod)


if __name__ == "__main__":
    main()
