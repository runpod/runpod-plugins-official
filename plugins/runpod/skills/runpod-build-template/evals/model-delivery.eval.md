# Model delivery without expert redirection

## Prompt

Evaluate separately with small source fixtures and recorded model metadata; do not
download large weights or create infrastructure just to run these scenarios:

1. "Package this HF model family as a Serverless template for GitHub deployment.
   Default to the medium model and let users select another." The medium model is
   self-contained; the largest uses an adapter plus a separate base and custom loader.
2. "The build timed out after 1800 seconds while downloading the weights. Guess we
   cannot use this model?" Supply the Dockerfile, log and artifact sizes.
3. "Bake the medium model; users should be able to change MODEL_ID to a larger one
   with their attached storage." Include a matching provider cache, a wrong revision,
   an empty writable volume, and a read-only completed model as separate cases.
4. "I specifically want to test whether the managed builder can bake the largest
   model and its base. Prepare that experiment; do not build or deploy it."

## Expected behavior

Inspect complete artifacts and the loader before choosing delivery. In normal design
and timeout recovery, consider Runpod's HF cache/Model Store without the user naming it;
preserve the selected model and explain each required component's location. Implement
app configuration and actual load/download behavior together. Keep explicit experiments
and offline/preloaded-only constraints intact.

## Assertions

- No separate-base assumption from model size or training ancestry alone; sizes include
  required components and are not reported as VRAM needs.
- Provider caching and app MODEL_ID are distinct settings. An adapter/base hybrid
  observes the current endpoint cache limit, with no invented multi-cache support.
- Custom loaders consume matching local artifacts for all required components through
  supported cache-directory or local-path interfaces; a path glob, global offline flag
  or baked default does not defeat the selected model.
- Provider-cache fixtures include its real snapshot/blob-symlink layout. Any required
  materialization is justified by the loader API, with storage/startup costs disclosed;
  flat fixture files alone do not prove the real cache can be consumed directly.
- For allowed runtime downloads, missing components download once to writable storage
  and can be reused; no manual path inventory is imposed on the ordinary user.
- Tests distinguish selection/fixture checks from real offline inference and target
  platform verification. No silent smaller model, redownload of a usable base, cache
  writes or out-of-scope build/push/deploy.
- (4) keeps all requested weights in the experiment and reports its unverified budget;
  it does not replace the experiment with a different delivery plan.
