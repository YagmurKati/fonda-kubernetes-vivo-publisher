# A2 MG-4 tested Snakemake profile

This is the third workflow verified with the FONDA Kubernetes-to-VIVO
publisher. It targets the MG-4 metagenomic read-mapping workflow from
[CRC-FONDA/A2-job-granularity](https://github.com/CRC-FONDA/A2-job-granularity)
and deterministic simulated input from
[eseiler/raptor_data_simulation](https://github.com/eseiler/raptor_data_simulation).
The private companion reproduction repository is
[YagmurKati/a2-mg4-reproduction-example](https://github.com/YagmurKati/a2-mg4-reproduction-example)
and is available only to authorized collaborators.

MG-4 is a Snakemake workflow, so this profile uses the repository's dedicated
Kubernetes attempt adapter instead of the Nextflow trace adapter. The shared
RDF builder and VIVO publisher remain the same.

## Verified publication

Run `a2-mg4-smoke-20260826` completed on the FONDA cluster and was published
to VIVO with HTTP 200 on 2026-08-26. The collected session covers all six
resumable Kubernetes attempts because the successful sixth attempt reused
intermediates produced on the same PVC by the earlier attempts.

The published metadata reports:

- `Succeeded with warnings`: five earlier compatibility attempts failed and
  the sixth attempt completed successfully;
- 3,200 SAM records in the validated final output;
- 1,792.605 CPU-seconds and 8.349 GB peak memory;
- 0.012259 kWh energy;
- 0.002329 kg CO2e using the latest available Electricity Maps value as a
  collection-time proxy, not an exact historical factor.

The result is visible as the
[published VIVO run](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-metagenomic-read-mapping-with-customizable-job-granularity-a2-mg4-smoke-20260826-2026-08-26t11-10-52-00-00).
The HTTP 200 receipt, exact Turtle, and detailed metrics audit remain on the
workflow PVC because they contain local cluster paths and task-level query
evidence; implementation details live in the private reproduction repository.
No credentials, generated genomics data, internal addresses, or kubeconfig are
committed here.

## Configure

From the publisher repository:

```bash
cp examples/a2-mg4/publisher.env.example config/publisher.env
cp examples/a2-mg4/input_datasets.json config/input_datasets.json
```

The checked-in profile preserves the public workflow identity but uses
`REPLACE_ME` placeholders for namespace, PVC, Secret name, private paths,
selectors, Prometheus, and internal VIVO resources. Replace every placeholder
with values from your own authorized environment before deployment.

If the configured VIVO and Electricity Maps Secrets already exist, do not
replace them. Otherwise, create credentials through hidden prompts:

```bash
./scripts/configure-secrets.sh
```

## Validate without publishing

The tested run already has an HTTP 200 receipt, so use dry-run validation when
checking it again:

```bash
./scripts/publish-run.sh a2-mg4-smoke-20260826 --dry-run
```

This deploys only publisher-owned code, settings, and namespace-scoped
read-only Pod/Job RBAC, then collects fresh metadata without sending RDF to
VIVO. It does not alter or rerun any MG-4 scientific Job.

## Publish a new MG-4 run

After a new run has a successful attempt and the expected result/provenance
files on its PVC, apply the `fonda.hu-berlin.de/run-id` label to its Pods, then
run:

```bash
./scripts/publish-run.sh YOUR_NEW_RUN_ID
```

The publisher refuses a second non-dry-run publication when a receipt already
exists for the same run ID. `FORCE_REPUBLISH=1` is available only for a
deliberately reviewed correction. The regex fallback is restricted to the
tested historical run so a new run ID cannot accidentally reuse its six Pods.
