set -euo pipefail
umask 002
cd /workspace/run
finish() {
    status=$?
    sleep 2
    date -u +%Y-%m-%dT%H:%M:%S.%NZ > stop.signal
    printf '%s\n' "$status" > driver-exit-code.txt
    exit "$status"
}
trap finish EXIT
for i in $(seq 1 120); do
    if [ -f /workspace/collector.ready ]; then break; fi
    sleep 1
done
test -f /workspace/collector.ready
nextflow -version > /workspace/provenance/nextflow-version.txt
nextflow -c /config/nextflow.config config /workspace/rnaseq-source -flat > /workspace/provenance/effective-nextflow.config
date -u +%Y-%m-%dT%H:%M:%S.%NZ > start.signal
for i in $(seq 1 60); do
    if [ -s /workspace/rapl/package-energy.txt ] && [ -s /workspace/rapl/dram-energy.txt ]; then break; fi
    sleep 1
done
test -s /workspace/rapl/package-energy.txt
test -s /workspace/rapl/dram-energy.txt
sleep 2
date -u +%Y-%m-%dT%H:%M:%S.%NZ > workflow-start.txt
nextflow run /workspace/rnaseq-source/main.nf -c /config/nextflow.config -name __RUN_NAME__ -ansi-log false -output-dir /workspace/results 2>&1 | tee workflow.log
date -u +%Y-%m-%dT%H:%M:%S.%NZ > workflow-end.txt
test -s /workspace/results/multiqc_report.html
printf '%s\n' 'Workflow outputs ready for read-only export and checksum verification.'
