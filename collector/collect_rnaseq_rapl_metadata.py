#!/usr/bin/env python3
"""Validate retained RNA-seq/RAPL evidence and build run-specific VIVO metadata.

No cluster or network writes. Requires the evidence exported by the RNA-seq/RAPL
profile; never substitutes Kepler metrics for missing RAPL counter records.
"""
import argparse
import bisect
import csv
from datetime import datetime, timedelta, timezone, time
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import tarfile
import zipfile
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_nextflow_run_metadata import add_resource, ttl_literal as literal, ttl_uri as uri, ttl_label as label
from rapl_carbon import CarbonUnavailable, fetch_carbon, require_carbon

UTC = timezone.utc
BASE = "http://example.org/vivo-import/run-metadata/"
WORKFLOW = BASE + "workflow/small-rna-seq-rapl-energy-measurement"
NAME = "RNA-seq workflow with RAPL energy measurement"
RESEARCHER = "https://fonda.hu-berlin.de/?page_id=2066#PhilippThamm"
COMMITS = {"nextflow-io/rnaseq-nf": "5c89d3859abbe54893d4e1ae0f21115dcebd9d1d",
           "CRC-FONDA/RAPL_measurement_workflows": "8786ab77fe4761fefb150957050d862c02c3dde8"}
NODES = {"hu-worker-c34", "hu-worker-c39", "hu-worker-c41"}
SCOPE = ("Whole-node CPU-package and DRAM energy, including system services, other activity, "
         "the driver and monitoring overhead. Not exclusive workflow or task energy; no idle baseline subtracted.")
CPU_METHOD = "Sum(realtime_ms * percent_cpu / 100000) from Nextflow TSV; CPU percent is already normalized. Excludes driver and collector."


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def timestamp(value):
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Timestamp needs an explicit timezone")
    return parsed.timestamp()


def integrate_counter(path, maximum, collector_start, start, end, max_gap=5.0):
    """Unwrap microjoules and interpolate both workflow boundaries in UTC."""
    require(maximum > 0 and end > start, "Invalid counter range or execution interval")
    lines = path.read_text().splitlines()
    require(len(lines) >= 4 and len(lines) % 2 == 0, "Incomplete RAPL counter pairs")
    day = datetime.fromtimestamp(collector_start, UTC).date()
    values, times, wraps, previous_clock = [], [], 0, None
    previous_raw = None
    for index in range(0, len(lines), 2):
        raw, clock = int(lines[index]), time.fromisoformat(lines[index + 1])
        require(0 <= raw < maximum, "Counter value outside its recorded range")
        if previous_clock is not None and clock < previous_clock:
            day += timedelta(days=1)
        stamp = datetime.combine(day, clock, tzinfo=UTC).timestamp()
        if not times and stamp < collector_start - 1:
            # Collector can start immediately before midnight and sample after it.
            stamp += 86400
            day += timedelta(days=1)
        if times:
            require(0 < stamp - times[-1] <= max_gap, "RAPL gap, duplicate or out-of-order timestamp")
            wraps += int(raw < previous_raw)
            values.append(values[-1] + (raw - previous_raw) % maximum)
        else:
            require(abs(stamp - collector_start) <= max_gap, "First RAPL sample too far from collector start")
            values.append(raw)
        times.append(stamp)
        previous_clock, previous_raw = clock, raw
    require(times[0] <= start and times[-1] >= end, "RAPL samples do not cover the workflow interval")

    def at(point):
        j = bisect.bisect_right(times, point)
        if j == len(times):
            return values[-1]
        lo = max(j - 1, 0)
        return values[lo] + (values[j] - values[lo]) * (point - times[lo]) / (times[j] - times[lo])

    energy = (at(end) - at(start)) / 1_000_000
    require(math.isfinite(energy) and energy > 0, "Invalid integrated energy")
    return dict(energy_joules=energy, sample_count=len(values), counter_wraps=wraps,
                max_sample_gap_seconds=max(b - a for a, b in zip(times, times[1:])),
                max_energy_range_uj=maximum)


def cpu_seconds(row):
    value = float(row["realtime"]) * float(row["%cpu"]) / 100_000
    require(math.isfinite(value) and value >= 0, "Invalid CPU measurement")
    return value


