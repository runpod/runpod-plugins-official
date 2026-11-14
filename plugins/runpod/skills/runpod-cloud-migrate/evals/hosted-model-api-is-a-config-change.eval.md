# A hosted-model API client is a base URL change, not a rewrite

## Prompt

Our app calls Together AI for chat completions through the OpenAI SDK. Can we run this on
Runpod instead?

```python
client = OpenAI(base_url="https://api.together.xyz/v1", api_key=os.environ["TOGETHER_API_KEY"])
client.chat.completions.create(model="meta-llama/Llama-3.3-70B-Instruct-Turbo", messages=msgs, stream=True)
```

## Expected behavior

1. Runs the inventory; reports the `together-ai` and `openai-compatible` hits.
2. Opens `reference/together-ai.md` and gives the two landing spots: a Runpod Public
   Endpoint when Runpod hosts the model, otherwise the user's own Serverless endpoint
   running the vLLM worker with the OpenAI-compatible route.
3. States the billing change in kind (per token to per second of worker time) without
   numbers for Together AI, and the cold-start trade-off of scale to zero.
4. Proposes the change as configuration: base URL, API key name and model name read from
   env vars, with the old values kept as the fallback.

## Assertions

- Does NOT rewrite the call site to a different client library.
- Does NOT claim a model is available as a Public Endpoint without checking the live
  catalog or the docs.
- Does NOT create an endpoint before the user approves the plan and cost bound.
- Routes endpoint creation to runpod-vllm rather than restating its procedure.
