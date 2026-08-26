# FORCE2NXF tested profile

This profile targets
[CRC-FONDA/FORCE2NXF-Rangeland](https://github.com/CRC-FONDA/FORCE2NXF-Rangeland)
and the companion Kubernetes setup in
[YagmurKati/force2nxf-rangeland-vivo-metadata](https://github.com/YagmurKati/force2nxf-rangeland-vivo-metadata).

## Verified publication

Run `force2nxf-vivo-20260825-01-resume` completed on the FONDA cluster and was
published to VIVO with HTTP 200 on 2026-08-26. The published metadata reports:

- `Succeeded with warnings`: all workflow outputs completed, with 32 failed
  attempts recovered by Nextflow retries;
- 3,092 trace rows: 2,796 cached and 264 completed executions, plus the 32
  historical failed attempts;
- 2,302 seconds wall-clock duration;
- 0.917701 kWh measured/estimated Kepler energy;
- 0.247779 kg CO2e using the latest available Electricity Maps value as a
  collection-time proxy, not a historical whole-run measurement.

The exact published files are included for audit:

- [timestamped TTL](force2nxf-vivo-20260825-01-resume-20260826T085029Z.ttl)
- [HTTP 200 publication receipt](force2nxf-vivo-20260825-01-resume-20260826T085029Z.published.json)

The full task-level metrics audit is retained with the workflow artifacts but
is not committed because it contains detailed Kubernetes pod and query data.

## Configure

From the generic publisher repository:

```bash
cp examples/force2nxf/publisher.env.example config/publisher.env
cp examples/force2nxf/input_datasets.json config/input_datasets.json
```

Edit `config/publisher.env`. Replace every `REPLACE_ME` value and check its PVC
paths against your FORCE2NXF deployment. Then store the approved non-admin VIVO
account and optional Electricity Maps token:

```bash
./scripts/configure-secrets.sh
```

## Publish a completed FORCE2NXF run

```bash
INCLUDE_CACHED_ORIGIN_METRICS=1 \
  ./scripts/publish-run.sh YOUR_COMPLETED_RUN_ID
```

The cached-origin option is recommended for a resumed FORCE2NXF run. It can
recover CPU and energy measurements from the original pods only while those
measurements remain within Prometheus retention. The command does not run or
rerun FORCE2NXF.
