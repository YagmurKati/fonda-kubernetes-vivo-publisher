#!/usr/bin/env bash
# Print the node's hardware and software as key<TAB>value lines.
# Called by run-with-node-sampler.sh. For a job that ran without it:
#   srun -w NODE collector/slurm/node-info.sh > EVIDENCE_DIR/node-info.tsv
lscpu_field() { lscpu 2>/dev/null | awk -F: -v k="$1" '$1 == k {gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit}'; }
printf 'hostname\t%s\n' "$(hostname -s)"
printf 'cpu_model\t%s\n' "$(lscpu_field 'Model name')"
printf 'node_cpus\t%s\n' "$(nproc --all 2>/dev/null)"
printf 'sockets\t%s\n' "$(lscpu_field 'Socket(s)')"
printf 'threads_per_core\t%s\n' "$(lscpu_field 'Thread(s) per core')"
printf 'architecture\t%s\n' "$(uname -m)"
printf 'memory_total_bytes\t%s\n' "$(awk '/^MemTotal:/ {printf "%.0f", $2 * 1024; exit}' /proc/meminfo 2>/dev/null)"
printf 'os\t%s\n' "$(. /etc/os-release 2>/dev/null && printf '%s' "$PRETTY_NAME")"
printf 'kernel\t%s\n' "$(uname -r)"
