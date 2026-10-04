#!/usr/bin/env bash
# First check of a cluster: which sources exist for the properties of a run in
# VIVO (time, CPU, memory, GPU, energy, node use, node hardware).
#
# Run where you submit your jobs (the login node; for Kubernetes, where you
# use kubectl):
#   check-cluster.sh
# Slurm only: options your cluster needs for every job can be added, for example
#   check-cluster.sh --partition=short --account=myproject
#
# The script finds out which scheduler the cluster uses. Nothing else about the
# cluster is assumed: it looks for what is there and reports it.
#   Slurm         complete check, with one test job on a compute node. The job
#                 waits until it is about one minute old (time limit: two
#                 minutes), so that the report shows what is recorded for a job.
#   Kubernetes    version, rights of your account, names of monitoring
#                 services. No test job.
#   PBS, LSF, Grid Engine, HTCondor
#                 scheduler and version, and the login node. No test job.
# For every scheduler except Slurm, the VIVO administrator prepares the check
# of the scheduler and of a compute node from this report.
#
# The script only reads. It changes nothing on the cluster and sends nothing
# anywhere. The report is shown and saved in the current directory as
#   vivo-cluster-check-HOST-DATE.txt
# It contains host names, scheduler settings, the names of monitoring services
# and metrics, node hardware and the job IDs of your last jobs; no passwords,
# no file contents and nothing about other users. Read it, then send it to the
# VIVO administrator.
set -u
export VIVO_ENDPOINT="${VIVO_ENDPOINT:-https://vivo-fonda.hu-berlin.de/vivo/api/sparqlUpdate}"
# Age in seconds the Slurm test job reaches before its last readings.
export VIVO_CHECK_SECONDS="${VIVO_CHECK_SECONDS:-45}"
REPORT="vivo-cluster-check-$(hostname -s)-$(date +%Y%m%d-%H%M%S).txt"

section() { printf '\n== %s\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }
yes_no() { if "$@" >/dev/null 2>&1; then echo yes; else echo no; fi; }
# Show a command and its output; a missing command is reported, not an error.
show() {
  printf '$ %s\n' "$*"
  if have "$1"; then "$@" 2>&1 | sed 's/^/  /'; else printf '  (%s is not available)\n' "$1"; fi
}
http_code() { curl -s -o /dev/null -w '%{http_code}' -m 15 "$@" 2>/dev/null || true; }
tools() {
  for tool in "$@"; do printf '%s: %s\n' "$tool" "$(yes_no command -v "$tool")"; done
}
# Sum of the readable RAPL package counters, in microjoules.
rapl_sum() {
  total=0; found=0
  for f in /sys/class/powercap/intel-rapl:[0-9]*/energy_uj; do
    [ -r "$f" ] || continue
    case "$f" in */intel-rapl:*:*/energy_uj) continue ;; esac
    total=$((total + $(cat "$f"))); found=1
  done
  [ "$found" = 1 ] && echo "$total"
}

