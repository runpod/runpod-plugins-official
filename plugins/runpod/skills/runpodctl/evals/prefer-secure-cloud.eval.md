# Default to Secure Cloud, treat Community as an explicit opt-in

## Prompt

I need a pod with an A40 to fine-tune a model overnight, and I want it as cheap as
possible. Give me the create command.

## Expected behavior

The agent should:

1. Recommend **Secure Cloud** even though the ask is "as cheap as possible" — the run is
   long and interruption-sensitive, and Community Cloud hosts can be reclaimed mid-run
2. Leave `--cloud-type` off the command (or pass `SECURE` explicitly) rather than
   reaching for `--cloud-type COMMUNITY` to hit the lower price
3. Name the trade concretely if it quotes the Community rate: cheaper per hour, but a
   reclaimed host or a changed public IP costs more than the saving on an overnight job
4. Read the actual rates from `runpodctl gpu list` (`securePricePerHr` /
   `communityPricePerHr`) rather than asserting a gap from memory
5. Leave the choice with the user — present Community as available if they accept the
   restart risk, not as the recommendation

## Assertions

- Recommends Secure Cloud for the overnight run
- The create command does NOT contain `--cloud-type COMMUNITY`
- States at least one concrete Community instability (host reclaimed mid-run, public IP
  changes on migrate/restart, or port 22 needing `--public-ip`)
- Cites `runpodctl gpu list` for any price comparison it makes
- Does NOT silently pick Community just because the user said "cheap"