def validate_cluster(cluster, rows, node):
    pods = read_json(cluster / "pods.json")["items"]
    tasks = {r["native_id"] for r in rows}
    scientific = [p for p in pods if p["metadata"]["name"] in tasks]
    require(len(scientific) == len(tasks) == 4, "Missing scientific task pods")
    drivers = [p for p in pods if {c["name"] for c in p["spec"]["containers"]} == {"nextflow", "rapl-monitor"}
               and p["status"]["phase"] == "Succeeded"]
    require(len(drivers) == 1, "Need exactly one successful driver and monitor pod")
    driver = drivers[0]
    rid = driver["metadata"]["labels"]["fonda.hu-berlin.de/run-id"]
    namespace = driver["metadata"]["namespace"]
    images = set()
    for pod in scientific + drivers:
        require(pod["metadata"]["namespace"] == namespace and
                pod["metadata"]["labels"].get("fonda.hu-berlin.de/run-id") == rid,
                "Task pod is not owned by this run")
        require(pod["spec"].get("nodeName") == node and node in NODES, "Unexpected execution node")
        require(pod["spec"].get("nodeSelector", {}).get("usedby") == "prototyping", "Missing prototyping selector")
        require(pod["status"]["phase"] == "Succeeded", "A run pod did not succeed")
        containers = pod["spec"].get("initContainers", []) + pod["spec"]["containers"]
        statuses = pod["status"].get("initContainerStatuses", []) + pod["status"].get("containerStatuses", [])
        require({c["name"] for c in containers} == {c["name"] for c in statuses}, "Missing container status")
        for status in statuses:
            require(status["state"].get("terminated", {}).get("exitCode") == 0, "Nonzero or missing container exit code")
            images.add(status["imageID"])
    for pod in scientific:
        for container in pod["spec"]["containers"]:
            require(str(container["resources"]["limits"]["cpu"]) == "2", "Unexpected task CPU limit")
    job_name = driver["metadata"]["labels"]["job-name"]
    jobs = read_json(cluster / "jobs.json")["items"]
    job = next(j for j in jobs if j["metadata"]["name"] == job_name)
    require(any(c["type"] == "Complete" and c["status"] == "True" for c in job["status"]["conditions"]), "Job is not Complete")
    return dict(run_id=rid, namespace=namespace, job=job_name, node=node, image_ids=sorted(images))


