# Route project requests to the Runpod SDK

## Prompt

I have a source build containing the unreleased runpod/runpodctl#382.
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
catch-all returns the same plain-text notice for project subcommands, aliases and
flags. Supported help forms include `project --help`, `project deploy --help`,
`help project`, `help project deploy`, `-h project`, `--help project` and
`--help project deploy`. It should scope this contract to builds containing #382,
not released versions through v3.0.1.

## Assertions

- Uses the Runpod SDK for serverless development.
- Treats exit 1 as failure, with empty stdout and the exact notice on stderr,
  including its final newline.
- Handles this as a plain-text exception without requiring a JSON `code`.
- Does not retry, suggest credential changes, or treat the listed project help
  forms as success; does not generalize this contract to every help arrangement.
- Does not recommend `project new`, `start`, `build`, `deploy`, `create` or
  `dev` as working development commands.
- Explains that unknown subcommands and flags also reach the same notice.
- Keeps `runpodctl serverless` available for endpoint management.

## Released-version compatibility prompt

I use the published runpodctl v3.0.1. A `project` command prints an error on stdout
but exits 0. Does that mean it succeeded? Should I use this version for serverless
development? Does its project SSH client check host keys? What about v2.14.0?

## Released-version assertions

- Recommends the Runpod SDK for serverless development on every CLI version.
- Explains that released versions through v3.0.1 print `project` runtime errors to
  stdout and exit 0, so the output must be checked even when the exit status is zero.
- Does not apply the fatal stderr notice contract to these released versions or
  invent a release version for #382.
- Checks `runpodctl version` and, for source or custom builds, verifies the build's
  commit before assuming the #382 contract, since their version string can match
  a released version.
- Explains that v2.15.0 through v3.0.1 support legacy `project` SSH with host key
  pinning, while v2.14.0 and earlier disable host key checking on the `project`
  and `exec python` SSH paths.
- Presents legacy behavior as compatibility and security caveats, not a reason to
  use `project` or downgrade the CLI.
