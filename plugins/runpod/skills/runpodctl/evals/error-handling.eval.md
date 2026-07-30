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
   `cli_error` (e.g. malformed `RUNPOD_API_URL`, a timed-out local wait loop) must not be
4. Distinguish `no_credentials` (no key set → `RUNPOD_API_KEY` / `runpodctl doctor`) from
   `unauthorized` (key present but wrong/expired) — neither is a retry
5. Treat `not_found` as server-side, not as a mistyped local path
6. Gate on a non-zero exit code and read errors from **stderr**, data from stdout — and
   not treat a `warning:`/`note:` line on stderr as a failure
7. Include a default branch for an unrecognized `code`, because the vocabulary is what the
   CLI generates rather than exhaustive (the API can pass its own code through lowercased)

## Assertions

- Switches/branches on `code`
- Does NOT branch on `status` alone or on `error` text matching
- Retry set includes `network_error` and at least one of `rate_limited`/`server_error`
- The produced handler has a default/else branch treating an unknown `code` as fatal
- Does NOT retry `cli_error`, `usage_error`, `not_found`, `no_credentials`, or
  `unauthorized`
- Separates `no_credentials` from `unauthorized` in the auth handling
- Reads errors from stderr and does NOT expect error JSON on stdout
- Does NOT claim `status` is always present
- Does NOT tell the user to parse plaintext for `pod`/`serverless`/`template`/`model`
  commands (only the legacy `pod` paths, `exec` and `project` still print plaintext)
