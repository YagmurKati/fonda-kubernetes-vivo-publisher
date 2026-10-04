#!/usr/bin/env bash
# Submit a job and, behind it, the job that publishes it to VIVO.
# Usage: submit-with-publish.sh RUN_JOB_FILE PUBLISH_JOB_FILE
#   RUN_JOB_FILE      your job, written as your cluster's own guide describes
#   PUBLISH_JOB_FILE  your copy of publish-after.sbatch.example
# The publishing job starts when the run has ended, whether it succeeded or
# not: a failed run is published as failed. Its output is in
# slurm-<publishing job ID>.out and ends with the run's VIVO page.
set -euo pipefail
if [[ $# -ne 2 ]]; then
  printf 'Usage: %s RUN_JOB_FILE PUBLISH_JOB_FILE\n' "$0" >&2
  exit 2
fi
run_id="$(sbatch --parsable "$1")"
run_id="${run_id%%;*}"
publish_id="$(sbatch --parsable --dependency="afterany:$run_id" --export="ALL,RUN_JOB_ID=$run_id" "$2")"
publish_id="${publish_id%%;*}"
printf 'Run job %s submitted.\n' "$run_id"
printf 'Publishing job %s starts when it has ended; output in slurm-%s.out\n' "$publish_id" "$publish_id"
