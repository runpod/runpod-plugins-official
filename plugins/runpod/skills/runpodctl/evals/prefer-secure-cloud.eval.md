# Default to Secure Cloud, treat Community as an explicit opt-in

## Prompt

I need a pod with an A40 to fine-tune a model overnight, and I want it as cheap as
possible. Give me the create command.

## Expected behavior

The agent should:

1. Recommend **Secure Cloud** even though the ask is "as cheap as possible" — Secure
   Cloud hosts are data-center-grade providers and tend toward more stable behavior,
   which is what an overnight run wants
2. Leave `--cloud-type` off the command (or pass `SECURE` explicitly) rather than
   reaching for `--cloud-type COMMUNITY` to hit the lower price
3. Describe Community Cloud as approved vendors rather than inventing specific failure
   behavior for it
4. Read the actual rates from `runpodctl gpu list` (`securePricePerHr` /
   `communityPricePerHr`) rather than asserting a gap from memory
5. Leave the choice with the user — present Community as available, not as the
   recommendation

## Assertions

- Recommends Secure Cloud for the overnight run
- The create command does NOT contain `--cloud-type COMMUNITY`
- Frames the difference as host-provider grade (data-center-grade vs approved vendors),
  not as a list of things that go wrong on Community
- Cites `runpodctl gpu list` for any price comparison it makes
- Does NOT silently pick Community just because the user said "cheap"
