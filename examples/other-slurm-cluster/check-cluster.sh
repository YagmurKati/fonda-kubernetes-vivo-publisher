#!/usr/bin/env bash
# Report what a Slurm cluster offers for publishing runs to FONDA VIVO.
#
# Run on the login node:
#   check-cluster.sh [SRUN OPTIONS...]
# for example
#   check-cluster.sh --partition=short --account=myproject
#
# The script only reads: it changes nothing on the cluster and sends nothing
# anywhere. It starts one test job of at most two minutes on a compute node.
# The report is shown and saved in the current directory as
#   vivo-cluster-check-HOST-DATE.txt
# It contains host names, Slurm settings, node hardware and the job IDs of
# your last jobs; no passwords and no file contents. Read it, then send it to
# the VIVO administrator.
set -u
export VIVO_ENDPOINT="${VIVO_ENDPOINT:-https://vivo-fonda.hu-berlin.de/vivo/api/sparqlUpdate}"
REPORT="vivo-cluster-check-$(hostname -s)-$(date +%Y%m%d-%H%M%S).txt"

section() { printf '\n== %s\n' "$1"; }
# Show a command and its output; a missing command is reported, not an error.
show() {
  printf '$ %s\n' "$*"
  if command -v "$1" >/dev/null 2>&1; then "$@" 2>&1 | sed 's/^/  /'; else printf '  (%s is not available)\n' "$1"; fi
}
http_code() { curl -s -o /dev/null -w '%{http_code}' -m 15 "$@" 2>/dev/null || true; }

# What is checked on a compute node. Kept in one function so that the same
# text can be sent to the test job.
node_checks() {
  printf 'node: %s\n' "$(hostname -s)"
  printf 'time zone: %s\n' "$(date '+%Z %z')"
  printf 'CPUs given to this test job: %s\n' "${SLURM_CPUS_ON_NODE:-unknown}"
  printf 'VIVO reachable from the node: HTTP %s (403 = yes)\n' \
    "$(curl -s -o /dev/null -w '%{http_code}' -m 15 -X POST "$VIVO_ENDPOINT" 2>/dev/null)"
  tmp="$(mktemp)"
  for exporter in "node_exporter http://localhost:9100/metrics" "ipmi_exporter http://localhost:9290/metrics"; do
    set -- $exporter
    code="$(curl -s -m 5 -o "$tmp" -w '%{http_code}' "$2" 2>/dev/null)"
    printf '%s at %s: HTTP %s\n' "$1" "$2" "${code:-000}"
    if [ "$code" = "200" ]; then
      printf '  node_cpu_seconds_total lines: %s\n' "$(grep -c '^node_cpu_seconds_total{' "$tmp")"
      printf '  power: %s\n' "$(grep -E '^ipmi_dcmi_power_consumption_watts |^ipmi_power_watts\{' "$tmp" | head -3 | tr '\n' ';')"
      printf '  temperature sensors: %s, fan sensors: %s\n' \
        "$(grep -c '^ipmi_temperature_celsius{' "$tmp")" "$(grep -c '^ipmi_fan_speed_rpm{' "$tmp")"
    fi
  done
  rm -f "$tmp"
  rapl_all=0; rapl_readable=0
  for f in /sys/class/powercap/intel-rapl*/energy_uj /sys/class/powercap/intel-rapl*/intel-rapl*/energy_uj; do
    [ -e "$f" ] || continue
    rapl_all=$((rapl_all + 1)); [ -r "$f" ] && rapl_readable=$((rapl_readable + 1))
  done
  printf 'RAPL energy counters: %s found, %s readable by you\n' "$rapl_all" "$rapl_readable"
  printf '/proc/stat readable: %s\n' "$([ -r /proc/stat ] && echo yes || echo no)"
  printf 'home directory writable from the node: %s\n' "$([ -w "$HOME" ] && echo yes || echo no)"
  for tool in python3 curl sacct ipmitool nvidia-smi nextflow snakemake apptainer singularity; do
    printf 'tool %s: %s\n' "$tool" "$(command -v "$tool" >/dev/null 2>&1 && echo yes || echo no)"
  done
  printf 'python3 on the node: %s\n' "$(python3 --version 2>&1)"
  lscpu 2>/dev/null | grep -E '^(Model name|Socket\(s\)|Core\(s\) per socket|Thread\(s\) per core|CPU\(s\)|Architecture):' | sed 's/  */ /g'
  printf 'memory: %s\n' "$(awk '/^MemTotal:/ {printf "%.1f GB", $2 / 1e6; exit}' /proc/meminfo 2>/dev/null)"
  printf 'operating system: %s\n' "$(. /etc/os-release 2>/dev/null && printf '%s' "$PRETTY_NAME")"
  printf 'kernel: %s\n' "$(uname -r)"
}