def validate(evidence, cluster):
    start = timestamp((evidence / "run/workflow-start.txt").read_text())
    end = timestamp((evidence / "run/workflow-end.txt").read_text())
    require(end > start, "Invalid workflow interval")
    require((evidence / "run/driver-exit-code.txt").read_text().strip() == "0", "Driver failed")
    meta = read_json(evidence / "rapl/metadata.json")
    require(meta["units"] == "microjoules", "Unexpected energy counter units")
    require(len(meta["domains"]) == 2 and {d["name"] for d in meta["domains"]} == {"package-0", "dram"}, "Unsupported or missing RAPL domains")
    counter_start = timestamp((evidence / "rapl/collector-start.txt").read_text())
    energies = {}
    for domain in meta["domains"]:
        key = {"package-0": "package", "dram": "dram"}[domain["name"]]
        energies[key] = integrate_counter(evidence / "rapl" / (key + "-energy.txt"),
                                         domain["max_energy_range_uj"], counter_start, start, end)
    with (evidence / "run/trace.tsv").open() as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    require(len(rows) == 4 and {r["process"].split(":")[-1] for r in rows} == {"FASTQC", "INDEX", "QUANT", "MULTIQC"}, "Expected four RNA-seq tasks")
    for row in rows:
        require(row["status"] == "COMPLETED" and row["exit"] == "0", "Unsuccessful or cached task")
        require(int(row["cpus"]) == 2, "Unexpected task CPU allocation")
        require(start <= int(row["submit"]) / 1000 < int(row["complete"]) / 1000 <= end, "Task outside workflow interval")
        raw_files = list((evidence / "task-records").glob(row["hash"] + "*/.command.trace"))
        require(len(raw_files) == 1, "Missing or ambiguous task trace")
        raw = dict(line.split("=", 1) for line in raw_files[0].read_text().splitlines() if "=" in line)
        require(int(raw["realtime"]) == int(row["realtime"]) and int(raw["peak_rss"]) * 1024 == int(row["peak_rss"]), "Task trace units or values disagree")
        require(math.isclose(int(raw["%cpu"]) / 10, float(row["%cpu"])), "CPU percentage units disagree")
        require((raw_files[0].parent / ".exitcode").read_text().strip() == "0", "Task command failed")
        cpu_seconds(row)
    placement = validate_cluster(cluster, rows, meta["node"])
    quant = list((evidence / "results").rglob("quant.sf"))
    require(len(quant) == 1, "Expected one Salmon quantification")
    with quant[0].open() as stream:
        estimates = list(csv.DictReader(stream, delimiter="\t"))
    require(len(estimates) == 30215, "Unexpected number of quantified targets")
    require(all(math.isfinite(float(r[k])) and float(r[k]) >= 0 for r in estimates for k in ("TPM", "NumReads")), "Invalid Salmon estimates")
    require(math.isclose(sum(float(r["TPM"]) for r in estimates), 1_000_000, rel_tol=1e-5), "TPM sum is inconsistent")
    salmon_files = list((evidence / "results").rglob("meta_info.json"))
    require(len(salmon_files) == 1, "Missing or ambiguous Salmon metadata")
    salmon = read_json(salmon_files[0])
    require(salmon["num_processed"] == 25024930 and 0 < salmon["num_mapped"] <= salmon["num_processed"], "Unexpected processed/mapped fragment count")
    require(math.isclose(sum(float(r["NumReads"]) for r in estimates), salmon["num_mapped"], abs_tol=1), "Assigned and mapped counts disagree")
    qc_archives = list((evidence / "results").rglob("*fastqc.zip"))
    require(len(qc_archives) == len(list((evidence / "results").rglob("*fastqc.html"))) == 2, "Missing paired FastQC outputs")
    for path in qc_archives:
        with zipfile.ZipFile(path) as archive:
            data = archive.read(next(n for n in archive.namelist() if n.endswith("/fastqc_data.txt"))).decode()
        require(re.search(r"(?m)^Total Sequences\t25024930$", data) is not None, "FastQC read count mismatch")
    report = evidence / "results/multiqc_report.html"
    require(report.stat().st_size > 10000 and "multiqc" in report.read_text().lower(), "Missing MultiQC report")
    inputs = read_json(evidence / "provenance/inputs.json")
    require(len(inputs) == 3, "Missing input provenance")
    expected = [(1172239021, "ca516408de480463f9b4c2825766a4a2"), (1198117461, "7a3e4b1258a4170e1fa8a8d0dd714aff")]
    require([(v["bytes"], v["md5"]) for v in inputs[:2]] == expected, "Read input checksums disagree")
    require(inputs[2]["sha256"] == "007c99289b98db767cd9822c9d78c20ae5ee17084559ed68da82df2e7a333b31", "Reference checksum mismatch")
    archives = read_json(evidence / "provenance/archives.json")
    require(len(archives) == 2 and {v["repository"] for v in archives} == set(COMMITS), "Missing source archive provenance")
    for source in archives:
        require(COMMITS.get(source["repository"]) == source["commit"], "Unexpected source commit")
        path = evidence / "provenance" / (source["repository"].split("/")[-1] + "-" + source["commit"] + ".tar.gz")
        require(sha(path) == source["sha256"], "Source archive checksum mismatch")
    change = read_json(evidence / "provenance/source-change.json")
    original = evidence / "source-backups/quant-main.nf.original"
    require(sha(original) == change["original_sha256"], "Original source backup checksum mismatch")
    adapted = original.read_bytes().replace(b"--libType=U", b"--libType=A")
    require(hashlib.sha256(adapted).hexdigest() == change["new_sha256"], "Unexpected source adaptation")
    session_match = re.search(r"Session UUID: ([a-f0-9-]+)", (evidence / "run/.nextflow.log").read_text())
    require(session_match is not None, "Missing Nextflow session identity")
    for name in ("report.html", "timeline.html", "workflow.log"):
        require((evidence / "run" / name).stat().st_size > 0, "Missing Nextflow execution evidence")
    summary = dict(status="validated", start_utc=datetime.fromtimestamp(start, UTC).isoformat(),
                   end_utc=datetime.fromtimestamp(end, UTC).isoformat(), duration_seconds=end-start,
                   completed_task_count=4, cpu_seconds=sum(cpu_seconds(r) for r in rows),
                   memory_peak_gb=max(int(r["peak_rss"]) for r in rows) / 1e9,
                   energy_kwh=energies["package"]["energy_joules"] / 3_600_000,
                   rapl=energies, measurement_scope=SCOPE, session_id=session_match[1],
                   processed_fragments=salmon["num_processed"], mapped_fragments=salmon["num_mapped"],
                   mapping_percent=salmon["percent_mapped"], source_change=change, **placement)
    return summary, rows, inputs


