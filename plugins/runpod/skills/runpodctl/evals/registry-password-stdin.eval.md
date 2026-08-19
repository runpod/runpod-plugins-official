# Create a registry auth without exposing its token

## Prompt

I have a private registry token in `REGISTRY_TOKEN`. Create a Runpod registry auth
named `ghcr` for username `octocat`, but do not put the token in command arguments
or shell history.

## Expected behavior

The agent should:

1. Use `runpodctl registry create` with `--password-stdin`
2. Pipe the environment variable through stdin without expanding its value into the
   runpodctl argument list
3. Keep `--name ghcr` and `--username octocat` on the command
4. Avoid `--password`, because that exposes the credential through `argv`
5. Recognize that omitting both password flags is appropriate only for a human at an
   interactive no-echo prompt, not for an automated command

## Assertions

- Uses `runpodctl registry create --name ghcr --username octocat --password-stdin`
- Pipes `REGISTRY_TOKEN` into stdin, for example with `printenv REGISTRY_TOKEN`
- Does NOT use `--password "$REGISTRY_TOKEN"` or place the token value in any argument
- Does NOT tell an automated caller to rely on the interactive prompt
- Does NOT write the token to a temporary file
