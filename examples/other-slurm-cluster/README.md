# Connect another Slurm cluster to FONDA VIVO

For users of a Slurm cluster that is not connected yet (for example at TU
Berlin, FU Berlin or GFZ) who want their runs to appear in
[FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/runs).

**Every cluster gets its own collector.** A collector is the program that
reads a finished job from Slurm, works out its time, CPU, memory and energy,
writes the run as a Turtle file (`run.ttl`) and sends it to VIVO. Clusters
measure energy in different ways, so a collector is written for one cluster
only. Today there are two: one for the FONDA Kubernetes cluster and one for
[HPC@HU](../hpc-at-hu-slurm/README.md).

So connecting a new cluster has three stages:

| Stage | Who | What |
|---|---|---|
| A | you | Check what your cluster offers and send the result (steps 1 to 4). |
| B | VIVO administrator | Builds the collector for your cluster and writes its guide. |
| C | you | Set up and publish, following your cluster's own guide. |

**Contact:** Yagmur Kati, FONDA VIVO administrator
([VIVO page](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=https%3A%2F%2Ffonda.hu-berlin.de%2F%3Fpage_id%3D2066%23YagmurKati)).
Below: "the administrator".

Nothing has to be installed by an administrator of your cluster; everything
runs with your own account. Run all commands on the login node.

---

## A. Check the cluster and ask for access

### 1. Download the publisher

Use a directory with enough space; home directories are often small.

```bash
export WORK=/path/to/your/work/directory
mkdir -p "$WORK" && cd "$WORK"
git clone https://github.com/YagmurKati/fonda-kubernetes-vivo-publisher.git
cd fonda-kubernetes-vivo-publisher
```

### 2. Run the cluster check

```bash
examples/other-slurm-cluster/check-cluster.sh
```

If your cluster needs a partition or an account for every job, add them:

```bash
examples/other-slurm-cluster/check-cluster.sh --partition=NAME --account=NAME
```

The script only reads: it changes nothing and sends nothing. It starts one
test job of at most two minutes and writes
`vivo-cluster-check-HOST-DATE.txt` in the current directory. The file contains
host names, Slurm settings, node hardware and the job IDs of your last jobs;
no passwords and no file contents. Read it before you send it.

What it reports:

| Section | Question it answers |
|---|---|
| 1. Slurm | Does Slurm record energy, and with which method (`AcctGatherEnergyType`)? |
| 2. Partitions | Node sizes, time limits, whether nodes are shared between jobs. |
| 3. Energy in accounting | Do your finished jobs have an energy value? |
| 4. Login node | Python version; does the login node reach VIVO? |
| 5. Compute node | Can power, CPU use and temperature be read on the node (exporters, RAPL)? Does the node reach VIVO? Hardware and operating system. |

### 3. Send this to the administrator

One e-mail with the check file attached and these lines filled in:

```text
Cluster
  name as it should appear in VIVO:
  institution:
  public web page of the cluster:
  how the cluster measures energy, if you know (or a contact at the computing centre):
Me
  name:
  institution:
  e-mail address for my VIVO account:
  my person page in VIVO (link), or "none":
  FONDA subproject or project:
Each workflow I want to publish
  title:
  code repository (link):
  started with: Nextflow / Snakemake / a script
  programming languages:
  input data (name and public link):
My jobs
  nodes per job:
  whole node or shared with other jobs:
  typical duration:
Publish automatically after each job: yes / no
Attached: vivo-cluster-check-....txt
```

### 4. Wait for the answer

The administrator reads the check file and answers with one of these:

| The check shows | Answer |
|---|---|
| Energy can be read (in Slurm, from exporters on the node, or from RAPL counters) | A collector for your cluster is built. You are told when it is on GitHub. |
| No energy source can be read with your account | Questions for your computing centre, which you pass on; or a collector without energy values, if that is still useful to you. |
| Login node does not reach VIVO (not `403`) | Ask your cluster support to allow outgoing HTTPS to `vivo-fonda.hu-berlin.de`. Until then runs can be sent from another computer; your cluster's guide will say how. |
| Compute nodes do not reach VIVO | Publishing by hand from the login node works; automatic publishing does not. |
| No Python 3.9 or newer | Ask your cluster support for a Python module. |

The administrator may ask you to run one or two further commands on the
cluster while the collector is being built.

---

## B. The collector for your cluster

Built by the administrator; nothing for you to do. When it is ready you
receive:

- the link to **your cluster's own folder** in this repository, with its
  guide, a settings template and a job example;
- an e-mail from VIVO to set the password of **your own VIVO account**. Never
  share an account;
- the values for your settings file: the VIVO pages of your cluster, of you
  ("run by"), of your workflows, languages and input data.

---

## C. Set up and publish

