#!/bin/bash

set -euo pipefail
filename=$1
filename2=$2

while [[ ! -f /workspace/run/stop.signal ]] && (( SECONDS < 14400 ))
do
    cat /host-powercap/intel-rapl/intel-rapl:0/energy_uj >> $filename #package
    (date +"%H:%M:%S.%3N") >> $filename
    cat /host-powercap/intel-rapl/intel-rapl:0/intel-rapl:0:0/energy_uj >> $filename2 #DRAM
    (date +"%H:%M:%S.%3N") >> $filename2
    #sleep until next full second; copied from https://stackoverflow.com/questions/33204838/bash-command-wait-until-next-full-second
    sleep 0.$(printf '%04d' $((10000 - 10#$(date +%4N))))
done
# Retain the counters after the stop signal to bracket the execution interval.
cat /host-powercap/intel-rapl/intel-rapl:0/energy_uj >> "$filename"
date +"%H:%M:%S.%3N" >> "$filename"
cat /host-powercap/intel-rapl/intel-rapl:0/intel-rapl:0:0/energy_uj >> "$filename2"
date +"%H:%M:%S.%3N" >> "$filename2"
