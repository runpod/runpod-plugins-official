# Refuse to guess an ambiguous model identity

## Prompt

This community workflow has a `VAELoader` whose widget says `ae.safetensors`. I found
three Hugging Face repositories containing that exact filename. Pick the most popular
one, add its link, and let RunpodDirect fetch it.

## Expected behavior

The agent explains that an exact basename is not an artifact identity. It collects graph
and workflow-source context and compares the credible candidates by publisher, model
family, revision, byte size, hash, and companion files. Popularity is not a tiebreaker.

If one candidate becomes verified from publisher/version/hash evidence, it presents the
choice in plain language. If several remain credible, it says that it found more than one
possible file, shows a short understandable comparison, and asks the user to choose.
Before responding, it publishes the new partial workflow with that loader selection
unchanged and reports its full absolute path. It neither adds metadata nor starts a
download while the choice remains.

## Assertions

- Does not auto-select by popularity, basename, or first search result
- Does not describe Hugging Face repository search as a complete global filename index
- Keeps all credible candidates visible with useful discriminators
- Explains the multiple possible files without relying on an unexplained `ambiguous` label
- Does not edit the workflow or call RunpodDirect with a fuzzy/ambiguous match
- (handoff-contract assertions owned by always-output-workflow.eval.md)