Follow your cluster's own guide. It has these parts; the first three are the
same on every cluster and can be done while you wait.

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

Carbon emission is calculated from the German grid's hourly carbon intensity
and needs a free [Electricity Maps](https://www.electricitymaps.com/) API
token. Run the first line on its own and paste the token at the prompt.

```bash
read -rs -p 'Electricity Maps token: ' t && printf '%s' "$t" > ~/.fonda-vivo/electricity-maps-token; unset t; echo
chmod 600 ~/.fonda-vivo/electricity-maps-token
curl -s -o /dev/null -w '%{http_code}\n' -H "auth-token: $(cat ~/.fonda-vivo/electricity-maps-token)" "https://api.electricitymaps.com/v4/carbon-intensity/latest?zone=DE"
```

The last line must print `200`. Without a token, runs are published without
carbon values. A cluster outside Germany: tell the administrator.

### 8 to 12. From your cluster's guide

| Step | What you do |
|---|---|
| 8. Settings file | Copy the template of your cluster's folder to `~/.fonda-vivo/` and fill in the values from the administrator. |
| 9. Job file | Start your command through the cluster's recording script, as in the job example. |
| 10. First run, without publishing | Run a job, then the publish script with `--dry-run`. **Send its output to the administrator and wait for the go-ahead.** Later runs need no check. |
| 11. Publish | Run the publish script with the job ID. It ends with `HTTP 200` and the run's VIVO page. Running it again replaces the run; it does not create a second one. |
| 12. Remove a run | The remove script of your cluster's folder, with the job ID. |

[HPC@HU](../hpc-at-hu-slurm/COLLECT_AND_PUBLISH.md) shows what these steps
look like for a connected cluster.

### 13. Publish automatically

The same on every cluster. Needs compute nodes that reach VIVO (cluster
check, section 5: `HTTP 403`).

Once:

```bash
cp "$WORK/fonda-kubernetes-vivo-publisher/examples/other-slurm-cluster/publish-after.sbatch.example" "$WORK/publish-after.sbatch"
```

Edit `$WORK/publish-after.sbatch`: set `PUBLISH_SCRIPT` to the publish script
of your cluster's folder, set the `module load` line, and add the partition or
account lines your cluster needs.

For every run, submit your job with:

```bash
cd "$WORK"
fonda-kubernetes-vivo-publisher/examples/other-slurm-cluster/submit-with-publish.sh my-job.sbatch publish-after.sbatch
```

This submits your job and a second, small job that starts when yours has
ended and publishes it. A failed run is published as failed. The output of
the publishing job, `slurm-<its job ID>.out`, ends with the run's VIVO page;
read it after your first automatic run.

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

When a request from step 3 arrives:

1. Read the check file and decide what the collector can use:
   - section 1 and 3: energy in Slurm accounting (`AcctGatherEnergyType`,
     `ConsumedEnergyRaw` of finished jobs);
   - section 5: `node_exporter` and `ipmi_exporter` on the node, RAPL
     counters readable by the user, temperature and fan sensors;
   - section 2: whether jobs share nodes (then a job's energy is a share of
     the node's);
   - section 4 and 5: whether login and compute nodes reach VIVO, Python.
2. Answer the user (step 4). Ask for further commands if something is
   unclear.
3. Build the collector for that cluster as its own file, with its own
   example folder, and keep the names in line:

   | | Pattern | Example |
   |---|---|---|
   | Collector | `collector/collect_<cluster>_slurm_job_metadata.py` | `collect_tu_berlin_slurm_job_metadata.py` |
   | Folder with guide, settings template, job example, publish and remove scripts | `examples/<cluster>-slurm/` | `examples/tu-berlin-slurm/` |
   | Start of every run address | `<cluster>-slurm-` | `tu-berlin-slurm-` |
   | Tests | `tests/test_<cluster>_slurm_collector.py` | `test_tu_berlin_slurm_collector.py` |

   Never change the start of the run addresses later: it is part of every
   published run of that cluster. The HPC@HU collector
   (`collector/collect_slurm_job_metadata.py`, `examples/hpc-at-hu-slurm/`)
   is the model to copy from.
4. In VIVO, create or choose the cluster page (class Compute Cluster), the
   user's person page, the workflow pages, and the language and input data
   pages.
5. Create the user's VIVO account and give it the publishing right
   ([Administrator onboarding](../../docs/ADMIN_SETUP.md)). Record owner,
   cluster and date.
6. Send the user the link to the cluster's folder and the settings values.
7. Review the dry-run output of the user's first run (step 10): status,
   energy present and plausible, run address starts with the cluster's
   prefix. Then give the go-ahead.
8. After the first published run, open its page and the cluster page in VIVO.
9. Add the cluster to the list of collectors at the top of this guide.
