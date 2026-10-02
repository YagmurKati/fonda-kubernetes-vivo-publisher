# Connect HPC@HU to VIVO

One-time setup. Afterwards follow
[Collect and publish a run](COLLECT_AND_PUBLISH.md).

## You need

- an HPC@HU account ([HPC@HU service](https://ssc.berlin-university-alliance.de/en/shared-service/high-performance-computing-hpc/),
  [login instructions](https://wikis.hu-berlin.de/hpc/Erste_Verbindung/Einloggen));
- a VIVO account with the `UseSparqlUpdateApi` permission. Use an ordinary
  account, not a VIVO administrator
  ([Administrator onboarding](../../docs/ADMIN_SETUP.md));
- optional: an Electricity Maps API token, for carbon values.

## 1. Log in

```bash
ssh USER@HPC_LOGIN_HOST
```

All following commands run on the login node.

## 2. Check that the cluster reaches VIVO

```bash
curl -s -o /dev/null -w '%{http_code}\n' -m 15 -X POST https://vivo-fonda.hu-berlin.de/vivo/api/sparqlUpdate
srun -t 2 -n 1 curl -s -o /dev/null -w '%{http_code}\n' -m 15 -X POST https://vivo-fonda.hu-berlin.de/vivo/api/sparqlUpdate
```

Both must print `403`: VIVO answers and asks for a login. The first line tests
the login node, the second a compute node.

## 3. Check that the cluster measures energy

```bash
scontrol show config | grep AcctGatherEnergyType
srun -t 2 -n 1 bash -c 'for p in 9100 9290; do curl -s -m 3 -o /dev/null -w "port $p: %{http_code}\n" http://localhost:$p/metrics; done'
```

Expected:

```text
AcctGatherEnergyType    = acct_gather_energy/ipmi
port 9100: 200
port 9290: 200
```

Port 9100 is the node's CPU metrics, port 9290 its IPMI power.

## 4. Download the publisher

Use a directory on Lustre; the home directory quota is small.

```bash
export WORK=/lustre/GROUP/USER/fonda
mkdir -p "$WORK" && cd "$WORK"
git clone https://github.com/YagmurKati/fonda-kubernetes-vivo-publisher.git
cd fonda-kubernetes-vivo-publisher
```

## 5. Load Python and test

The system Python (3.6) is too old; the collector needs 3.9 or newer.

```bash
module load python/3.12.9-gcc14.2.0
python3 -m unittest tests.test_slurm_collector
```

The last line must be `OK`.

## 6. Store the VIVO login

```bash
mkdir -p ~/.fonda-vivo && chmod 700 ~/.fonda-vivo
printf '%s' 'YOUR_VIVO_EMAIL' > ~/.fonda-vivo/email
```

Run the next line on its own. It shows `VIVO password:`; type or paste the
password there and press Enter. Nothing is displayed.

```bash
read -rs -p 'VIVO password: ' p && printf '%s' "$p" > ~/.fonda-vivo/password; unset p; echo
```

## 7. Store the Electricity Maps token (optional)

Run the first line on its own and paste the token at the prompt.

```bash
read -rs -p 'Electricity Maps token: ' t && printf '%s' "$t" > ~/.fonda-vivo/electricity-maps-token; unset t; echo
curl -s -o /dev/null -w '%{http_code}\n' -H "auth-token: $(cat ~/.fonda-vivo/electricity-maps-token)" "https://api.electricitymaps.com/v4/carbon-intensity/latest?zone=DE"
```

The second line must print `200`. `401` means the token is wrong.

Without a token, runs are published without carbon values when no other
time-matched grid data is available.

## 8. Protect the files

```bash
chmod 600 ~/.fonda-vivo/*
```

The cluster is now connected. Continue with
[Collect and publish a run](COLLECT_AND_PUBLISH.md).
