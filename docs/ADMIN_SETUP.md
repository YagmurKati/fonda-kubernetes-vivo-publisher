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

The repository creates only Secrets, ConfigMaps, and Jobs in the user's own
namespace. It does not require cluster administrator rights.

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
3. Preserve published run records unless a documented RDF deletion has been
   reviewed.
