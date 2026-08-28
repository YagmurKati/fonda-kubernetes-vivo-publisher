#!/usr/bin/env python3
"""Collect VIVO-ready metadata for supported Snakemake Kubernetes runs."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Sequence, Tuple

try:
    from . import collect_nextflow_run_metadata as core
except ImportError:
    # The Kubernetes ConfigMap mounts the shared collector under this name.
    import collector_core as core  # type: ignore[no-redef]


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is empty")
    return value


def csv_env(name: str) -> List[str]:
    return [
        value.strip()
        for value in os.environ.get(name, "").split(",")
        if value.strip()
    ]


def snakemake_profile() -> str:
    profile = required_env("SNAKEMAKE_PROFILE").lower()
    if profile not in {"mg4", "popinsnake"}:
        raise RuntimeError(
            "SNAKEMAKE_PROFILE must be either 'mg4' or 'popinsnake'"
        )
    return profile


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def in_cluster_get(
    path: str, params: Dict[str, str] | None = None
) -> Dict[str, Any]:
    host = required_env("KUBERNETES_SERVICE_HOST")
    port = os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")
    token_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
    ca_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
    if not token_path.is_file() or not ca_path.is_file():
        raise RuntimeError(
            "In-cluster Kubernetes service-account credentials are unavailable"
        )
    url = f"https://{host}:{port}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": (
                "Bearer " + token_path.read_text(encoding="utf-8").strip()
            ),
        },
    )
    context = ssl.create_default_context(cafile=str(ca_path))
    with urllib.request.urlopen(
        request, timeout=30, context=context
    ) as response:
        return json.loads(response.read().decode("utf-8"))


def workflow_container_status(pod: Dict[str, Any]) -> Dict[str, Any]:
    statuses = pod.get("status", {}).get("containerStatuses", [])
    for status in statuses:
        if status.get("name") == "workflow":
            return status
    if len(statuses) == 1:
        return statuses[0]
    raise RuntimeError(
        f"Pod {pod.get('metadata', {}).get('name')} has no workflow status"
    )


def select_attempt_pods(
    namespace: str, run_id: str
) -> List[Dict[str, Any]]:
    selector = required_env("POD_LABEL_SELECTOR")
    payload = in_cluster_get(
        f"/api/v1/namespaces/{urllib.parse.quote(namespace, safe='')}/pods",
        {"labelSelector": selector},
    )
    pods = [
        item for item in payload.get("items", []) if isinstance(item, dict)
    ]
    tagged = [
        pod
        for pod in pods
        if pod.get("metadata", {})
        .get("labels", {})
        .get("fonda.hu-berlin.de/run-id")
        == run_id
    ]
    if tagged:
        selected = tagged
    else:
        fallback_run_id = required_env("FALLBACK_RUN_ID")
        if run_id != fallback_run_id:
            raise RuntimeError(
                f"No Pods carry run-id label {run_id!r}; the unlabelled "
                f"legacy fallback is restricted to {fallback_run_id!r}"
            )
        pattern = re.compile(required_env("JOB_NAME_REGEX"))
        selected = [
            pod
            for pod in pods
            if pattern.fullmatch(
                pod.get("metadata", {})
                .get("labels", {})
                .get("batch.kubernetes.io/job-name", "")
            )
        ]
    if not selected:
        raise RuntimeError(
            f"No Snakemake attempt Pods matched run {run_id!r}; "
            f"selector={selector!r}"
        )
    return selected


def build_tasks(
    pods: Sequence[Dict[str, Any]],
) -> Tuple[List[core.TaskRecord], List[Dict[str, Any]]]:
    records: List[Tuple[core.TaskRecord, Dict[str, Any]]] = []
    for pod in pods:
        metadata = pod.get("metadata", {})
        labels = metadata.get("labels", {})
        pod_name = str(metadata.get("name", ""))
        job_name = str(labels.get("batch.kubernetes.io/job-name", ""))
        status = workflow_container_status(pod)
        terminated = status.get("state", {}).get("terminated")
        if not isinstance(terminated, dict):
            raise RuntimeError(f"Pod {pod_name} has not reached a terminal state")
        started = parse_time(str(terminated["startedAt"]))
        finished = parse_time(str(terminated["finishedAt"]))
        exit_code = int(terminated.get("exitCode", 1))
        task = core.TaskRecord(
            task_id=job_name,
            hash_value=str(metadata.get("uid", "")),
            pod_name=pod_name,
            name=job_name,
            status="COMPLETED" if exit_code == 0 else "FAILED",
            exit_code=exit_code,
            submit=started,
            duration_seconds=max(0.0, (finished - started).total_seconds()),
            realtime_seconds=max(0.0, (finished - started).total_seconds()),
            end=finished,
        )
        records.append((task, pod))
    records.sort(key=lambda value: (value[0].submit, value[0].name))
    return [value[0] for value in records], [value[1] for value in records]


def read_tsv(path: Path) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("\t")
        if separator:
            result[key.strip()] = value.strip()
    return result


def read_mg4_result_metadata(run_root: Path) -> Dict[str, Any]:
    output_path = run_root / "source/MG-4-yagmur/mapped_reads/all_sorted.sam"
    completed_path = run_root / "RUN_COMPLETED"
    if (
        not completed_path.is_file()
        or not output_path.is_file()
        or output_path.stat().st_size == 0
    ):
        raise RuntimeError(
            "The MG-4 run has no completed, non-empty final SAM output"
        )
    provenance = read_tsv(run_root / "provenance.tsv")
    count = int(
        (run_root / "results/mapped-record-count.txt")
        .read_text(encoding="utf-8")
        .strip()
    )
    output_sha = ""
    sha_path = run_root / "results/output-sha256.txt"
    for line in sha_path.read_text(encoding="utf-8").splitlines():
        digest, separator, filename = line.partition("  ")
        if separator and filename.endswith("/mapped_reads/all_sorted.sam"):
            output_sha = digest.strip()
            break
    if not re.fullmatch(r"[0-9a-f]{64}", output_sha):
        raise RuntimeError("Could not identify the final SAM SHA-256 digest")
    run_size = (
        (run_root / "results/run-size.txt")
        .read_text(encoding="utf-8")
        .split()[0]
    )
    return {
        "completed_at": completed_path.read_text(encoding="utf-8").strip(),
        "provenance": provenance,
        "mapped_record_count": count,
        "output_path": str(output_path),
        "output_size_bytes": output_path.stat().st_size,
        "output_sha256": output_sha,
        "run_directory_size": run_size,
    }


def sha256_from_manifest(path: Path, filename_suffix: str) -> str:
    if not path.is_file():
        raise RuntimeError(f"Checksum manifest is missing: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) == 2 and fields[1].lstrip("*").endswith(filename_suffix):
            digest = fields[0].lower()
            if re.fullmatch(r"[0-9a-f]{64}", digest):
                return digest
    raise RuntimeError(
        f"Could not identify the SHA-256 for {filename_suffix} in {path}"
    )


def read_optional_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def read_popinsnake_result_metadata(run_root: Path) -> Dict[str, Any]:
    status_path = run_root / "RUN_STATUS"
    output_path = run_root / "results/insertions_genotypes.vcf.gz"
    provenance_dir = run_root / "provenance"
    if read_optional_text(status_path) != "COMPLETED":
        raise RuntimeError("The PopinSnake RUN_STATUS marker is not COMPLETED")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(
            "The PopinSnake run has no completed, non-empty final VCF output"
        )

    variant_count = 0
    samples: List[str] = []
    try:
        with gzip.open(output_path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("#CHROM\t"):
                    samples = line.rstrip("\n").split("\t")[9:]
                elif not line.startswith("#"):
                    variant_count += 1
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"The final PopinSnake VCF is invalid: {exc}") from exc
    if not samples:
        raise RuntimeError("The final PopinSnake VCF has no sample header")

    workflow_commit = read_optional_text(
        provenance_dir / "workflow-commit.txt"
    )
    if not re.fullmatch(r"[0-9a-f]{40}", workflow_commit):
        raise RuntimeError(
            "PopinSnake provenance has no valid upstream workflow commit"
        )
    output_sha = sha256_from_manifest(
        provenance_dir / "result-SHA256SUMS",
        "/results/insertions_genotypes.vcf.gz",
    )
    result_files = []
    for path in sorted((run_root / "results").iterdir()):
        if path.is_file():
            result_files.append(
                {"name": path.name, "size_bytes": path.stat().st_size}
            )

    provenance = {
        "workflow_commit": workflow_commit,
        "snakemake": read_optional_text(
            provenance_dir / "snakemake-version.txt"
        ),
        "micromamba": read_optional_text(
            provenance_dir / "micromamba-version.txt"
        ),
        "samtools": read_optional_text(
            provenance_dir / "samtools-version.txt"
        ),
        "submodules": read_optional_text(
            provenance_dir / "submodule-status.txt"
        ).splitlines(),
        "compatibility_patch": read_optional_text(
            provenance_dir / "compatibility.patch"
        ),
    }
    return {
        "completed_at": read_optional_text(provenance_dir / "completed-at.txt"),
        "provenance": provenance,
        "variant_record_count": variant_count,
        "samples": samples,
        "output_path": str(output_path),
        "output_size_bytes": output_path.stat().st_size,
        "output_sha256": output_sha,
        "result_files": result_files,
    }


def read_result_metadata(run_root: Path, profile: str) -> Dict[str, Any]:
    if profile == "mg4":
        return read_mg4_result_metadata(run_root)
    if profile == "popinsnake":
        return read_popinsnake_result_metadata(run_root)
    raise RuntimeError(f"Unsupported Snakemake profile: {profile}")


def collector_args(
    namespace: str,
    result: Dict[str, Any],
    attempt_count: int,
    profile: str,
) -> SimpleNamespace:
    failed_count = int(os.environ.get("FAILED_ATTEMPT_COUNT", "0"))
    failed_clause = (
        f", including {failed_count} compatibility-debugging attempts"
        if failed_count
        else ""
    )
    if profile == "mg4":
        description = (
            "Smoke-scale reproduction of the FONDA MG-4 workflow using "
            "deterministic Raptor-simulated input. The resumable session used "
            f"{attempt_count} Kubernetes Job attempts{failed_clause}, and "
            f"produced {result['mapped_record_count']} SAM records. Final "
            f"output SHA-256: {result['output_sha256']}."
        )
        resource_scope = (
            "All Kubernetes workflow Pods in the resumable MG-4 session, "
            "including earlier attempts that produced retained intermediates."
        )
    else:
        description = (
            "Reproduction of the FONDA PopinSnake genomic-insertion workflow "
            "using the three example BAM samples and chromosome 21 reference "
            "distributed by the upstream repository. The resumable session "
            f"used {attempt_count} Kubernetes Job attempts{failed_clause}, and "
            f"produced {result['variant_record_count']} VCF variant records "
            f"for {len(result['samples'])} samples. Final output SHA-256: "
            f"{result['output_sha256']}."
        )
        resource_scope = (
            "All Kubernetes workflow Pods in the resumable PopinSnake "
            "session, including earlier compatibility attempts and the final "
            "successful attempt that reused retained intermediates."
        )
    return SimpleNamespace(
        namespace=namespace,
        include_cached_origin_metrics=False,
        prom_url=required_env("PROM_URL"),
        memory_step_seconds=int(os.environ.get("MEMORY_STEP_SECONDS", "15")),
        base_uri=required_env("BASE_URI"),
        ontology_uri=required_env("ONTOLOGY_URI"),
        workflow_name=required_env("WORKFLOW_NAME"),
        workflow_uri=required_env("WORKFLOW_URI"),
        publication_uri=os.environ.get("PUBLICATION_URI", ""),
        code_uri=os.environ.get("CODE_URI", ""),
        workflow_repo_url=required_env("WORKFLOW_REPO_URL"),
        trace_archive=os.environ.get("TRACE_ARCHIVE", ""),
        application_domain_uri=os.environ.get("APPLICATION_DOMAIN_URI", ""),
        run_operator_uri=os.environ.get("RUN_OPERATOR_URI", ""),
        backend_uri=os.environ.get("BACKEND_URI", ""),
        cluster_uri=required_env("CLUSTER_URI"),
        cluster_label=os.environ.get(
            "CLUSTER_LABEL", "FONDA Kubernetes Cluster"
        ),
        engine_uri=required_env("ENGINE_URI"),
        engine_label="Snakemake",
        trace_types=(
            "Kubernetes Job and Pod status, container termination metadata, "
            "Snakemake logs and summary, provenance, and output checksums"
        ),
        trace_data_format=(
            "Kubernetes JSON, Snakemake text/TSV, JSON, and plain text"
        ),
        workflow_description="",
        run_description=description,
        duration_calculation_method=(
            "Wall-clock time from the first container start to the final "
            "container completion across the resumable Kubernetes Job session."
        ),
        resource_accounting_scope=resource_scope,
        parallelism_note=(
            "Each recorded VIVO process is one Kubernetes Job attempt. The "
            "scientific Snakemake rules run inside that Job container; CPU "
            "time is measured independently of the session wall clock."
        ),
        carbon_intensity_source=os.environ.get("CARBON_SOURCE", "fixed"),
        carbon_intensity=float(os.environ.get("CARBON_INTENSITY", "0.4")),
        electricity_maps_api_token_env="ELECTRICITY_MAPS_API_TOKEN",
        electricity_maps_zone=os.environ.get("ELECTRICITY_MAPS_ZONE", "DE"),
        electricity_maps_api_url=(
            "https://api.electricitymaps.com/v4/carbon-intensity/past-range"
        ),
        electricity_maps_latest_api_url=(
            "https://api.electricitymaps.com/v4/carbon-intensity/latest"
        ),
        electricity_maps_disable_estimations=False,
        co2map_api_url="https://api.co2map.de",
        co2map_state="DE",
        co2map_country="DE",
        co2map_data_status="preliminary",
    )


def enrich_metrics_from_pods(
    pod_metrics: Dict[str, core.PodMetrics],
    pods: Sequence[Dict[str, Any]],
) -> List[str]:
    images: List[str] = []
    by_name = {pod.get("metadata", {}).get("name"): pod for pod in pods}
    for pod_name, metrics in pod_metrics.items():
        pod = by_name.get(pod_name, {})
        metrics.node_name = metrics.node_name or pod.get("spec", {}).get(
            "nodeName"
        )
        status = workflow_container_status(pod)
        image = str(status.get("imageID") or status.get("image") or "").strip()
        if image and image not in metrics.images:
            metrics.images.append(image)
        for item in metrics.images:
            if item and item not in images:
                images.append(item)
    return images


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-file", required=True, type=Path)
    parser.add_argument("--input-metadata-file", required=True)
    return parser


def main() -> None:
    cli = build_parser().parse_args()
    namespace = required_env("NAMESPACE")
    profile = snakemake_profile()
    run_root = Path(required_env("RUN_ROOT"))
    result = read_result_metadata(run_root, profile)
    tasks, pods = build_tasks(select_attempt_pods(namespace, cli.run_id))
    if not any(task.status == "COMPLETED" for task in tasks):
        raise RuntimeError("No successful Kubernetes attempt exists for this run")
    run_start = min(task.submit for task in tasks)
    run_end = max(task.end for task in tasks if task.end is not None)
    failed_tasks = [task for task in tasks if task.status == "FAILED"]
    os.environ["FAILED_ATTEMPT_COUNT"] = str(len(failed_tasks))

    args = collector_args(namespace, result, len(tasks), profile)
    core.ensure_prometheus_reachable(args.prom_url)
    metric_names = core.prometheus_metric_names(args.prom_url)
    energy_metric = core.find_energy_metric(metric_names)
    padding = timedelta(
        seconds=int(os.environ.get("METRICS_PADDING_SECONDS", "30"))
    )
    pod_metrics = core.collect_pod_metrics(
        args, tasks, run_start - padding, run_end + padding, energy_metric
    )
    images = enrich_metrics_from_pods(pod_metrics, pods)
    any_metrics = any(
        value.cpu_seconds is not None
        or value.energy_joules is not None
        or bool(value.memory_series)
        for value in pod_metrics.values()
    )
    if not any_metrics and os.environ.get("ALLOW_MISSING_METRICS", "0") != "1":
        raise RuntimeError(
            "Prometheus returned no retained metrics for the Snakemake Pods"
        )

    carbon_info = core.resolve_carbon_intensity(args, run_start, run_end)
    code_path = Path(required_env("CODE_PATH"))
    code_version = core.sha256_source(code_path)
    workflow_commit = result["provenance"].get("workflow_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", workflow_commit):
        raise RuntimeError(
            "The run provenance has no valid upstream workflow commit"
        )

    stage_prefix = "MG-4" if profile == "mg4" else "PopinSnake"
    stages = []
    for index, task in enumerate(tasks, start=1):
        suffix_match = re.search(r"(?:-v|-)([0-9]+)$", task.name)
        suffix = suffix_match.group(1) if suffix_match else str(index)
        stages.append(
            {
                "slug": f"kubernetes-attempt-{index}",
                "label": f"{stage_prefix} Kubernetes attempt {suffix}",
                "tasks": [task],
            }
        )
    log_metadata = {
        "run_id": cli.run_id,
        "session_id": None,
        "run_name": cli.run_id,
        "engine_version": result["provenance"].get("snakemake"),
        "nextflow_version": None,
        "failure_reason": (
            f"{len(failed_tasks)} earlier attempts ended non-zero before the "
            "final resumable attempt completed successfully."
            if failed_tasks
            else None
        ),
    }
    run_status = "Succeeded with warnings" if failed_tasks else "Succeeded"
    input_datasets = core.load_input_datasets(cli.input_metadata_file)
    ttl_text, audit = core.build_ttl(
        args=args,
        tasks=tasks,
        stages=stages,
        pod_metrics=pod_metrics,
        run_start=run_start,
        run_end=run_end,
        run_status=run_status,
        log_metadata=log_metadata,
        code_version=code_version,
        git_commit=workflow_commit,
        git_dirty=True,
        energy_metric=energy_metric,
        carbon_info=carbon_info,
        node_infos=[],
        images=images,
        responsible_researchers=[],
        responsible_researcher_uris=csv_env("RESPONSIBLE_RESEARCHER_URIS"),
        subproject_uris=csv_env("SUBPROJECT_URIS"),
        language_uris=csv_env("LANGUAGE_URIS"),
        input_datasets=input_datasets,
    )
    audit["snakemake"] = {
        "profile": profile,
        "version": result["provenance"].get("snakemake"),
        "workflow_commit": workflow_commit,
        "simulator_commit": result["provenance"].get("simulator_commit"),
        "dream_yara_commit": result["provenance"].get("dream_yara_commit"),
        "submodules": result["provenance"].get("submodules"),
        "compatibility_patch": result["provenance"].get(
            "compatibility_patch"
        ),
    }
    audit["result"] = result
    audit["kubernetes_attempts"] = [
        {
            "job_name": task.name,
            "pod_name": task.pod_name,
            "status": task.status,
            "exit_code": task.exit_code,
            "started_at": task.submit.isoformat(),
            "finished_at": task.end.isoformat() if task.end else None,
        }
        for task in tasks
    ]
    audit["collector_source"] = (
        "https://github.com/YagmurKati/fonda-kubernetes-vivo-publisher"
    )

    cli.output_file.parent.mkdir(parents=True, exist_ok=True)
    cli.output_file.write_text(ttl_text, encoding="utf-8")
    audit_path = cli.output_file.with_suffix(".metrics.json")
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    summary = audit["summary"]
    print(f"Wrote TTL: {cli.output_file}")
    print(f"Wrote audit JSON: {audit_path}")
    print(f"run_uri={audit['run_uri']}")
    print(f"run_status={run_status}")
    print(f"attempt_count={len(tasks)}")
    print(f"pod_count={len(pod_metrics)}")
    print(f"cpu_seconds={summary['cpu_seconds']}")
    print(f"memory_peak_gb={summary['memory_peak_gb']}")
    print(f"energy_kwh={summary['energy_kwh']}")
    print(f"carbon_kg={summary['carbon_kg']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
