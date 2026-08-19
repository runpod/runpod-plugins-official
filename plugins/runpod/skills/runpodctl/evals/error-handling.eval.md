# Handle a runpodctl failure without parsing message text

## Prompt

I'm scripting `runpodctl` in a loop. Write the failure handling: how do I tell a
missing endpoint from a bad API key from a blip I should retry? Here are two failures
I've seen:

```
{"error":"failed to get endpoint: endpoint not found","code":"not_found","status":404}
{"error":"failed to get template: template not found: tpl-abc","code":"not_found"}
```

## Expected behavior

The agent should:

1. Branch on `code`, not on `status` and not on substrings of `error`
2. Explain that the second failure has no `status` because GraphQL answers a missing
   resource with HTTP 200 + null data, so `status === 404` misses it
3. Retry `network_error`, `rate_limited` and `server_error` with backoff, and say why
   `cli_error` (e.g. a malformed `RUNPOD_API_URL`) must not be
4. Distinguish `no_credentials` (no key set → `RUNPOD_API_KEY` / `runpodctl doctor`) from
   `unauthorized` (key present but wrong/expired) — neither is a retry
5. Treat `not_found` as server-side, not as a mistyped local path
6. Gate on a non-zero exit code and read errors from **stderr**, data from stdout — and
   not treat a `warning:`/`note:` line on stderr as a failure
7. Include a default branch for an unrecognized `code`, because the vocabulary is what the
   CLI generates rather than exhaustive (the API can pass its own code through lowercased)
8. Not retry `timeout` / `wait_timeout` / `wait_interrupted` / `job_failed` (v2.9.0+): each
   means work or a resource outlived the CLI, so re-running the command buys a **second**
   job or a second billed resource. Follow up instead — poll (`serverless status`, `pod get`)
   or clean up via the error object's `id`

## Assertions

- Switches/branches on `code`
- Does NOT branch on `status` alone or on `error` text matching
- Retry set includes `network_error` and at least one of `rate_limited`/`server_error`
- The produced handler has a default/else branch treating an unknown `code` as fatal
- Does NOT retry `cli_error`, `usage_error`, `not_found`, `no_credentials`, or
  `unauthorized`
- Does NOT retry `timeout`, `wait_timeout`, `wait_interrupted` or `job_failed`; treats them
  as "poll or clean up", not as "run it again"
- Separates `no_credentials` from `unauthorized` in the auth handling
- Reads errors from stderr and does NOT expect error JSON on stdout
- Does NOT claim `status` is always present
- Does NOT tell the user to parse plaintext for `pod`/`serverless`/`template`/`model`
  commands (on v2.10.0+ only the legacy `pod` paths and `project` still print plaintext —
  `exec` joined the coded-JSON shape and now exits non-zero, so an assertion that names
  `exec` as a plaintext surface is stale)
- Does NOT pass `--output` anything but `json`/`yaml`: on v2.10.0+ an unrecognized value is
  a `usage_error` with exit 1, where v2.9.0 silently returned JSON
