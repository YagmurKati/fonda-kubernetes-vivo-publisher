#!/usr/bin/env bash
# Run a command inside a Slurm job while sampling the node's CPU use and power.
#
# Usage (inside an sbatch script):
#   collector/slurm/run-with-node-sampler.sh EVIDENCE_DIR -- COMMAND [ARGS...]
#
# Every SAMPLE_INTERVAL seconds (default 10) one line is appended to
# EVIDENCE_DIR/node-samples.tsv:
#   epoch_seconds  node_busy_cpu_seconds  node_cpu_count  node_power_watts
# read from the node's Prometheus exporters (node_exporter :9100 and
# ipmi_exporter :9290). The collector later uses these samples to give the job
# its CPU-time share of the node's IPMI energy. The command's exit status is
# returned unchanged.
set -uo pipefail

if [[ $# -lt 3 || "$2" != "--" ]]; then
  printf 'Usage: %s EVIDENCE_DIR -- COMMAND [ARGS...]\n' "$0" >&2
  exit 2
fi
EVIDENCE_DIR="$1"
shift 2

NODE_EXPORTER_URL="${NODE_EXPORTER_URL:-http://localhost:9100/metrics}"
IPMI_EXPORTER_URL="${IPMI_EXPORTER_URL:-http://localhost:9290/metrics}"
SAMPLE_INTERVAL="${SAMPLE_INTERVAL:-10}"

mkdir -p "$EVIDENCE_DIR"
SAMPLES="$EVIDENCE_DIR/node-samples.tsv"
if [[ -e "$SAMPLES" ]]; then
  printf 'ERROR: %s already exists; use a new evidence directory per run.\n' "$SAMPLES" >&2
  exit 2
fi

sample() {
  local now cpu power
  now="$(date +%s.%N)"
  cpu="$(curl -s -m 5 "$NODE_EXPORTER_URL" | awk '
    /^node_cpu_seconds_total\{/ {
      mode = $0; sub(/.*mode="/, "", mode); sub(/".*/, "", mode)
      cpu = $0; sub(/.*cpu="/, "", cpu); sub(/".*/, "", cpu)
      cpus[cpu] = 1
      if (mode != "idle" && mode != "iowait") busy += $NF
    }
    END { n = 0; for (c in cpus) n++; if (n) printf "%.3f\t%d", busy, n; else printf "NA\tNA" }')"
  power="$(curl -s -m 5 "$IPMI_EXPORTER_URL" | awk '
    /^ipmi_dcmi_power_consumption_watts / { dcmi = $NF }
    /^ipmi_power_watts\{/ { sensor = $NF }
    END { if (dcmi != "") print dcmi; else if (sensor != "") print sensor; else print "NA" }')"
  [[ -n "$cpu" ]] || cpu=$'NA\tNA'
  [[ -n "$power" ]] || power="NA"
  printf '%s\t%s\t%s\n' "$now" "$cpu" "$power" >> "$SAMPLES"
}

{
  printf 'slurm_job_id\t%s\n' "${SLURM_JOB_ID:-}"
  printf 'hostname\t%s\n' "$(hostname -s)"
  printf 'sample_interval_seconds\t%s\n' "$SAMPLE_INTERVAL"
  printf 'command_start_epoch\t%s\n' "$(date +%s.%N)"
} > "$EVIDENCE_DIR/job-info.tsv"
"$(dirname "$0")/node-info.sh" > "$EVIDENCE_DIR/node-info.tsv" 2>/dev/null || true

sample
( while sleep "$SAMPLE_INTERVAL"; do sample; done ) &
SAMPLER_PID=$!

"$@"
STATUS=$?

kill "$SAMPLER_PID" 2>/dev/null
wait "$SAMPLER_PID" 2>/dev/null
sample
{
  printf 'command_end_epoch\t%s\n' "$(date +%s.%N)"
  printf 'command_exit_status\t%s\n' "$STATUS"
} >> "$EVIDENCE_DIR/job-info.tsv"
exit "$STATUS"
