# Route project requests to the Runpod SDK

## Prompt

I want to develop and deploy a serverless app with `runpodctl project new`,
`project start`, `project build` and `project deploy`. My script expects JSON
errors, but `runpodctl project deploy --help` exits 1 with empty stdout and this
stderr:

```text
The "project" command has been removed.

Use the Runpod SDK for serverless development workflows:
  https://github.com/runpod/runpod-python
```

Should I retry, fix my API key, or try `project create` or `project dev`?

## Expected behavior

The agent should treat exit 1 as a fatal failure, surface the notice verbatim,
and route serverless development to the Runpod SDK at
https://github.com/runpod/runpod-python. It should explain that the hidden `project`
catch-all returns the same plain-text notice for every invocation, including
subcommands, aliases, flags and help.

## Assertions

- Uses the Runpod SDK for serverless development.
- Treats exit 1 as failure, with empty stdout and the exact notice on stderr,
  including its final newline.
- Handles this as a plain-text exception without requiring a JSON `code`.
- Does not retry, suggest credential changes, or treat a help request as success.
- Does not recommend `project new`, `start`, `build`, `deploy`, `create` or
  `dev` as working development commands.
- Explains that unknown subcommands and flags also reach the same notice.
- Keeps `runpodctl serverless` available for endpoint management.
