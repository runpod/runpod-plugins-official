# Golden path 16: get the job result pushed instead of polling

## Prompt

I submit long jobs to my Runpod endpoint and don't want to poll. Can Runpod call my
server when each job finishes?

## Expected behavior

Follows [golden path 16](../golden-paths/16-serverless-webhooks.md): pass `webhook` as a
top-level sibling of `input` in the `/run` body (inside `input` it only reaches the
handler). The receiver must be public HTTPS and return `2xx`; a non-2xx or timeout is
retried up to 2 more times, so the receiver dedupes on the job `id`. The delivered body is
the whole job (`status` first, then `output`). A failed webhook does not fail the job, so
keep `/status` as the fallback.

## Assertions

- Puts `webhook` at the top level of the `/run` body
- Requires a public HTTPS receiver that answers `2xx`, and idempotent handling on job `id`
- Says the payload is the whole job object, not the bare output
- Keeps `/status` polling as the fallback for critical results
