# Administrator onboarding

Users do not need VIVO administrator accounts. They do need explicitly approved
API publishing access.

## One-time VIVO preparation

1. Confirm the FONDA run-metadata ontology and display configuration are already
   installed in VIVO.
2. Create or enable one ordinary VIVO account per user or responsible team.
3. Grant that account the `UseSparqlUpdateApi` permission used by the tested
   `/vivo/api/sparqlUpdate` endpoint. Do not grant site-administrator access.
4. Give the user only their own account activation/reset route. Never share a
   common publisher password across namespaces.
5. Record the account owner, Kubernetes namespace, date granted, and date
   revoked in the local administrator register.

Although the account is not a site administrator, SPARQL Update is privileged:
it can write to the shared VIVO ABox graph. Grant it only to identified FONDA
users and revoke it when the project or cluster access ends.

## User-specific metadata

Send the user the stable URIs they should place in `config/publisher.env`:

- their existing VIVO Person URI;
- the applicable FONDA Subproject URI;
- optional Application Domain, Backend, and Publication URIs.

Do not ask users to invent duplicate Person or Subproject resources.

## Kubernetes boundary

The repository creates only Secrets, ConfigMaps, Jobs, and—where a trace
adapter needs Kubernetes discovery—namespace-scoped read-only RBAC in the
user's own namespace. It does not require cluster administrator rights.

The collector attempts to read Kubernetes Node metadata. If the selected
service account cannot read Nodes, it logs a warning and omits node hardware
details; CPU, memory, Kepler energy, containers, timing, and publication still
work. Cluster-wide Node read access is optional and should be granted only
under the cluster's normal RBAC review.

## Acceptance test

Ask the user to publish a small completed run and provide only:

- the run ID;
- the `HTTP 200` line;
- the artifact filenames;
- the public VIVO run URL.

They must not send passwords, API tokens, decoded Secrets, or full Kubernetes
configuration files.

## Trace archives in the shared HU-Box folder

Members without an HU-Box account upload trace archives with `--shared-folder`
(see the [HU-Box trace archive guide](HU_BOX_TRACE_ARCHIVE.md#without-an-hu-box-account-the-shared-fonda-folder)).
The files arrive in the HU-Box folder "Traces of FONDA Workflows" of the
folder's owner and count against the owner's quota. Each archive comes with a
note file, `<archive>.run.json`, that names its run. An archive is not public
until its owner shares it; an upload link cannot do that.

The owner does this with one command, on a computer where
`./scripts/configure-hu-box.sh` was run with the library that holds the folder:

```bash
./scripts/link-shared-traces.sh --dry-run
./scripts/link-shared-traces.sh
```

The first command only lists the uploads. The second shows each archive and
its run, asks, creates the public HU-Box link of the file and adds it to the
run in VIVO (`rm:traceArchive`). It asks for the VIVO login once and skips

- archives that already have a public link;
- uploads whose run is not in VIVO;
- notes that do not fit their archive.

`--yes` does not ask. `--relink ARCHIVE` adds an existing link again, for
example after VIVO was not reachable. If the folder has another name or
place, set `HU_BOX_SHARED_DIR` in `config/hu-box.env`.

An archive that was uploaded in the browser has no note. Link it by hand:
create the share link of the file in HU-Box, then upload a file like this in
VIVO (Site Admin, Add/Remove RDF data, "add mixed RDF", Turtle):

```turtle
@prefix rm:  <http://example.org/ontology/run-metadata#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
<RUN_ADDRESS> rm:traceArchive "https://box.hu-berlin.de/f/REPLACE/"^^xsd:anyURI .
```

The upload link is public, so anyone can put files into the folder; nothing
becomes public without the owner's command. If the link is misused, delete it
in HU-Box under Share Admin, generate a new one for the folder and replace the
address in `publisher/upload_trace_archive.py` and in the HU-Box trace archive
guide.

## VIVO request-size limits

The VIVO SPARQL Update request passes through Nginx and Tomcat. If Nginx returns
`413 Request Entity Too Large`, an administrator must set an appropriate limit
inside the active HTTPS proxy `location` block, for example:

```nginx
client_max_body_size 25m;
```

Validate with `nginx -t` before reloading Nginx. The active Tomcat HTTP
Connector must also accept the form-encoded request, for example:

```xml
maxPostSize="26214400"
```

Use ordinary straight XML quotes and restart Tomcat after changing
`server.xml`. Keep both limits bounded; do not disable them globally. The
collector aggregates tagged task instances by process name, so tested Geoflow
and FORCE2NXF TTL files remain well below these limits.

## Revocation

1. Disable the user's VIVO API permission/account.
2. Ask the namespace owner to delete `fonda-vivo-credentials`.
3. Preserve published run records unless the user removed a selected
   publication with `scripts/remove-run.sh` or an administrator reviewed a
   run-scoped RDF deletion.
