# Security

## Credentials

- Never commit `config/publisher.env`, passwords, tokens, kubeconfigs, WireGuard
  files, private keys, or unreviewed generated TTL/audit/receipt files. A
  generated artifact may be checked in only as a deliberately documented public
  example after its content has been reviewed for credentials, private data,
  and internal infrastructure details.
- Use `scripts/configure-secrets.sh`; it accepts sensitive values through hidden
  prompts and stores them only in the selected Kubernetes namespace.
- Use a distinct non-admin VIVO publisher account per person or team. Never use
  the VIVO site administrator account in Kubernetes.
- Do not paste decoded Secrets into issues or support requests.

## Publishing authority

VIVO SPARQL Update is shared-database write access. The VIVO administrator must
approve, record, and revoke it. A successful HTTP response proves acceptance,
not scientific review of the metadata.

## Reporting

Report a vulnerability privately to the repository owner. Do not open a public
issue containing credentials, internal addresses, kubeconfigs, RDF with private
data, or unpublished research metadata.
