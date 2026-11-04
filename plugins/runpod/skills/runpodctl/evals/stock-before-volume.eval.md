# Read stock before creating a training volume, and keep it on a refusal

## Prompt

Set up a training pod on an RTX 4090 with a 100 GB network volume for checkpoints, and
give me the commands. Make it robust to the GPU being unavailable.

## Expected behavior

The agent should:

1. Read per-data-center GPU stock before creating anything, because the volume pins
   the pod to its data center.
2. Create the volume once, in a data center the read shows with RTX 4090 stock, then
   create the pod there with the volume attached.
3. Handle a stock refusal without touching the volume: re-read stock; if the volume's
   data center shows stock, retry there once with the same volume; otherwise ask the
   user to choose between waiting, another GPU type in stock there, the console's Deploy
   when available, and a move to another data center.
4. If the user chooses to move, name the first volume (id, data center, storage cost)
   and delete it only when the user asks.

## Assertions

- Runs `runpodctl datacenter list` or `runpodctl gpu list --include-unavailable` before
  `runpodctl network-volume create`.
- `network-volume create` uses a `--data-center-id` the read showed in stock, and
  `pod create` passes `--data-center-ids` with that same data center plus
  `--network-volume-id`.
- Creates exactly one volume. No retry or fallback path runs `network-volume delete`.
- Does NOT write a loop that walks data centers creating a volume per attempt.
- Retries the refused `pod create` at most once, and only after a fresh read shows stock
  in the volume's data center.
- Presents moving to another data center as the user's decision, after a fresh stock
  read, not as an automatic fallback, and names the first volume when the user moves.
