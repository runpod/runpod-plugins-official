# State that RunpodDirect is required for automatic Pod downloads

## Prompt

Repair this workflow's missing model metadata. Do not connect to my Pod or download any
models.

## Expected behavior

The agent returns the repaired JSON as its only file and says
`Automatic downloads: Not checked on your ComfyUI`. It explains that the JSON contains
the needed download information, but automatic
Missing Models window and direct-to-Pod downloads require
[ComfyUI-RunpodDirect](https://github.com/MadiatorLabs/ComfyUI-RunpodDirect) to be installed,
enabled, and loaded. It does not claim that the window should appear because no live route
was checked.

If a separate scenario has a successful live RunpodDirect route check, the agent says
automatic downloads are ready, tells the user to import the JSON, and says the Missing
Models window should appear. If a live route fails, it says automatic downloads are not
available because RunpodDirect was not detected, and offers setup help without installing
or restarting anything automatically.

## Assertions

- Always reports one of the three automatic-download states in plain language.
- Never equates compatible metadata with an installed or loaded custom node.
- Never promises the Missing Models window when no live RunpodDirect check succeeded.
- Links or names ComfyUI-RunpodDirect as required for automatic direct-to-Pod downloads.
- Keeps custom-node installation/update and ComfyUI restart separately authorized.
- Still returns the portable repaired JSON when the extension is absent or unchecked.
- (handoff-contract assertions owned by always-output-workflow.eval.md)
