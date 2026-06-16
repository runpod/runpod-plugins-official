# Get SSH connection details for a running pod

## Prompt

I have a running pod with id `pod-xyz`. I want to SSH into it to debug a process
interactively. What runpodctl command(s) should I use to get connected?

## Expected behavior

The agent should:

1. Retrieve connection details with `runpodctl ssh info pod-xyz` (or `runpodctl pod get pod-xyz`)
2. Connect using the SSH command/key those return
3. NOT use any deprecated interactive SSH subcommand to open the session

## Assertions

- Uses `runpodctl ssh info pod-xyz` or `runpodctl pod get pod-xyz` to obtain host/port/key
- Does NOT rely on a deprecated interactive `runpodctl ssh`/`exec` session command
- Final guidance results in a usable `ssh ...` connection to the pod
