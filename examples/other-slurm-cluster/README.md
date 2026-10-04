# Connect another Slurm cluster to FONDA VIVO

For users of a Slurm cluster that is not connected yet (for example at TU
Berlin, FU Berlin or GFZ) who want their runs to appear in
[FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/runs).

**Every cluster gets its own collector.** A collector is the program that
reads a finished job, works out its time, CPU, memory and energy, writes the
run as a Turtle file (`run.ttl`) and sends it to VIVO. Clusters record jobs
and measure energy in different ways, so a collector is written for one
cluster only. Today there are two: one for the FONDA Kubernetes cluster and
one for [HPC@HU](../hpc-at-hu-slurm/README.md).

**The aim** is that the properties of a run in VIVO are read from the cluster
itself, as many as the cluster can give:

| Run property in VIVO | Where it can come from |
|---|---|
| Start, end, duration, status, CPU time | Slurm's job records |
| Peak and average memory | Slurm's job records; Slurm profiling for values over time |
| GPU requested, GPU use | Slurm's job records, GPU tools on the node |
| Energy | Slurm's own energy records, energy tools of the cluster, monitoring on the node (per job or per node), counters and sensors |
| Energy measurement coverage, node use | whether jobs share nodes, the job's part of its node, other jobs on the node |
| Execution host, CPU model, CPUs, memory, operating system, kernel | read on the node |
| Node temperature | sensors and monitoring on the node |
| Carbon emission and intensity | calculated from the energy; same on every cluster |
| Workflow engine and version, code version, container images, task count, workflow stages | the log and trace of Nextflow or Snakemake; same on every cluster |
| Run by, language, input data, code link | a settings file you fill in once; same on every cluster |

Which of these sources exist on your cluster is not known beforehand, and how
the connected clusters measure energy is not assumed for yours. So the cluster
is checked in two rounds before the collector is written:

| Stage | Who | What |
|---|---|---|
| A | you | First check: which sources exist on your cluster (steps 1 to 3). |
| B | VIVO administrator, then you | Second check: commands written for your cluster, which read the sources that were found (step 4). |
| C | VIVO administrator | Builds the collector for your cluster and writes its guide. |
| D | you | Set up and publish, following your cluster's own guide. |

**Contact:** Yagmur Kati, FONDA VIVO administrator,
[yagmur.kati@hu-berlin.de](mailto:yagmur.kati@hu-berlin.de).

Nothing has to be installed by an administrator of your cluster; everything
runs with your own account. Run all commands on the login node.

---

## A. First check: which sources exist

### 1. Download the publisher

Use a directory with enough space; home directories are often small.

```bash
export WORK=/path/to/your/work/directory
mkdir -p "$WORK" && cd "$WORK"
git clone https://github.com/YagmurKati/fonda-kubernetes-vivo-publisher.git
cd fonda-kubernetes-vivo-publisher
```

### 2. Run the first check

```bash
examples/other-slurm-cluster/check-cluster.sh
```

If your cluster needs a partition or an account for every job, add them:

```bash
examples/other-slurm-cluster/check-cluster.sh --partition=NAME --account=NAME
```

The script only reads: it changes nothing and sends nothing. It starts one
test job of about one minute (time limit: two minutes) and writes
`vivo-cluster-check-HOST-DATE.txt` in the current directory. The file contains
host names, Slurm settings, the names of monitoring services and metrics, node
hardware and the job IDs of your last jobs; no passwords, no file contents and
nothing about other users. Read it before you send it.

What it reports:

| Section | Question it answers |
|---|---|
| 1. Slurm settings | What does Slurm record for a job? Does it record energy, and from which source? |
| 2. Partitions | Node sizes, time limits, whether jobs share nodes. |
| 3. Your last jobs | What Slurm stored for them, and everything this Slurm can report for a job. |
| 4. Tools | Which job reports and energy tools does the cluster offer? |
| 5. Login node | Python version; does the login node reach VIVO? |
| 6. Compute node | Which monitoring runs on the node? Which power, energy and temperature values does it offer, and are they given per job? Which counters and sensors can you read? GPUs, hardware, operating system. How Slurm sees the test job. |
| 7. The test job | What Slurm recorded for it: time, CPU, memory, energy. |

### 3. Send this to the VIVO administrator

One e-mail with:

- the cluster name;
- the check file `vivo-cluster-check-....txt`, attached.

---

## B. Second check: read the sources that were found

### 4. Run the commands you receive

The first check shows which sources exist, not yet what they give for a job.
From your report the administrator writes a few commands for your cluster.
They read the sources found there, for one short test job, so that the values,
their units and whether they belong to the job or to the whole node can be
seen. You run them and send the output back.

This round is skipped if the first report already shows everything.

Other answers you may get instead:

| The first check shows | Answer |
|---|---|
| Monitoring runs on the node, but you cannot read it | One or two precise questions for your cluster support, which you pass on. |
| No energy source can be read with your account | Questions for your cluster support; or a collector without energy values, if that is still useful to you. |
| The login node does not reach VIVO (not `403`) | Ask your cluster support to allow outgoing HTTPS to `vivo-fonda.hu-berlin.de`. |
| No Python 3.9 or newer | Ask your cluster support for a Python module. |

---

## C. The collector for your cluster

Built by the administrator; nothing for you to do. When it is ready you
receive:

- the link to **your cluster's own folder** in this repository, with its
  guide;
- the right to publish for **your own VIVO account**. If you have no account
  yet, VIVO sends you an e-mail to set its password. Never share an account.

---

## D. Set up and publish

Follow your cluster's own guide. Steps 5 to 7 are the same on every cluster
and can be done while you wait.

### 5. Python