{
  printf 'Cluster check for FONDA VIVO\n'
  printf 'date: %s\n' "$(date '+%Y-%m-%d %H:%M %Z')"
  printf 'login node: %s\n' "$(hostname -s)"

  section "1. Slurm"
  show sinfo --version
  printf '$ scontrol show config (selected lines)\n'
  if command -v scontrol >/dev/null 2>&1; then
    scontrol show config 2>&1 | grep -E '^(ClusterName|AcctGatherEnergyType|AcctGatherNodeFreq|JobAcctGatherType|JobAcctGatherFrequency|AccountingStorageType|AccountingStorageTRES|SelectType|SelectTypeParameters|ProctrackType|TaskPlugin) ' | sed 's/^/  /'
  else
    printf '  (scontrol is not available)\n'
  fi

  section "2. Partitions (name|state|time limit|nodes|CPUs per node|memory MB|GPUs|node sharing)"
  show sinfo -o '%P|%a|%l|%D|%c|%m|%G|%h'

  section "3. Energy in Slurm accounting: your last finished jobs (job|elapsed|nodes|energy in joules)"
  printf '$ sacct -X -n -P -S now-30days -s CD -o JobID,Elapsed,NNodes,ConsumedEnergyRaw | tail -5\n'
  if command -v sacct >/dev/null 2>&1; then
    sacct -X -n -P -S now-30days -s CD -o JobID,Elapsed,NNodes,ConsumedEnergyRaw 2>&1 | tail -5 | sed 's/^/  /'
  else
    printf '  (sacct is not available)\n'
  fi
  printf '(an empty last column or 0 means Slurm records no energy)\n'

  section "4. Login node"
  printf 'time zone: %s\n' "$(date '+%Z %z')"
  show python3 --version
  printf '$ module avail python (first lines)\n'
  bash -lc 'if type module >/dev/null 2>&1; then module -t avail python 2>&1 | head -15; else echo "(no module system found)"; fi' 2>/dev/null | sed 's/^/  /'
  show git --version
  printf 'VIVO reachable from the login node: HTTP %s (403 = yes)\n' "$(http_code -X POST "$VIVO_ENDPOINT")"
  printf 'Electricity Maps reachable (carbon values): HTTP %s (any number except 000 = yes)\n' \
    "$(http_code 'https://api.electricitymaps.com/v4/carbon-intensity/latest?zone=DE')"

  section "5. Compute node (test job: srun $*)"
  if command -v srun >/dev/null 2>&1; then
    if ! { declare -f node_checks; echo node_checks; } | srun --time=2 --ntasks=1 "$@" bash -s 2>&1; then
      printf 'The test job did not run. Start the script again with the options your cluster needs,\n'
      printf 'for example: %s --partition=NAME --account=NAME\n' "$0"
    fi
  else
    printf '(srun is not available)\n'
  fi
  printf '\nEnd of report.\n'
} 2>&1 | tee "$REPORT"

printf '\nSaved as %s\n' "$REPORT"
