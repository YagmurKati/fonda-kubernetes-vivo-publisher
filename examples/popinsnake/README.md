# PopinSnake tested Snakemake profile

This is the fourth workflow integrated with the FONDA Kubernetes-to-VIVO
publisher. It targets the original
[FONDA A6 PopinSnake repository](https://gitlab.informatik.hu-berlin.de/fonda_a6/popinSnake)
at commit `359d94165dcd086adf0511598bf21102c7cf0e0c`.

## Verified workflow run

Run `popinsnake-example-20260828-02` completed in the `yagmur` namespace on
2026-08-28. The resumable session contains six isolated Kubernetes attempts:
five dependency/build compatibility attempts followed by one successful
attempt. Snakemake completed 48 of 48 rules. The final gzip-valid VCF contains
381 records for samples `S0001`, `S0002`, and `S0003`; its SHA-256 is
`170010db40798794dffa0506a2326b9777dbdba9bd2148ab9b572821e14753a2`.

An in-cluster dry run collected all six attempt Pods and validated the generated
VIVO Turtle without publishing it. The retained metrics reported 2,518.525
CPU-seconds, 4.600 GB peak memory, 0.025950 kWh, and 0.009524 kg CO2e. The
carbon value uses the latest available Electricity Maps factor at collection
time rather than a historical factor for the run interval.

The collector verifies the `RUN_STATUS` marker, reads the pinned workflow and
submodule revisions, validates and counts the final compressed VCF, inventories
result files, discovers the six terminal attempt Pods through read-only
namespace RBAC, and retrieves their retained Prometheus/Kepler metrics. It does
not rerun or modify the scientific workflow.

## Configure a fresh checkout

```bash
cp examples/popinsnake/publisher.env.example config/popinsnake.publisher.env
```

Replace the `REPLACE_ME` values. Store publisher credentials only in the
namespace Secret described in the user guide; never commit them.

## Collect and publish automatically

```bash
./scripts/collect-and-publish-popinsnake.sh popinsnake-example-20260828-02
```

That single command deploys the namespaced read-only collector, generates the
TTL and metrics audit under `RUN_ROOT/vivo-outbox`, sends only the TTL to VIVO,
and writes an HTTP publication receipt beside it. An existing receipt blocks a
duplicate publication.

Validate the full collection and RDF generation without contacting VIVO:

```bash
./scripts/collect-and-publish-popinsnake.sh popinsnake-example-20260828-02 --dry-run
```
