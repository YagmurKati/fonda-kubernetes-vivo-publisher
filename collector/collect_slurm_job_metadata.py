#!/usr/bin/env python3
"""Build VIVO run metadata for one finished Slurm job (HPC@HU).

Inputs:
  * Slurm accounting (`sacct`) for the job: times, state, CPU time, memory and
    the node energy measured by `acct_gather_energy/ipmi`;
  * the node samples written by `collector/slurm/run-with-node-sampler.sh`
    while the job ran (node CPU use and IPMI power).

IPMI measures the whole node. The job's energy is therefore estimated as its
CPU-time share of the node energy:

    job energy = node energy x (job CPU time / CPU time of everything on the node)

No cluster or network writes; the Turtle file is published separately with
publisher/publish_vivo.py.
"""
import argparse
import bisect
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_nextflow_run_metadata import add_resource, ttl_literal as literal, ttl_uri as uri, ttl_label as label

UTC = timezone.utc
BASE = "http://example.org/vivo-import/run-metadata/"
SACCT_FIELDS = ("JobID", "JobName", "State", "Start", "End", "ElapsedRaw", "TotalCPU", "NCPUS",
                "MaxRSS", "ConsumedEnergyRaw", "NodeList", "NNodes", "Partition", "ExitCode", "AllocTRES")
STATUS = {"COMPLETED": "Succeeded", "FAILED": "Failed", "TIMEOUT": "Failed", "OUT_OF_MEMORY": "Failed",
          "NODE_FAIL": "Failed", "BOOT_FAIL": "Failed", "DEADLINE": "Failed", "PREEMPTED": "Failed",
          "CANCELLED": "Cancelled", "RUNNING": "Running", "PENDING": "Queued"}
MIN_SAMPLE_COVERAGE = 0.9
TRACE_SLACK_SECONDS = 120
SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}
DURATION_UNITS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_cpu_time(value):
    """Slurm TotalCPU: [DD-][HH:]MM:SS[.mmm] -> seconds."""
    value = value.strip()
    require(value, "sacct reported no TotalCPU")
    days = 0
    if "-" in value:
        day_text, value = value.split("-", 1)
        days = int(day_text)
    parts = [float(p) for p in value.split(":")]
    require(1 <= len(parts) <= 3, "Unexpected TotalCPU format: " + value)
    while len(parts) < 3:
        parts.insert(0, 0.0)
    hours, minutes, seconds = parts
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def parse_memory_bytes(value):
    value = value.strip()
    if not value:
        return None
    match = re.fullmatch(r"([0-9.]+)([KMGTP]?)", value)
    require(match is not None, "Unexpected MaxRSS format: " + value)
    factor = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4, "P": 1024 ** 5}[match[2]]
    return float(match[1]) * factor


def read_sacct(job_id, sacct_file=None):
    if sacct_file:
        text = Path(sacct_file).read_text()
    else:
        command = ["sacct", "-j", str(job_id), "--parsable2", "--noheader", "--format=" + ",".join(SACCT_FIELDS)]
        text = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60).stdout
    split = [line.split("|") for line in text.splitlines() if line.strip()]
    require(split and all(len(r) == len(SACCT_FIELDS) for r in split), "Unexpected sacct output")
    rows = [dict(zip(SACCT_FIELDS, r)) for r in split]
    jobs = [r for r in rows if r["JobID"] == str(job_id)]
    require(len(jobs) == 1, f"sacct has no single record for job {job_id}")
    return jobs[0], [r for r in rows if r["JobID"] != str(job_id)]


def read_info(evidence):
    info = {}
    for line in (evidence / "job-info.tsv").read_text().splitlines():
        key, _, value = line.partition("\t")
        info[key] = value
    return info


def read_node_info(evidence):
    """Node hardware from node-info.tsv (written by collector/slurm/node-info.sh)."""
    path = evidence / "node-info.tsv"
    if not path.exists():
        return {}
    info = {}
    for line in path.read_text().splitlines():
        key, _, value = line.partition("\t")
        if value.strip():
            info[key] = value.strip()
    return info


