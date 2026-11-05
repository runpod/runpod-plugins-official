# Golden path 12: stream a serverless job's output as it is generated

## Prompt

My serverless handler builds a long answer word by word. I want my client to show the
words as they arrive. What do I change and how do I read them?

## Expected behavior

Follows [golden path 12](../golden-paths/12-serverless-streaming.md): the handler must
`yield` (a generator), not `return`; the client submits with `/run`, then polls
`/stream/<job-id>`, draining the chunks buffered since the last call until `status` is
`COMPLETED` or `FAILED`, with a bounded loop and a sleep. Explains that without
`return_aggregate_stream` the `/status` result carries no output, and that a cold start
delays the first chunk, not the stream.

## Assertions

- Says `yield`, not `return`, and names `/stream/<job-id>`
- Describes `/stream` as repeated poll-and-drain, not a single long-lived SSE connection
- Mentions `return_aggregate_stream` for consumers that need the whole result
- Bounds the poll loop and does not hot-loop (the `/stream` rate limit is 2000 requests / 10 s)