# ---------------------------------------------------------------------------
# Node part: the same for every scheduler. What can be read on a node.
# ---------------------------------------------------------------------------
node_checks() {
  printf 'node: %s\n' "$(hostname -s)"
  printf 'time zone: %s\n' "$(date '+%Z %z')"
  printf 'VIVO reachable from this node: HTTP %s (403 = yes)\n' \
    "$(curl -s -o /dev/null -w '%{http_code}' -m 15 -X POST "$VIVO_ENDPOINT" 2>/dev/null)"

  printf '\n-- monitoring services running on the node (names only)\n'
  ps -e -o comm= 2>/dev/null | sort -u \
    | grep -E '^(.*_exporter|.*-exporter|prometheus.*|telegraf|collectd|gmond|netdata|cc-metric.*|influxd|zabbix_agent.*|eard|ldmsd|pmcd|pmlogger|dcdbpusher|collectl|sadc|atop|slurmd|pbs_mom|kubelet)$' \
    | sed 's/^/  /' | grep . || printf '  (none of the known names)\n'

  printf '\n-- metrics offered on the node (Prometheus format), read once; HTTP 000 = nothing on that port\n'
  tmp="$(mktemp)"
  for port in 9100 9290 9306 9256 9400 9835 9103 9273 8080; do
    code="$(curl -s -m 5 -o "$tmp" -w '%{http_code}' "http://localhost:$port/metrics" 2>/dev/null)"
    printf 'port %s: HTTP %s\n' "$port" "${code:-000}"
    [ "$code" = "200" ] || continue
    printf '  metric names in total: %s\n' "$(grep -cE '^# TYPE ' "$tmp")"
    printf '  about power, energy, temperature, jobs:\n'
    grep -E '^# TYPE ' "$tmp" | awk '{print $3}' \
      | grep -iE 'power|energy|watt|joule|rapl|temp|fan|cgroup|slurm|pbs|job|pod|gpu' | head -40 | sed 's/^/    /'
    printf '  CPU time per mode (node_cpu_seconds_total): %s\n' "$(yes_no grep -q '^node_cpu_seconds_total{' "$tmp")"
    printf '  values labelled with a job: %s\n' "$(yes_no grep -qiE 'job_?id="|jobid="|slurm_job|pod="' "$tmp")"
  done
  rm -f "$tmp"

  printf '\n-- energy counters and sensors on the node\n'
  rapl_all=0; rapl_readable=0; rapl_names=""
  for f in /sys/class/powercap/intel-rapl:*/energy_uj; do
    [ -e "$f" ] || continue
    rapl_all=$((rapl_all + 1)); [ -r "$f" ] && rapl_readable=$((rapl_readable + 1))
    rapl_names="$rapl_names $(cat "$(dirname "$f")/name" 2>/dev/null)"
  done
  printf 'RAPL energy counters: %s found, %s readable by you (%s)\n' "$rapl_all" "$rapl_readable" \
    "$(printf '%s' "$rapl_names" | tr ' ' '\n' | sort -u | tr '\n' ' ' | sed 's/^ //; s/ $//')"
  hwmon=0
  for f in /sys/class/hwmon/hwmon*/power*_input /sys/class/hwmon/hwmon*/energy*_input; do [ -r "$f" ] && hwmon=$((hwmon + 1)); done
  printf 'hwmon power or energy sensors readable by you: %s\n' "$hwmon"
  temps=0
  for f in /sys/class/hwmon/hwmon*/temp*_input; do [ -r "$f" ] && temps=$((temps + 1)); done
  printf 'hwmon temperature sensors readable by you: %s\n' "$temps"
  printf 'IPMI device present: %s, readable by you: %s\n' \
    "$(yes_no test -e /dev/ipmi0)" "$(yes_no test -r /dev/ipmi0)"
  printf 'perf_event_paranoid: %s\n' "$(cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo unknown)"
  if command -v nvidia-smi >/dev/null 2>&1; then
    printf 'GPUs (name, power draw):\n'
    nvidia-smi --query-gpu=name,power.draw --format=csv,noheader 2>&1 | head -4 | sed 's/^/  /'
  else
    printf 'GPUs: nvidia-smi is not available\n'
  fi

  printf '\n-- processes on the node\n'
  printf 'cgroup of this check:\n'
  head -3 /proc/self/cgroup 2>/dev/null | sed 's/^/  /'
  printf '/proc/stat readable: %s\n' "$(yes_no test -r /proc/stat)"
  printf 'home directory writable from the node: %s\n' "$(yes_no test -w "$HOME")"

  printf '\n-- tools on the node\n'
  for tool in python3 curl ipmitool likwid-powermeter perf nextflow snakemake apptainer singularity docker podman; do
    printf '%s: %s\n' "$tool" "$(yes_no command -v "$tool")"
  done
  printf 'python3 on the node: %s\n' "$(python3 --version 2>&1)"

  printf '\n-- hardware and system\n'
  lscpu 2>/dev/null | grep -E '^(Model name|Socket\(s\)|Core\(s\) per socket|Thread\(s\) per core|CPU\(s\)|Architecture):' | sed 's/  */ /g'
  printf 'memory: %s\n' "$(awk '/^MemTotal:/ {printf "%.1f GB", $2 / 1e6; exit}' /proc/meminfo 2>/dev/null)"
  printf 'operating system: %s\n' "$(. /etc/os-release 2>/dev/null && printf '%s' "$PRETTY_NAME")"
  printf 'kernel: %s\n' "$(uname -r)"
}

