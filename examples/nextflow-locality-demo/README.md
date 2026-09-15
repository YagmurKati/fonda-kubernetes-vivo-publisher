# Nextflow locality DSL2 demo test workflow

This profile executes and publishes the valid Nextflow DSL2 workflow in
[`tests/demo-dsl2.nf`](https://github.com/CRC-FONDA/nextflow_locality/blob/4343e333b749b748b57f65290443d2fc61c27b96/tests/demo-dsl2.nf)
from `CRC-FONDA/nextflow_locality`. The source is a test fixture, but it is an
executable workflow: it fans five greeting values into five `sayHello` tasks.

The tracked source copy has SHA-256
`f8e077dadb374bea484564aef5a96b4c7acb1ad2f13ff7b9393ae9a27d0e93c9`.
It is kept byte-for-byte equal to repository commit
`4343e333b749b748b57f65290443d2fc61c27b96`.

Published records:

- [Workflow in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Fworkflow%2Fnextflow-locality-dsl2-demo-test)
- [Successful run in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Ffonda-nextflow-locality-dsl2-demo-test-workflow-d21b12b9-b53a-491a-99f6-3e9f88e2137b-2026-09-15t08-18-38-764000-00-00)

## Attribution

The VIVO workflow is linked through `rm:responsibleResearcher` to Fabian
Lehmann and Friedrich Tschirpke and through `rm:subproject` to FONDA B5. These
are responsibility/stewardship links; the Git commit remains the source-code
provenance. No run-operator assertion is emitted.
`RUN_IDENTITY_SCOPE=fonda` also keeps the operational Kubernetes namespace out
of the public run and date IRIs.

## Cluster safety boundary

The run is deliberately small and sequential (`maxForks = 1`). The driver and
all five task pods carry both:

- `nodeSelector: usedby=prototyping`
- required node affinity for `usedby In [prototyping]`

`run-safely.sh` refuses to launch unless exactly three matching nodes are Ready
and schedulable. It watches only pods carrying the dedicated run label and
stops only those resources if any scheduled pod violates the boundary. The run
uses its own PVC, ConfigMap, Job, work directory, and results directory in the
`yagmur` namespace.

## Run

With the cluster VPN connected:

```bash
chmod +x examples/nextflow-locality-demo/run-safely.sh
examples/nextflow-locality-demo/run-safely.sh
```

The evidence is written to:

```text
/workspace/nextflow-locality-demo/results/NFL-DSL2-DEMO-RUN01/
```

## Collect and publish

Use `publisher.env.example` as the publisher configuration and the empty
`input_datasets.json` as input metadata. The workflow generates values
internally and reads no external dataset. Before publication, assert that the
generated Turtle contains exactly two `rm:responsibleResearcher` statements
and contains neither `rm:runOperator` nor a Yagmur Kati URI.

Missing Prometheus samples are allowed for this very short test fixture; all
available task metrics plus the complete structural trace metadata are kept.
The run uses the collector's documented fixed `0.4 kg CO2e/kWh` fallback
because same-day preliminary CO2Map data may not yet overlap such a recent,
short execution.

The dedicated publication path performs those assertions automatically and
keeps the generic publisher ConfigMaps untouched:

```bash
chmod +x examples/nextflow-locality-demo/publish-safely.sh
examples/nextflow-locality-demo/publish-safely.sh
```

The publisher pod is subject to the same duplicated hard prototyping-node
constraint as the workflow pods.
