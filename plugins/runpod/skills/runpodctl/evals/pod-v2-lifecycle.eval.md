# Use Pod lifecycle commands supported by API v2

## Prompt

Update a Pod's ports and environment, restart it, explain what `pod reset` does, and show the supported Pod lifecycle commands.

## Expected behavior

The agent should:

1. Use `runpodctl pod update <pod-id>` to change ports or environment on an existing Pod
2. Use `runpodctl pod restart <pod-id>` only when the user asks for a restart
3. Explain that runpodctl v3.0.0 removed `pod reset`
4. Never silently substitute restart for reset
5. Show start, stop, restart, update, and delete as supported lifecycle commands

## Assertions

- Uses `runpodctl pod update <pod-id>` for existing Pod ports or environment changes
- Uses `runpodctl pod restart <pod-id>` only for a restart request
- Explicitly reports that `pod reset` was removed in runpodctl v3.0.0
- Does NOT describe reset as an alias for restart
- Lists start, stop, restart, update, and delete; omits reset