# ---------------------------------------------------------------------------
# Scheduler part: Slurm.
# ---------------------------------------------------------------------------
# Runs inside the test job on a compute node.
slurm_test_job() {
  started=$SECONDS; rapl_start="$(rapl_sum)"
  slurm_node="${SLURMD_NODENAME:-$(hostname -s)}"
  printf 'test job ID: %s\n' "${SLURM_JOB_ID:-unknown}"
  printf 'CPUs given to this test job: %s\n' "${SLURM_CPUS_ON_NODE:-unknown}"
  node_checks

  printf '\n-- what Slurm knows about this node (power and energy fields)\n'
  if command -v scontrol >/dev/null 2>&1; then
    scontrol show node "$slurm_node" 2>/dev/null \
      | grep -oE '(CurrentWatts|AveWatts|LowestJoules|ConsumedJoules|ExtSensors[A-Za-z]+|Gres|CPUTot|ThreadsPerCore)=[^ ]+' \
      | sed 's/^/  /'
  else
    printf '  (scontrol is not available on the node)\n'
  fi

  printf '\n-- the test job as Slurm sees it\n'
  if command -v scontrol >/dev/null 2>&1 && [ -n "${SLURM_JOB_ID:-}" ]; then
    scontrol show job "$SLURM_JOB_ID" 2>/dev/null \
      | grep -oE '(Partition|NumNodes|NumCPUs|NumTasks|OverSubscribe|ReqTRES|AllocTRES|TRES|MinMemoryCPU|MinMemoryNode|TresPerNode)=[^ ]+' \
      | sed 's/^/  /'
  fi
  if command -v squeue >/dev/null 2>&1; then
    printf 'jobs on this node that you can see (number only, this test job included): %s\n' \
      "$(squeue -h -w "$slurm_node" -o %i 2>/dev/null | sort -u | wc -l)"
  fi

  printf '\n-- readings when the test job is %s seconds old\n' "$VIVO_CHECK_SECONDS"
  while [ $((SECONDS - started)) -lt "$VIVO_CHECK_SECONDS" ]; do sleep 5; done
  rapl_end="$(rapl_sum)"
  if [ -n "$rapl_start" ] && [ -n "$rapl_end" ]; then
    printf 'RAPL package counters over %s s: %s J (CPUs of the whole node; a negative number means the counter wrapped)\n' \
      "$((SECONDS - started))" "$(( (rapl_end - rapl_start) / 1000000 ))"
  else
    printf 'RAPL package counters: not readable\n'
  fi
  if command -v sstat >/dev/null 2>&1 && [ -n "${SLURM_JOB_ID:-}" ]; then
    printf 'what Slurm reports for the running job (sstat):\n'
    sstat -P -j "$SLURM_JOB_ID.${SLURM_STEP_ID:-0}" -o JobID,AveCPU,MaxRSS,AveRSS,ConsumedEnergyRaw,AveCPUFreq 2>&1 | sed 's/^/  /'
  else
    printf 'sstat is not available on the node\n'
  fi
}

