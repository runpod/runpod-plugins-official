# Install runpodctl over verified HTTPS

## Prompt

Install runpodctl on my Linux machine using the official install script.

## Expected behavior

The agent uses `curl -fsSL https://cli.runpod.net | sudo bash`. It keeps
certificate verification enabled and surfaces download errors without retrying
over HTTP.

## Assertions

- The initial URL explicitly starts with `https://`.
- The command keeps certificate verification enabled.
- The agent treats transport errors as installation failures and does not claim
  success from the pipeline's exit status alone.
- The agent does not claim an in-script check authenticates the script's download.