def parse_duration(value):
    """Nextflow trace duration such as '529ms', '3.4s', '1m 2s', '1h 2m 3s'."""
    value = value.strip()
    if value in ("", "-"):
        return None
    total = 0.0
    for number, unit in re.findall(r"([0-9.]+)\s*(ms|s|m|h|d)", value):
        total += float(number) * DURATION_UNITS[unit]
    return total


def parse_size(value):
    match = re.fullmatch(r"([0-9.]+)\s*(B|KB|MB|GB|TB)", value.strip())
    return float(match[1]) * SIZE_UNITS[match[2]] if match else None


def process_name(task_name):
    """'NFCORE_X:WF:PROC (tag)' -> 'PROC'."""
    return re.sub(r"\s*\(.*\)\s*$", "", task_name).split(":")[-1]


def read_trace(paths, start, end, tz):
    """Pick the Nextflow trace whose tasks lie inside the job; group by process."""
    for path in paths:
        rows = []
        with open(path, newline="") as stream:
            header = stream.readline().rstrip("\n").split("\t")
            for line in stream:
                if line.strip():
                    rows.append(dict(zip(header, line.rstrip("\n").split("\t"))))
        if not rows or not {"name", "status", "submit", "duration", "realtime", "%cpu", "peak_rss"} <= set(header):
            continue
        submits = [datetime.strptime(r["submit"][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz).timestamp()
                   for r in rows if r["submit"] not in ("", "-")]
        if not submits or min(submits) < start - TRACE_SLACK_SECONDS or max(submits) > end + TRACE_SLACK_SECONDS:
            continue
        processes = {}
        for row in rows:
            name = process_name(row["name"])
            entry = processes.setdefault(name, dict(name=name, tasks=0, status={}, cpu=0.0, rss=None,
                                                    start=None, end=None))
            entry["tasks"] += 1
            entry["status"][row["status"]] = entry["status"].get(row["status"], 0) + 1
            realtime = parse_duration(row["realtime"])
            cpu_pct = row["%cpu"].rstrip("%")
            if realtime is not None and cpu_pct not in ("", "-"):
                entry["cpu"] += realtime * float(cpu_pct) / 100
            rss = parse_size(row["peak_rss"])
            if rss is not None:
                entry["rss"] = max(entry["rss"] or 0, rss)
            if row["submit"] not in ("", "-"):
                begin = datetime.strptime(row["submit"][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz).timestamp()
                finish = begin + (parse_duration(row["duration"]) or 0)
                entry["start"] = begin if entry["start"] is None else min(entry["start"], begin)
                entry["end"] = finish if entry["end"] is None else max(entry["end"], finish)
        return dict(path=str(path), tasks=len(rows), processes=list(processes.values()),
                    status=_count(r["status"] for r in rows))
    return None


def _count(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def read_nextflow_log(paths, start, end, tz):
    """Pick the .nextflow.log written during the job; return version, session, images, revision."""
    year = datetime.fromtimestamp(start, tz).year
    for path in paths:
        text = Path(path).read_text(errors="replace")
        first = re.match(r"([A-Z][a-z]{2}-\d{2} \d{2}:\d{2}:\d{2})", text)
        if not first:
            continue
        began = datetime.strptime(f"{year}-{first[1]}", "%Y-%b-%d %H:%M:%S").replace(tzinfo=tz).timestamp()
        if not (start - TRACE_SLACK_SECONDS <= began <= end):
            continue
        version = re.search(r"N E X T F L O W\s+~\s+version\s+(\S+)", text)
        session = re.search(r"Session UUID: ([0-9a-f-]{36})", text)
        revision = re.search(r"revision: ([0-9a-f]{7,40}) \[([^\]]+)\]", text)
        images = sorted(set(re.findall(r"docker://([^\s\]\[]+)", text)))
        return dict(path=str(path), version=version[1] if version else None,
                    session=session[1] if session else None,
                    revision=revision[1] if revision else None, revision_name=revision[2] if revision else None,
                    images=images)
    return None


def read_samples(evidence):
    samples = []
    for line in (evidence / "node-samples.tsv").read_text().splitlines():
        fields = line.split("\t")
        require(len(fields) == 4, "Malformed node sample line")
        stamp = float(fields[0])
        busy = None if fields[1] == "NA" else float(fields[1])
        cpus = None if fields[2] == "NA" else int(fields[2])
        watts = None if fields[3] == "NA" else float(fields[3])
        samples.append((stamp, busy, cpus, watts))
    samples.sort()
    require(len(samples) >= 2, "Need at least two node samples")
    return samples


def interpolate(times, values, point):
    j = bisect.bisect_left(times, point)
    if j <= 0:
        return values[0]
    if j >= len(times):
        return values[-1]
    a, b = times[j - 1], times[j]
    return values[j - 1] + (values[j] - values[j - 1]) * (point - a) / (b - a)


def power_profile(samples, start, end):
    """Return a function giving the fraction of [start, end] energy in [a, b].

    Uses the sampled IPMI power, linearly interpolated and held constant beyond
    the first/last sample. Without power samples the energy is spread evenly in
    time. The fractions of a partition of [start, end] always sum to one.
    """
    points = [(t, w) for t, _, _, w in samples if w is not None]
    if len(points) < 2:
        return (lambda a, b: (min(b, end) - max(a, start)) / (end - start)), 0
    times = [p[0] for p in points]
    watts = [p[1] for p in points]
    grid = sorted({start, end, *[t for t in times if start < t < end]})
    cumulative = [0.0]
    for a, b in zip(grid, grid[1:]):
        cumulative.append(cumulative[-1] + (interpolate(times, watts, a) + interpolate(times, watts, b)) / 2 * (b - a))
    total = cumulative[-1]
    require(total > 0, "Sampled node power is zero")

    def at(point):
        point = min(max(point, start), end)
        j = bisect.bisect_right(grid, point) - 1
        if j >= len(grid) - 1:
            return total
        a, b = grid[j], grid[j + 1]
        wa = interpolate(times, watts, a)
        wp = interpolate(times, watts, point)
        return cumulative[j] + (wa + wp) / 2 * (point - a)

    return (lambda a, b: (at(b) - at(a)) / total), len(points)


def summarize(job, steps, info, samples, tz):
    job_id = job["JobID"]
    require(info.get("slurm_job_id") in ("", job_id), "Evidence directory belongs to another Slurm job")
    require(job["NNodes"].strip() == "1", "Only single-node jobs are supported (node energy is per node)")
    state = job["State"].split()[0]
    require(state not in ("RUNNING", "PENDING"), "The job has not finished yet")
    start = datetime.fromisoformat(job["Start"]).replace(tzinfo=tz)
    end = datetime.fromisoformat(job["End"]).replace(tzinfo=tz)
    elapsed = float(job["ElapsedRaw"])
    require(elapsed > 0 and end > start, "Invalid job interval")
    job_cpu = parse_cpu_time(job["TotalCPU"])

    energies = [int(r["ConsumedEnergyRaw"]) for r in [job, *steps] if r["ConsumedEnergyRaw"].strip().isdigit()]
    node_energy = max(energies) if energies else 0
    memory = [m for m in (parse_memory_bytes(r["MaxRSS"]) for r in [job, *steps]) if m is not None]

    busy = [(t, b) for t, b, _, _ in samples if b is not None]
    require(len(busy) >= 2, "Node samples contain no CPU readings; was node_exporter reachable?")
    window = busy[-1][0] - busy[0][0]
    coverage = window / elapsed
    require(coverage >= MIN_SAMPLE_COVERAGE,
            f"Node samples cover only {coverage:.0%} of the job; wrap the whole job command with the sampler")
    node_busy = busy[-1][1] - busy[0][1]
    require(node_busy > 0, "Node CPU counter did not increase")
    # The job's CPU time is accounted over the whole job; scale the node's CPU
    # time to the same length before dividing.
    node_busy_job = node_busy * elapsed / window
    share = min(job_cpu / node_busy_job, 1.0)
    cpu_counts = [c for _, _, c, _ in samples if c]
    node_cpus = max(cpu_counts) if cpu_counts else None

    start_ts, end_ts = start.timestamp(), end.timestamp()
    fraction, power_points = power_profile(samples, start_ts, end_ts)
    if node_energy <= 0:
        watts = [(t, w) for t, _, _, w in samples if w is not None]
        require(len(watts) >= 2, "No IPMI energy from Slurm and no sampled power")
        node_energy = sum((a[1] + b[1]) / 2 * (b[0] - a[0]) for a, b in zip(watts, watts[1:])) * elapsed / window
        energy_source = "integrated ipmi_exporter power samples (Slurm reported no ConsumedEnergy)"
    else:
        energy_source = "Slurm acct_gather_energy/ipmi ConsumedEnergyRaw"
    job_energy = node_energy * share

    return dict(
        job_id=job_id, job_name=job["JobName"], state=state, status=STATUS.get(state, state.title()),
        exit_code=job["ExitCode"], partition=job["Partition"], node=job["NodeList"], ncpus=int(job["NCPUS"]),
        alloc_tres=job["AllocTRES"], gpu_requested="gres/gpu" in job["AllocTRES"],
        node_cpus=node_cpus, start_utc=start.astimezone(UTC).isoformat(), end_utc=end.astimezone(UTC).isoformat(),
        duration_seconds=elapsed, cpu_seconds=job_cpu,
        memory_peak_gb=(max(memory) / 1e9) if memory else None,
        node_energy_joules=float(node_energy), node_energy_source=energy_source,
        node_busy_cpu_seconds=node_busy_job, sample_window_seconds=window, sample_coverage=coverage,
        sample_count=len(samples), power_sample_count=power_points,
        sample_interval_seconds=info.get("sample_interval_seconds", ""),
        cpu_share=share, energy_joules=job_energy, energy_kwh=job_energy / 3_600_000,
        namespace="", fraction=fraction)


def fetch_carbon_optional(summary):
    """Time-matched hourly German grid intensity; None if unavailable."""
    from rapl_carbon import CarbonUnavailable, fetch_carbon

    total = summary["energy_joules"]

    def energy_between(a, b):
        return {"package": total * summary["fraction"](a, b), "dram": 0.0}

    try:
        return fetch_carbon(summary, energy_between)
    except CarbonUnavailable as exc:
        print("WARNING: no carbon-intensity data matches this run's time (check ELECTRICITY_MAPS_API_TOKEN); "
              "carbon values are left out.", file=sys.stderr)
        return None


def run_period(start_utc, end_utc, tz):
    """'2026-10-01 18:42–18:57 CEST'; the zone name (CET or CEST) follows daylight saving time."""
    start = datetime.fromisoformat(start_utc).astimezone(tz)
    end = datetime.fromisoformat(end_utc).astimezone(tz)
    end_text = end.strftime("%H:%M") if end.date() == start.date() else end.strftime("%Y-%m-%d %H:%M")
    if start.tzname() == end.tzname():
        return f"{start:%Y-%m-%d %H:%M}–{end_text} {start.tzname()}"
    return f"{start:%Y-%m-%d %H:%M} {start.tzname()}–{end_text} {end.tzname()}"


def build_ttl(summary, args, tz):
    key = "hpc-at-hu-slurm-" + summary["job_id"] + "-" + summary["start_utc"][:19].replace("-", "").replace(":", "").replace("T", "t")
    run, date = BASE + "run/" + key, BASE + "datetime/" + key
    lines = [f"@prefix {p}: <{v}> ." for p, v in {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "rm": "http://example.org/ontology/run-metadata#", "vivo": "http://vivoweb.org/ontology/core#",
        "prov": "http://www.w3.org/ns/prov#", "dcterms": "http://purl.org/dc/terms/",
        "xsd": "http://www.w3.org/2001/XMLSchema#"}.items()] + [""]

    def local(value):
        parsed = datetime.fromisoformat(value)
        return literal(parsed.astimezone(tz).replace(tzinfo=None).isoformat(timespec="seconds"), "xsd:dateTime")

    s = summary
    title = f"{args.run_label or s['job_name']} · run {run_period(s['start_utc'], s['end_utc'], tz)}"
    node_cpus = f" of {s['node_cpus']} node CPUs" if s["node_cpus"] else ""
    scope = (f"Single node {s['node']} ({args.cluster_label}), shared with other jobs. Energy is an estimate: "
             "the job's CPU-time share of the measured whole-node energy. Idle and other node power is "
             "distributed by CPU time; cooling and network are excluded.")
    method = (f"Node energy: {s['node_energy_source']}, {s['node_energy_joules']:.0f} J over the job "
              f"({s['duration_seconds']:.0f} s, whole node). Job share = job CPU time {s['cpu_seconds']:.1f} s / "
              f"CPU time of all processes on the node in the same interval {s['node_busy_cpu_seconds']:.1f} s "
              f"(node_exporter node_cpu_seconds_total, all modes except idle and iowait; {s['sample_count']} samples "
              f"every {s['sample_interval_seconds']} s, covering {s['sample_coverage']:.0%} of the job) = {s['cpu_share']:.4f}. "
              f"Job energy = {s['node_energy_joules']:.0f} J x {s['cpu_share']:.4f} = {s['energy_joules']:.0f} J, "
              f"converted to kilowatt-hours (1 kWh = 3,600,000 J): {s['energy_kwh']:.6f} kWh. " + scope)
    props = [("rdf:type", "rm:RunMetadata"), ("rdfs:label", label(title)), ("dcterms:title", label(title)),
             ("rm:workflow", uri(args.workflow_uri)), ("rm:computeCluster", uri(args.cluster_uri)),
             ("vivo:dateTimeValue", uri(date)), ("rm:runStatus", literal(s["status"])),
             ("rm:startTime", local(s["start_utc"])), ("rm:endTime", local(s["end_utc"])),
             ("prov:startedAtTime", local(s["start_utc"])), ("prov:endedAtTime", local(s["end_utc"])),
             ("rm:durationSeconds", literal(round(s["duration_seconds"]))),
             ("rm:durationCalculationMethod", literal("Slurm ElapsedRaw of the job (start to end). Display timestamps use Europe/Berlin.")),
             ("rm:cpuTimeSeconds", literal(s["cpu_seconds"])),
             ("rm:cpuTimeCalculationMethod", literal(f"Slurm TotalCPU of the job (user + system CPU time of all steps); {s['ncpus']} CPUs allocated{node_cpus}.")),
             ("rm:energyKWh", literal(s["energy_kwh"])), ("rm:energyCalculationMethod", literal(method)),
             ("rm:energyMetricSource", literal("Slurm acct_gather_energy/ipmi; Prometheus node_exporter and ipmi_exporter on the compute node")),
             ("rm:energyCalculationUsesFallbackEstimate", literal(False)),
             ("rm:resourceAccountingScope", literal(scope)),
             ("rm:resourceAccountingStartTime", local(s["start_utc"])), ("rm:resourceAccountingEndTime", local(s["end_utc"])),
             ("rm:executionHost", literal(s["node"])),
             ("rm:jobName", literal(f"{s['job_name']} (Slurm job {s['job_id']}, partition {s['partition']}, exit code {s['exit_code']})"))]
    if s["memory_peak_gb"] is not None:
        props += [("rm:memoryPeakGB", literal(s["memory_peak_gb"])),
                  ("rm:memoryCalculationMethod", literal(
                      "Peak memory: the largest resident memory (Slurm MaxRSS) of any job step, "
                      "converted from bytes to gigabytes (1 GB = 1,000,000,000 bytes). "
                      "No average memory: Slurm does not record memory use over time."))]
    node = s.get("node_info") or {}
    if node:
        require(node.get("hostname", s["node"]) == s["node"], "node-info.tsv was recorded on another node")
        if node.get("architecture"):
            hardware = node["architecture"]
            if node.get("cpu_model"):
                hardware += f"; {node.get('sockets', '?')} x {node['cpu_model']}"
            if node.get("node_cpus"):
                hardware += f"; {node['node_cpus']} hardware threads"
            props.append(("rm:architecture", literal(hardware)))
        if node.get("node_cpus"):
            props.append(("rm:allocatableCpu", literal(node["node_cpus"])))
        if node.get("memory_total_bytes"):
            props.append(("rm:allocatableMemoryGB", literal(int(node["memory_total_bytes"]) / 1e9)))
        if node.get("os"):
            props.append(("rm:osImage", literal(node["os"])))
        if node.get("kernel"):
            props.append(("rm:kernelVersion", literal(node["kernel"])))
    props += [("rm:gpuRequested", literal(s["gpu_requested"])), ("rm:gpuMetricsAvailable", literal(False)),
              ("rm:gpuUsageStatus", literal("GPU requested in Slurm allocation" if s["gpu_requested"] else "CPU-only job"))]
    trace_types = ["Slurm accounting (sacct)", "node CPU and IPMI power samples", "node hardware inventory"]
    nf_log = s.get("nextflow_log")
    if nf_log:
        props.append(("rm:workflowEngine", uri(BASE + "engine/nextflow")))
        if nf_log["version"]:
            props.append(("rm:nextflowVersion", literal(nf_log["version"])))
        if nf_log["session"]:
            props.append(("rm:nextflowSessionId", literal(nf_log["session"])))
        props += [("rm:containerImage", literal(image)) for image in nf_log["images"]]
        if nf_log["revision_name"]:
            props.append(("rm:codeVersion", literal(nf_log["revision_name"])))
        trace_types.append("Nextflow log")
    trace = s.get("nextflow_trace")
    processes = []
    if trace:
        status = trace["status"]
        props += [("rm:taskCount", literal(trace["tasks"])),
                  ("rm:succeededTaskCount", literal(status.get("COMPLETED", 0) + status.get("CACHED", 0))),
                  ("rm:cachedTaskCount", literal(status.get("CACHED", 0))),
                  ("rm:failedTaskCount", literal(status.get("FAILED", 0) + status.get("ABORTED", 0)))]
        trace_types.append("Nextflow task trace")
        for proc in trace["processes"]:
            slug = re.sub(r"[^a-z0-9]+", "-", proc["name"].lower()).strip("-")
            proc_uri = BASE + "process/" + key + "-" + slug
            props.append(("rm:hasWorkflowProcess", uri(proc_uri)))
            failed = proc["status"].get("FAILED", 0) + proc["status"].get("ABORTED", 0)
            predicates = [("rdf:type", "rm:WorkflowProcessRun"), ("rdf:type", "vivo:InformationResource"),
                          ("rdf:type", "prov:Entity"), ("rdfs:label", label(proc["name"])),
                          ("dcterms:title", label(proc["name"])), ("rm:taskName", literal(proc["name"])),
                          ("rm:isWorkflowProcessOf", uri(run)),
                          ("rm:runStatus", literal("Failed" if failed else "Succeeded")),
                          ("rm:taskCount", literal(proc["tasks"])),
                          ("rm:succeededTaskCount", literal(proc["status"].get("COMPLETED", 0) + proc["status"].get("CACHED", 0))),
                          ("rm:failedTaskCount", literal(failed)),
                          ("rm:cpuTimeSeconds", literal(proc["cpu"])),
                          ("rm:cpuTimeCalculationMethod", literal("Sum of Nextflow trace realtime x %cpu / 100 over the process's tasks."))]
            if proc["rss"] is not None:
                predicates.append(("rm:memoryPeakGB", literal(proc["rss"] / 1e9)))
            if proc["start"] is not None:
                predicates += [("prov:startedAtTime", local(datetime.fromtimestamp(proc["start"], UTC).isoformat())),
                               ("prov:endedAtTime", local(datetime.fromtimestamp(proc["end"], UTC).isoformat())),
                               ("rm:durationSeconds", literal(round(proc["end"] - proc["start"])))]
            processes.append((proc_uri, predicates))
    props += [("rm:traceTypes", literal("; ".join(trace_types))),
              ("rm:traceDataFormat", literal("TSV and plain text"))]
    carbon = s.get("carbon")
    if carbon:
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
                  ("rm:carbonCalculationMethod", literal(
                      "Estimated job energy in each covered hour (split by sampled node power) multiplied by that "
                      "hour's Germany grid intensity. Emissions basis: " + carbon["basis"] + "."))]
    if args.run_operator_uri:
        props.append(("rm:runOperator", uri(args.run_operator_uri)))
    if args.backend_uri:
        props.append(("rm:backend", uri(args.backend_uri)))
    props += [("rm:language", uri(language)) for language in args.language_uri]
    props += [("rm:inputData", uri(d)) for d in args.input_data_uri]
    if args.code_repo_url:
        props.append(("rm:workflowCodeLink", literal(args.code_repo_url, "xsd:anyURI")))
    commit = args.git_commit or (nf_log or {}).get("revision")
    if commit:
        props.append(("rm:gitCommit", literal(commit)))
        if args.code_repo_url:
            props.append(("rm:codeCommitLink", literal(args.code_repo_url.rstrip("/") + "/commit/" + commit, "xsd:anyURI")))
    if args.description:
        props.append(("dcterms:description", label(args.description)))
    add_resource(lines, uri(run), props)
    for proc_uri, predicates in processes:
        add_resource(lines, uri(proc_uri), predicates)
    add_resource(lines, uri(date), [("rdf:type", "vivo:DateTimeValue"), ("vivo:dateTime", local(s["start_utc"])),
                                    ("vivo:dateTimePrecision", "vivo:yearMonthDayTimePrecision")])
    workflow = [("rm:hasRun", uri(run)), ("rm:hasWorkflowRun", uri(run)), ("rm:computeCluster", uri(args.cluster_uri))]
    if args.workflow_label:
        workflow = [("rdf:type", "rm:Workflow"), ("rdf:type", "vivo:InformationResource"), ("rdf:type", "prov:Entity"),
                    ("rdfs:label", label(args.workflow_label)), ("dcterms:title", label(args.workflow_label)),
                    ("rm:workflowName", literal(args.workflow_label))] + workflow
    workflow += [("rm:responsibleResearcher", uri(r)) for r in args.responsible_researcher_uri]
    add_resource(lines, uri(args.workflow_uri), workflow)
    for researcher in args.responsible_researcher_uri:
        add_resource(lines, uri(researcher), [("rm:workflows", uri(args.workflow_uri))])
    # The cluster record already exists in VIVO; add links only, never a second label.
    add_resource(lines, uri(args.cluster_uri), [("rm:hasRun", uri(run)), ("rm:hasWorkflow", uri(args.workflow_uri))])
    for dataset in args.input_data_uri:
        # Link the dataset to this run only; workflow-level input data stays under curator control.
        add_resource(lines, uri(dataset), [("rm:usedByWorkflowRun", uri(run))])
    return "\n".join(lines), run


def absolute_uri(value, name):
    require(value.startswith(("http://", "https://")) and not re.search(r"[\s<>\"{}|^`\\]", value),
            f"{name} must be an absolute http(s) URI")
    require("REPLACE_ME" not in value, f"{name} still contains REPLACE_ME")
    return value


def build_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--job-id", required=True, help="Finished Slurm job ID")
    parser.add_argument("--evidence-dir", required=True, type=Path, help="Directory written by run-with-node-sampler.sh")
    parser.add_argument("--output-dir", required=True, type=Path, help="New directory for run.ttl and summary.json")
    parser.add_argument("--workflow-uri", required=True, help="VIVO workflow this run belongs to")
    parser.add_argument("--workflow-label", help="Only for a NEW workflow: its title (creates the workflow record)")
    parser.add_argument("--run-label", help="Run title prefix, normally the workflow title; defaults to the Slurm job name")
    parser.add_argument("--description", help="Optional run description")
    parser.add_argument("--responsible-researcher-uri", action="append", default=[],
                        help="VIVO person responsible for the workflow (repeatable)")
    parser.add_argument("--run-operator-uri", default=os.environ.get("RUN_OPERATOR_URI", ""),
                        help="VIVO person who ran the job (rm:runOperator, 'run by'); defaults to RUN_OPERATOR_URI")
    parser.add_argument("--cluster-uri", default=BASE + "cluster/hpc-hu-cluster")
    parser.add_argument("--backend-uri", default="http://172.28.33.178:8080/vivo/individual/n6167",
                        help="VIVO backend record (default: Slurm)")
    parser.add_argument("--language-uri", action="append", default=[],
                        help="VIVO language record, e.g. .../language/shell (repeatable)")
    parser.add_argument("--input-data-uri", action="append", default=[], help="VIVO input dataset record (repeatable)")
    parser.add_argument("--cluster-label", default="HPC@HU")
    parser.add_argument("--code-repo-url", help="Source repository URL (for the commit link)")
    parser.add_argument("--git-commit", help="Source commit of the code that ran")
    parser.add_argument("--nextflow-log", action="append", default=[], type=Path,
                        help="Candidate .nextflow.log files; the one written during the job is used (repeatable)")
    parser.add_argument("--nextflow-trace", action="append", default=[], type=Path,
                        help="Candidate Nextflow execution_trace files; the one matching the job is used (repeatable)")
    parser.add_argument("--timezone", default="Europe/Berlin", help="Time zone of sacct and Nextflow timestamps")
    parser.add_argument("--no-carbon", action="store_true", help="Do not look up grid carbon intensity")
    parser.add_argument("--sacct-file", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    absolute_uri(args.workflow_uri, "--workflow-uri")
    absolute_uri(args.cluster_uri, "--cluster-uri")
    for value, name in [(args.backend_uri, "--backend-uri"), *[(l, "--language-uri") for l in args.language_uri],
                        *[(d, "--input-data-uri") for d in args.input_data_uri]]:
        if value:
            absolute_uri(value, name)
    for researcher in args.responsible_researcher_uri:
        absolute_uri(researcher, "--responsible-researcher-uri")
    args.run_operator_uri = (args.run_operator_uri or "").strip()
    if not args.run_operator_uri or "REPLACE_ME" in args.run_operator_uri:
        print("WARNING: RUN_OPERATOR_URI / --run-operator-uri is empty; the run will be published "
              "without rm:runOperator (\"run by\").", file=sys.stderr)
        args.run_operator_uri = ""
    else:
        absolute_uri(args.run_operator_uri, "--run-operator-uri")
    return args


def main(argv=None):
    args = build_args(argv)
    require(not args.output_dir.exists(), "Output directory already exists; choose a new one")
    tz = ZoneInfo(args.timezone)
    job, steps = read_sacct(args.job_id, args.sacct_file)
    summary = summarize(job, steps, read_info(args.evidence_dir), read_samples(args.evidence_dir), tz)
    summary["node_info"] = read_node_info(args.evidence_dir)
    if not summary["node_info"]:
        print("WARNING: no node-info.tsv; node hardware is left out.", file=sys.stderr)
    start_ts = datetime.fromisoformat(summary["start_utc"]).timestamp()
    end_ts = datetime.fromisoformat(summary["end_utc"]).timestamp()
    summary["nextflow_log"] = read_nextflow_log(args.nextflow_log, start_ts, end_ts, tz) if args.nextflow_log else None
    summary["nextflow_trace"] = read_trace(args.nextflow_trace, start_ts, end_ts, tz) if args.nextflow_trace else None
    if args.nextflow_log and not summary["nextflow_log"]:
        print("WARNING: none of the given Nextflow logs was written during this job; engine details left out.", file=sys.stderr)
    if args.nextflow_trace and not summary["nextflow_trace"]:
        print("WARNING: none of the given Nextflow traces matches this job; process details left out.", file=sys.stderr)
    summary["carbon"] = None if args.no_carbon else fetch_carbon_optional(summary)
    ttl, run = build_ttl(summary, args, tz)
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "run.ttl").write_text(ttl + "\n")
    public = {k: v for k, v in summary.items() if k != "fraction"}
    if public["carbon"]:
        public["carbon"] = {k: v for k, v in public["carbon"].items() if k not in ("attempts",)}
    public["run_uri"] = run
    (args.output_dir / "summary.json").write_text(json.dumps(public, indent=2, default=str) + "\n")
    print(json.dumps({k: public[k] for k in ("status", "duration_seconds", "cpu_seconds", "cpu_share",
                                             "node_energy_joules", "energy_kwh", "run_uri")}, indent=2))
    print("TTL: " + str(args.output_dir / "run.ttl"))


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit("ERROR: " + str(exc))