```bash
module load python/VERSION        # your cluster's module; skip if python3 is new enough
python3 --version                 # must be 3.9 or newer
```

### 6. Store your VIVO login

After you have set your VIVO password:

```bash
mkdir -p ~/.fonda-vivo && chmod 700 ~/.fonda-vivo
printf '%s' 'YOUR_VIVO_EMAIL' > ~/.fonda-vivo/email
```

Run the next line on its own. It shows `VIVO password:`; type or paste the
password and press Enter. Nothing is displayed.

```bash
read -rs -p 'VIVO password: ' p && printf '%s' "$p" > ~/.fonda-vivo/password; unset p; echo
chmod 600 ~/.fonda-vivo/*
```

### 7. Carbon values (optional)

Carbon emission is calculated the same way on every cluster: from the run's
energy and the German grid's hourly carbon intensity. It needs a free
[Electricity Maps](https://www.electricitymaps.com/) API token. Run the first
line on its own and paste the token at the prompt.

```bash
read -rs -p 'Electricity Maps token: ' t && printf '%s' "$t" > ~/.fonda-vivo/electricity-maps-token; unset t; echo
chmod 600 ~/.fonda-vivo/electricity-maps-token
curl -s -o /dev/null -w '%{http_code}\n' -H "auth-token: $(cat ~/.fonda-vivo/electricity-maps-token)" "https://api.electricitymaps.com/v4/carbon-intensity/latest?zone=DE"
```

The last line must print `200`. Without a token, runs are published without
carbon values. A cluster outside Germany: tell the administrator.

### 8 to 11. From your cluster's guide

| Step | What you do |
|---|---|
| 8. Run a job | As your cluster's guide describes. |
| 9. First run, without publishing | Collect the run as the guide describes, without sending it to VIVO. **Send the output to the administrator and wait for the go-ahead.** Later runs need no check. |
| 10. Publish | Send the run to VIVO. It ends with `HTTP 200` and the run's VIVO page. Publishing the same job again replaces the run; it does not create a second one. |
| 11. Remove a run | As the guide describes. |

---

## If something goes wrong

Send the administrator the command you ran and its full output. Never send
your password.

| Message | Cause and fix |
|---|---|
| The check's test job does not start | Add the options your cluster needs: `check-cluster.sh --partition=NAME --account=NAME`. |
| `No module named 'zoneinfo'` | Python is older than 3.9: load the Python module first. |
| `VIVO rejected the update with HTTP 403` | Wrong e-mail or password, or your account may not publish yet: ask the administrator. |
| `Disk quota exceeded` | Home directory full; free space there. The run records are small. |

## When you leave

Tell the administrator when you no longer publish from this cluster, so that
your VIVO account's publishing right is removed. Delete `~/.fonda-vivo` on the
cluster.

---

## For the VIVO administrator

1. **First report (step 3).** For every run property in the table at the top,
   note which source the report shows:
   - sections 1, 3 and 7: what Slurm records itself. Energy: `AcctGatherEnergyType`
     and `ConsumedEnergyRaw` of the test job. Values over time:
     `AcctGatherProfileType`. Whether the user sees other jobs: `PrivateData`.
   - section 4: job reports and energy tools the cluster offers;
   - section 6: monitoring services on the node, the metrics they offer and
     whether values carry a job label; counters and sensors the user can read;
     GPUs; whether the job shares its node (`OverSubscribe`, jobs on the node).
2. **Second check (step 4).** Write commands for that cluster which read what
   was found, for one short test job. Read each source once at the start and
   once at the end of the job, not in a loop.

   | Found in the first report | The second check reads |
   |---|---|
   | Slurm records energy | `sacct` and `sstat` energy of a job and of its steps; on a shared node, whether the value is the job's or the node's |
   | Slurm profiling | the profile of the test job (`sh5util`) |
   | An energy tool or job report (for example `eacct`, `jobstats`) | its report for the test job |
   | Metrics with a job label | the lines of the test job |
   | Power or energy of the whole node only (monitoring, sensors, counters) | the values, and what else ran on the node |
   | GPUs | power and use per GPU, and what Slurm records for them |
   | Monitoring that the user cannot read | a question for the cluster's support: can a user read the values of their own job, and how |

   Prefer a source that gives the energy of the job itself. A value for the
   whole node is only the job's when the job had the node to itself;
   otherwise it is a share.
3. Check the rest: Python and access to VIVO (section 5).
4. Build the collector for that cluster as its own file, with its own example
   folder, and keep the names in line:

   | | Pattern | Example |
   |---|---|---|
   | Collector | `collector/collect_<cluster>_slurm_job_metadata.py` | `collect_tu_berlin_slurm_job_metadata.py` |
   | Folder with the cluster's guide and examples | `examples/<cluster>-slurm/` | `examples/tu-berlin-slurm/` |
   | Start of every run address | `<cluster>-slurm-` | `tu-berlin-slurm-` |
   | Tests | `tests/test_<cluster>_slurm_collector.py` | `test_tu_berlin_slurm_collector.py` |

   Never change the start of the run addresses later: it is part of every
   published run of that cluster. The energy part is written for that
   cluster. Carbon values and publishing are the same on every cluster.
5. In VIVO, create the cluster page (class Compute Cluster).
6. Give the user's VIVO account the publishing right
   ([Administrator onboarding](../../docs/ADMIN_SETUP.md)). Record owner,
   cluster and date.
7. Send the user the link to the cluster's folder.
8. Review the user's first run before it is published (step 9): status,
   energy present and plausible, run address starts with the cluster's
   prefix. Then give the go-ahead.
9. After the first published run, open its page and the cluster page in VIVO.
10. Add the cluster to the list of collectors at the top of this guide.
