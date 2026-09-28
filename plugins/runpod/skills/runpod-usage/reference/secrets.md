---
concepts: [runpod-secret, pod, serverless-endpoint, template]
---

# Secrets

A Runpod **secret** stores a sensitive value, such as an API token or S3 key, in your
account. Pods, endpoints and templates reference it by name, so the plain value never
appears in their configuration.

## Use a secret

1. **Create it** with a `name` and `value`. REST: `POST /v2/account/secrets`.
   MCP: `create-secret`.
2. **Reference it** from an environment variable on a pod, endpoint or template by setting
   the variable's value to `{{ RUNPOD_SECRET_<name> }}`.
3. Runpod substitutes the stored value when the pod or worker boots.

## Rules to know

- **The value is write-only.** No API response or console page shows it after it is set,
  so keep your own copy if you will need it again.
- **Names are permanent and unique** in the account. A name is up to 191 characters,
  starts with a letter or underscore, and uses letters, digits and `_.-/`. Names that start
  with `runpod` in any letter case, such as `RUNPOD_TOKEN` or `RunpodKey`, are rejected.
- **Rotation takes effect at the next boot.** Running pods and workers keep the value they
  started with, so restart them after you change it.
- **Update the value and the description separately** when it matters. A `PATCH` that sends
  both applies the value first, so if the description update fails the new value is already
  live.
- **Deleting is permanent and is not blocked while the secret is in use.** Variables that
  reference it stop resolving, so update them first.

List secrets with `GET /v2/account/secrets` (MCP: `list-secrets`); each entry has an `id`,
`name` and timestamps but never the value. Change one with `PATCH /v2/account/secrets/{id}`
and delete it with `DELETE /v2/account/secrets/{id}`.

## Exact rules

These facts come from [`runpod-secret`](../concepts/runpod-secret.yaml), which cites the
REST v2 spec and the public docs. With the Runpod MCP server, read it with
`lookup-concept runpod-secret`.