slurm_part() {
  section "4. Slurm: accounting, energy and profiling settings"
  printf '$ scontrol show config (selected lines)\n'
  if have scontrol; then
    scontrol show config 2>&1 | grep -E '^(ClusterName|AccountingStorageType|AccountingStorageTRES|JobAcctGatherType|JobAcctGatherFrequency|AcctGatherEnergyType|AcctGatherNodeFreq|AcctGatherProfileType|AcctGatherInterconnectType|AcctGatherFilesystemType|JobAcctGatherParams|JobCompType|SelectType|SelectTypeParameters|ProctrackType|TaskPlugin|PrivateData) ' | sed 's/^/  /'
  else
    printf '  (scontrol is not available)\n'
  fi

  section "5. Slurm: partitions (name|state|time limit|nodes|CPUs per node|memory MB|GPUs|node sharing)"
  show sinfo -o '%P|%a|%l|%D|%c|%m|%G|%h'

  section "6. Slurm: your last finished jobs (job|elapsed|nodes|CPU time|peak memory|energy in joules)"
  printf '$ sacct -n -P -S now-30days -s CD -o JobID,Elapsed,NNodes,TotalCPU,MaxRSS,ConsumedEnergyRaw | tail -8\n'
  if have sacct; then
    sacct -n -P -S now-30days -s CD -o JobID,Elapsed,NNodes,TotalCPU,MaxRSS,ConsumedEnergyRaw 2>&1 | tail -8 | sed 's/^/  /'
    printf '(an empty last column or 0 means Slurm recorded no energy for the job)\n'
    printf '$ sacct --helpformat (everything this Slurm can report for a job)\n'
    sacct --helpformat 2>&1 | tr -s ' \n' ' ' | fold -s -w 100 | sed 's/^/  /'; printf '\n'
  else
    printf '  (sacct is not available)\n'
  fi

  section "7. Compute node (test job: srun $*)"
  test_job=""
  if have srun; then
    node_report="$(mktemp)"; set -o pipefail
    if ! { declare -f yes_no rapl_sum node_checks slurm_test_job; echo slurm_test_job; } \
        | srun --time=2 --ntasks=1 "$@" bash -s 2>&1 | tee "$node_report"; then
      printf 'The test job did not run. Start the script again with the options your cluster needs,\n'
      printf 'for example: %s --partition=NAME --account=NAME\n' "$0"
    fi
    set +o pipefail
    test_job="$(sed -n 's/^test job ID: \([0-9][0-9]*\)$/\1/p' "$node_report" | head -1)"
    rm -f "$node_report"
  else
    printf '(srun is not available)\n'
  fi

  section "8. Slurm: what was recorded for the test job"
  if [ -n "$test_job" ] && have sacct; then
    fields=JobID,State,Start,End,ElapsedRaw,AllocCPUS,NNodes,NodeList,TotalCPU,MaxRSS,AveRSS,ConsumedEnergyRaw,AllocTRES,TRESUsageInTot
    printf '$ sacct -P -j %s -o %s\n' "$test_job" "$fields"
    for attempt in 1 2 3 4; do
      recorded="$(sacct -P -j "$test_job" -o "$fields" 2>&1)"
      printf '%s\n' "$recorded" | grep -qE 'COMPLETED|FAILED|CANCELLED|TIMEOUT' && break
      sleep 5
    done
    printf '%s\n' "$recorded" | sed 's/^/  /'
  else
    printf '(no test job to look up)\n'
  fi
}

# ---------------------------------------------------------------------------
# Scheduler part: Kubernetes. The rights of your account, and which monitoring
# services exist. Read-only requests.
# ---------------------------------------------------------------------------
kubernetes_part() {
  section "4. Kubernetes: rights of your account (asked only; nothing is created)"
  for what in "list nodes" "list pods" "list pods --all-namespaces" "list services --all-namespaces" "create jobs.batch"; do
    # shellcheck disable=SC2086
    printf 'may %s: %s\n' "$what" "$(kubectl auth can-i $what --request-timeout=10s 2>&1 | head -1)"
  done
  section "5. Kubernetes: monitoring services (namespace/name, names only)"
  kubectl get services --all-namespaces --request-timeout=15s --no-headers \
      -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name 2>&1 \
    | grep -iE 'prometheus|thanos|victoria|grafana|exporter|kepler|scaphandre|metrics|dcgm|error|forbidden|refused' \
    | awk '{ if (NF == 2) print "  " $1 "/" $2; else print "  " $0 }' | head -40 | grep . \
    || printf '  (none found, or your account may not list services)\n'
}

