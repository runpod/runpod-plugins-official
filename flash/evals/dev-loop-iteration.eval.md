# Iterate on a flash GPU handler with live remote logs

## Prompt

I'm building an image-to-3D endpoint with runpod-flash and need to iterate on my GPU
handler fast — testing each change against a real GPU worker and watching the logs. My
handler works when I `flash deploy` it, but I want a tighter loop than re-deploying every
time. It also just failed with `NameError: name 'VOL' is not defined`, where `VOL` is a
constant I defined at the top of the module. How should I run this, and why is `VOL`
failing?

## Expected behavior

The agent should:

1. Recommend `flash dev` (not repeated `flash deploy`) as the iteration loop
2. Explain that `flash dev` runs the function on a **remote** GPU/CPU worker (not locally)
   while hot-reloading on save and streaming the worker's logs live
3. Run the dev server as a **background** process (it is long-running / blocking) and read
   its captured log output to see the remote worker's logs
4. Explain the `NameError`: only the function body ships to the worker, so the
   module-level `VOL` constant does not exist remotely — fix by moving it inside the
   function body
5. Note that `flash deploy` imports the whole module so it can mask this, while `flash dev`
   surfaces it

## Assertions

- Recommends `flash dev` for the iteration loop and does NOT recommend repeated `flash deploy` for iteration
- States that `flash dev` executes the function on a REMOTE worker, not on the local machine
- Mentions hot-reload on save AND live/streamed worker logs
- Runs `flash dev` as a background / non-blocking process (does NOT run it as a plain blocking command)
- Reads the dev server's log output (file or BashOutput) to inspect the remote worker logs
- Diagnoses the `NameError` as the module-level `VOL` not shipping to the worker (only the function body ships)
- Fixes it by moving `VOL` inside the decorated function body
- Notes that `flash deploy` can mask this bug while `flash dev` surfaces it
