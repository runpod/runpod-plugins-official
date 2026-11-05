# Golden path 11: call a ready hosted model without deploying anything

## Prompt

I just want to send one instruction to a hosted Qwen model on Runpod and cap the reply at
about 200 tokens. I don't want to deploy anything. How?

## Expected behavior

Matches [golden path 11](../golden-paths/11-public-endpoints.md): a Public Endpoint, not a
new serverless endpoint. Uses the account `RUNPOD_API_KEY` as the Bearer token and nothing
else (no Docker, runpodctl, template or volume). Sends the instruction to the
OpenAI-compatible `/openai/v1/chat/completions` route, because the native `/runsync`
`input.prompt` is a raw completion that ignored the instruction and `max_tokens` in the
live run. Warns that a reasoning model can spend a small `max_tokens` inside `<think>`.

## Assertions

- Does not create an endpoint, template or volume
- Uses the OpenAI-compatible route for an instruction with a token cap, and says why
- Notes the call is pay-per-output and needs account credits
- Gives enough `max_tokens` headroom for a reasoning model, or picks one without a think phase
