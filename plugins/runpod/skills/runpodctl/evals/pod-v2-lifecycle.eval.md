# Use Pod lifecycle commands supported by API v2

## Prompt

Restart a Pod, explain what `pod reset` does, and show the supported Pod lifecycle commands.

## Expected behavior

The agent should:

1. Use `runpodctl pod restart <pod-id>` when the user asks for a restart
2. Explain that runpodctl v3 has no `pod reset` command
3. Never silently substitute restart for reset
4. Show start, stop, restart, update, and delete as supported lifecycle commands

## Assertions

- Uses `runpodctl pod restart <pod-id>` only for a restart request
- Explicitly reports that runpodctl has no reset command
- Does NOT describe reset as an alias for restart
- Lists start, stop, restart, update, and delete; omits reset