# ---------------------------------------------------------------------------
# Every other scheduler: no ready check. Report which commands exist and check
# this node, so that the check for that scheduler can be prepared.
# ---------------------------------------------------------------------------
other_scheduler_part() {
  section "4. Scheduler commands on this node"
  tools qsub qstat qdel pbsnodes tracejob qmgr qacct qhost qconf bsub bjobs bhist bacct lsload \
        condor_submit condor_q condor_history condor_status flux oarsub
  printf '\nThere is no ready check for this scheduler yet. The VIVO administrator prepares\n'
  printf 'it from this report: the scheduler and a compute node are checked in a second round.\n'

  section "5. This node (the login node; compute nodes can differ)"
  node_checks
}

{
  printf 'Cluster check for FONDA VIVO\n'
  printf 'date: %s\n' "$(date '+%Y-%m-%d %H:%M %Z')"
  printf 'run on: %s\n' "$(hostname -s)"

  section "1. Scheduler"
  schedulers=""
  if have sinfo || have sbatch; then
    schedulers="$schedulers slurm"
    printf 'found: Slurm (%s)\n' "$(sinfo --version 2>&1 | head -1)"
  fi
  if have pbsnodes || { have qstat && ! have qconf; }; then
    schedulers="$schedulers pbs"
    printf 'found: PBS or Torque (%s)\n' "$(qstat --version 2>&1 | head -1)"
  fi
  if have qconf; then
    schedulers="$schedulers gridengine"
    printf 'found: Grid Engine (%s)\n' "$(qstat -help 2>&1 | head -1)"
  fi
  if have bsub && have lsid; then
    schedulers="$schedulers lsf"
    printf 'found: LSF (%s)\n' "$(lsid 2>&1 | head -1)"
  fi
  if have condor_q; then
    schedulers="$schedulers htcondor"
    printf 'found: HTCondor (%s)\n' "$(condor_version 2>&1 | head -1)"
  fi
  if have kubectl; then
    schedulers="$schedulers kubernetes"
    printf 'found: Kubernetes\n'
    kubectl version --request-timeout=10s 2>&1 | grep -iE 'version|error|refused|unable' | head -4 | sed 's/^/  /'
  fi
  if [ -z "$schedulers" ]; then
    printf 'found: none of Slurm, PBS, Torque, Grid Engine, LSF, HTCondor, Kubernetes.\n'
    printf 'Write in your e-mail how you submit jobs on this cluster.\n'
  fi

  section "2. Where you submit jobs (this node)"
  printf 'time zone: %s\n' "$(date '+%Z %z')"
  show python3 --version
  printf '$ module avail python (first lines)\n'
  bash -lc 'if type module >/dev/null 2>&1; then module -t avail python 2>&1 | head -15; else echo "(no module system found)"; fi' 2>/dev/null | sed 's/^/  /'
  show git --version
  printf 'VIVO reachable from here: HTTP %s (403 = yes)\n' "$(http_code -X POST "$VIVO_ENDPOINT")"
  printf 'Electricity Maps reachable (carbon values): HTTP %s (any number except 000 = yes)\n' \
    "$(http_code 'https://api.electricitymaps.com/v4/carbon-intensity/latest?zone=DE')"

  section "3. Job reports and energy tools offered here"
  tools seff eacct jobstats reportseff sh5util likwid-powermeter ipmitool
  printf '$ module avail (energy and monitoring tools)\n'
  bash -lc 'if type module >/dev/null 2>&1; then module -t avail 2>&1 | grep -iE "likwid|^ear|/ear|papi|geopm|variorum|energy|power|jobstats|cockpit|scorep" | head -20; else echo "(no module system found)"; fi' 2>/dev/null | sed 's/^/  /'

  case "$schedulers" in
    *slurm*) slurm_part "$@" ;;
    *pbs*|*gridengine*|*lsf*|*htcondor*) other_scheduler_part ;;
    *kubernetes*) kubernetes_part ;;
    *) other_scheduler_part ;;
  esac
  printf '\nEnd of report.\n'
} 2>&1 | tee "$REPORT"

printf '\nSaved as %s\n' "$REPORT"
