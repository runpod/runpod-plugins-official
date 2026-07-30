# Read invoke URLs and GPU cost from command output

## Prompt

I'm on a shell-only box with `runpodctl` and no MCP tools. I want a serverless endpoint
from template `tpl-abc` on the cheapest GPU with at least 24 GB that can actually schedule
in `US-KS-2`, and then the URL to send a job to. Give me the exact commands and tell me
where each number comes from — don't create anything yet.

## Expected behavior

The agent should:

1. Run `runpodctl gpu list --include-unavailable` and filter on `memoryInGb >= 24`,
   noting that the default listing hides no-stock GPUs and could omit one that has stock
   only in `US-KS-2`
2. Compare `securePricePerHr` / `communityPricePerHr` rather than assuming a lower tier is
   cheaper, and treat a `null` price as "not offered on that cloud", not as free
3. Check `dataCenterAvailability[]` for a `US-KS-2` entry with real stock instead of
   trusting top-level `stockStatus` (the best status across all DCs), reading `"none"` as
   "offered here, no stock"
4. Pin placement with `--data-center-ids US-KS-2` — reading per-DC availability without
   constraining the create leaves the placement to chance
5. Say that `--gpu-id` on serverless resolves to a GPU **pool**, so the endpoint may run on
   more than the single card that was priced, and/or that the listed prices are pod
   on-demand rates while serverless bills per request-second
6. State that the run URL comes from the `urls` object in the create output (`run`,
   `runsync`, `health`) rather than hand-assembling `https://api.runpod.ai/v2/<id>/run`

## Assertions

- Runs `runpodctl gpu list` before choosing a GPU
- Cites `securePricePerHr` / `communityPricePerHr` for the cost comparison
- Consults `dataCenterAvailability[]` for `US-KS-2`
- Command includes `--data-center-ids US-KS-2`
- Says the run URL will be read from the `urls` object rather than assembled by hand
- Flags at least one of: the type→pool translation, or that the prices are pod rates
- Does NOT claim the CLI can't report GPU pricing
- Does NOT present `securePricePerHr` as the endpoint's serverless cost