def build_ttl(summary, rows, inputs, archive_sha, backend_uri=None):
    # Session UUID makes the run identity stable across repeated collections.
    key = "rnaseq-rapl-" + summary["session_id"]
    run, date = BASE + "run/" + key, BASE + "datetime/" + key
    lines = [f"@prefix {p}: <{v}> ." for p, v in {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "rm": "http://example.org/ontology/run-metadata#", "vivo": "http://vivoweb.org/ontology/core#",
        "prov": "http://www.w3.org/ns/prov#", "dcterms": "http://purl.org/dc/terms/",
        "xsd": "http://www.w3.org/2001/XMLSchema#"}.items()] + [""]

    def local(value):
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else datetime.fromtimestamp(value, UTC)
        return literal(parsed.astimezone(ZoneInfo("Europe/Berlin")).replace(tzinfo=None).isoformat(timespec="seconds"), "xsd:dateTime")

    def resource(subject, properties):
        add_resource(lines, uri(subject), properties)

    title = f"{NAME} · SRR16287545 · {summary['start_utc']}"
    method = (f"Wrap-corrected RAPL microjoule deltas, linearly interpolated at workflow boundaries. "
              f"CPU package: {summary['rapl']['package']['energy_joules']:.6f} J / 3600000 = kWh. "
              f"DRAM: {summary['rapl']['dram']['energy_joules']:.6f} J, reported separately and excluded from kWh. " + SCOPE)
    props = [("rdf:type", "rm:RunMetadata"), ("rdfs:label", label(title)), ("dcterms:title", label(title)),
             ("rm:workflow", uri(WORKFLOW)), ("rm:workflowEngine", uri(BASE + "engine/nextflow")),
             ("rm:computeCluster", uri(BASE + "cluster/fonda-cluster")), ("vivo:dateTimeValue", uri(date)),
             ("rm:runStatus", literal("Succeeded")), ("rm:taskCount", literal(4)), ("rm:succeededTaskCount", literal(4)),
             ("rm:failedTaskCount", literal(0)), ("rm:podCount", literal(4)),
             ("rm:startTime", local(summary["start_utc"])), ("rm:endTime", local(summary["end_utc"])),
             ("prov:startedAtTime", local(summary["start_utc"])), ("prov:endedAtTime", local(summary["end_utc"])),
             ("rm:durationSeconds", literal(round(summary["duration_seconds"]))),
             ("rm:durationCalculationMethod", literal(f"Nextflow command interval: {summary['duration_seconds']:.6f} seconds; excludes input preparation. Display timestamps use Europe/Berlin.")),
             ("rm:cpuTimeSeconds", literal(summary["cpu_seconds"])), ("rm:cpuTimeCalculationMethod", literal(CPU_METHOD)),
             ("rm:memoryPeakGB", literal(summary["memory_peak_gb"])),
             ("rm:memoryCalculationMethod", literal("Largest task peak RSS, bytes / 1e9. Sequential tasks; excludes driver. No time-averaged memory measured.")),
             ("rm:energyKWh", literal(summary["energy_kwh"])), ("rm:energyCalculationMethod", literal(method)),
             ("rm:energyMetricSource", literal("Intel RAPL powercap energy_uj; package-0 and dram")),
             ("rm:energyCalculationUsesFallbackEstimate", literal(False)),
             ("rm:resourceAccountingScope", literal(SCOPE + " CPU and memory cover the four task processes.")),
             ("rm:resourceAccountingStartTime", local(summary["start_utc"])), ("rm:resourceAccountingEndTime", local(summary["end_utc"])),
             ("rm:executionHost", literal(summary["node"])), ("rm:nextflowSessionId", literal(summary["session_id"])),
             ("rm:jobName", literal(summary["job"])), ("rm:gitCommit", literal(COMMITS["nextflow-io/rnaseq-nf"])),
             ("rm:codeVersion", literal("Salmon --libType=A; adapted module SHA-256 " + summary["source_change"]["new_sha256"])),
             ("rm:gpuRequested", literal(False)), ("rm:gpuMetricsAvailable", literal(False)),
             ("rm:traceTypes", literal("Nextflow task trace, commands, logs, report and timeline; RAPL CPU-package and DRAM counters; Kubernetes status, logs and image identifiers; input provenance, checksums and source diff; FastQC, Salmon and MultiQC outputs")),
             ("rm:traceDataFormat", literal("TSV, JSON, plain text, HTML, shell and Python scripts, unified diff, ZIP, and TAR.GZ")),
             ("dcterms:description", label(f"Complete SRR16287545 paired-end RNA-seq and Ensembl 106 Drosophila cDNA reference. Mapped {summary['mapped_fragments']} of {summary['processed_fragments']} fragments. Sequential tasks, two CPUs and 8 GiB per task. Energy method adapted from CRC-FONDA/RAPL_measurement_workflows; workflow implementation nextflow-io/rnaseq-nf. Does not reproduce the original paper experiment. Verified local evidence archive SHA-256: {archive_sha}. No public archive URL assigned."))]
    carbon = require_carbon(summary)
    carbon_method = ("Sum of measured CPU-package kWh in each covered hour multiplied by that hour's Germany grid intensity. "
                     "RAPL boundaries are interpolated; no annual-average or collection-time proxy is used. "
                     f"DRAM is separate: {carbon['dram_kg']:.9f} kg {carbon['basis']}. "
                     "The displayed emissions field covers CPU-package energy only, including other node activity. "
                     "Cooling and other hardware are excluded. Emissions basis: " + carbon['basis'] + ".")
    props += [("rm:carbonEmissionKgCO2e", literal(carbon["package_kg"])),
              ("rm:carbonIntensityAssumptionKgCO2ePerKWh", literal(carbon["intensity_kg_per_kwh"])),
              ("rm:carbonIntensitySource", literal(carbon["source"])),
              ("rm:carbonIntensitySourceLink", literal(carbon["source_url"], "xsd:anyURI")),
              ("rm:carbonIntensityZone", literal(carbon["zone"])),
              ("rm:carbonIntensityDataPointCount", literal(len(carbon["intervals"]))),
              ("rm:carbonIntensityWindowStart", literal(carbon["source_window_start"], "xsd:dateTime")),
              ("rm:carbonIntensityWindowEnd", literal(carbon["source_window_end"], "xsd:dateTime")),
              ("rm:carbonIntensityIncludesEstimatedData", literal(carbon["includes_estimates"])),
              ("rm:carbonIntensityEmissionsBasis", literal(carbon["basis"])),
              ("rm:carbonIntensityTemporalGranularity", literal("hourly")),
              ("rm:carbonCalculationMethod", literal(carbon_method))]
    if backend_uri:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "publisher"))
        from publish_vivo import validate_absolute_iri
        validate_absolute_iri(backend_uri, "backend URI")
        props.append(("rm:backend", uri(backend_uri)))
    props += [("rm:containerImage", literal(image)) for image in summary["image_ids"]]
    props += [("rm:codeCommitLink", literal("https://github.com/" + repo + "/commit/" + commit, "xsd:anyURI")) for repo, commit in COMMITS.items()]
    datasets = [BASE + "input-dataset/ena-srr16287545-paired-reads", BASE + "input-dataset/ensembl-106-drosophila-bdgp6-32-cdna"]
    props += [("rm:inputData", uri(dataset)) for dataset in datasets]
    for row in rows:
        process = BASE + "process/" + key + "-" + row["process"].split(":")[-1].lower()
        props.append(("rm:hasWorkflowProcess", uri(process)))
        resource(process, [("rdf:type", "rm:WorkflowProcessRun"), ("rdfs:label", label(row["process"])),
                 ("rm:taskName", literal(row["process"])), ("rm:isWorkflowProcessOf", uri(run)),
                 ("rm:runStatus", literal("Succeeded")), ("rm:taskCount", literal(1)),
                 ("rm:cpuTimeSeconds", literal(cpu_seconds(row))), ("rm:cpuTimeCalculationMethod", literal(CPU_METHOD)),
                 ("rm:memoryPeakGB", literal(int(row["peak_rss"]) / 1e9)),
                 ("rm:durationSeconds", literal(round((int(row["complete"]) - int(row["submit"])) / 1000))),
                 ("prov:startedAtTime", local(int(row["submit"]) / 1000)), ("prov:endedAtTime", local(int(row["complete"]) / 1000))])
    resource(run, props)
    resource(date, [("rdf:type", "vivo:DateTimeValue"), ("vivo:dateTime", local(summary["start_utc"])), ("vivo:dateTimePrecision", "vivo:yearMonthDayTimePrecision")])
    # Existing workflow labels/purpose stay under curator control; add only links.
    resource(WORKFLOW, [("rm:hasRun", uri(run)), ("rm:hasWorkflowRun", uri(run)), ("rm:responsibleResearcher", uri(RESEARCHER))]
             + [("rm:hasUsedInputData", uri(d)) for d in datasets])
    resource(RESEARCHER, [("rm:workflows", uri(WORKFLOW))])
    resource(BASE + "cluster/fonda-cluster", [("rm:hasRun", uri(run))])
    for dataset in datasets:
        resource(dataset, [("rm:usedByWorkflowRun", uri(run)), ("rm:inputDataOfWorkflow", uri(WORKFLOW))])
    return "\n".join(lines), run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="Exported evidence/completed-run directory")
    parser.add_argument("--cluster", type=Path, required=True, help="Exported evidence/cluster directory")
    parser.add_argument("--output", type=Path, required=True, help="New local publication directory")
    parser.add_argument("--backend-uri", help="Optional existing VIVO backend resource URI")
    args = parser.parse_args()
    require(not args.output.exists(), "Output directory already exists; preserve it and choose a fresh path")
    summary, rows, inputs = validate(args.evidence, args.cluster)
    meta = read_json(args.evidence / "rapl/metadata.json")
    collector_start = timestamp((args.evidence / "rapl/collector-start.txt").read_text())

    def energy_between(start, end):
        energies = {}
        for domain in meta["domains"]:
            key = {"package-0": "package", "dram": "dram"}[domain["name"]]
            energies[key] = integrate_counter(args.evidence / "rapl" / (key + "-energy.txt"),
                domain["max_energy_range_uj"], collector_start, start, end)["energy_joules"]
        return energies

    try:
        summary["carbon"] = fetch_carbon(summary, energy_between)
    except CarbonUnavailable as exc:
        args.output.mkdir(parents=True)
        with (args.output / "carbon-unavailable.json").open("x") as stream:
            json.dump(dict(status="unavailable", start_utc=summary["start_utc"], end_utc=summary["end_utc"],
                           reason=str(exc), attempts=exc.attempts), stream, indent=2)
        raise SystemExit(str(exc) + " Keep the evidence and choose a new publication directory for the retry.")
    args.output.mkdir(parents=True)
    carbon_file = args.output / "carbon-accounting.json"
    with carbon_file.open("x") as stream:
        json.dump(summary["carbon"], stream, indent=2)
    checksums = {"carbon-accounting.json": sha(carbon_file)}
    archive_path = args.output / "trace-archive.tar.gz"
    with tarfile.open(archive_path, "x:gz") as archive:
        archive.add(carbon_file, arcname="carbon-accounting.json", recursive=False)
        for directory, prefix in ((args.evidence, "evidence"), (args.cluster, "kubernetes")):
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    require(not path.is_symlink(), "Evidence file must not be a symlink")
                    name = prefix + "/" + path.relative_to(directory).as_posix()
                    checksums[name] = sha(path)
                    archive.add(path, arcname=name, recursive=False)
    with tarfile.open(archive_path) as archive:
        for name, digest in checksums.items():
            require(hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest, "Archive checksum mismatch")
    archive_sha = sha(archive_path)
    ttl, run = build_ttl(summary, rows, inputs, archive_sha, args.backend_uri)
    summary.update(run_uri=run, workflow_uri=WORKFLOW, archive_sha256=archive_sha, trace_archive_public_url=None,
                   ttl_sha256=hashlib.sha256((ttl + "\n").encode()).hexdigest())
    for name, value in (("run.ttl", ttl), ("validation.json", json.dumps(summary, indent=2)),
                        ("checksums.json", json.dumps(checksums, indent=2))):
        with (args.output / name).open("x") as stream:
            stream.write(value + "\n")
    print(json.dumps({k: summary[k] for k in ("status", "duration_seconds", "cpu_seconds", "energy_kwh", "run_uri")}, indent=2))


if __name__ == "__main__":
    main()
