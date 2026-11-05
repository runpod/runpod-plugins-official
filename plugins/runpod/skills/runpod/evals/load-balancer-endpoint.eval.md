# Golden paths 14 and 17: a load-balancing endpoint for a custom HTTP (or WebSocket) server

## Prompt

I have a container that runs its own HTTP server with `/ping`, `/predict` and a `/ws`
WebSocket route. Put it on Runpod serverless so clients call those paths directly.

## Expected behavior

Matches [golden path 14](../golden-paths/14-load-balancing-endpoint.md) (and
[17](../golden-paths/17-serverless-websocket.md) for the WebSocket route): a
load-balancing endpoint, not a queue endpoint. Uses the v2 create (MCP `create-endpoint`
or `POST /v2/serverless`) with `"type": "LOAD_BALANCER"` and a `REQUEST_COUNT` scaler,
because neither the REST v1 body nor `runpodctl serverless create` exposes an
endpoint-type field (golden path 14, prerequisites), and v2 has no PATCH for `type`. Passes the server's port in `ports` and sets `PORT`/`PORT_HEALTH`
(the reply defaults them to 80 otherwise), sets `timeout` explicitly, reads the invoke URL
from `requestUrls.base`, and calls `/ping` until it answers 200 before reporting success.
Cleanup deletes the endpoint and, separately, any template it created.

## Assertions

- Chooses `LOAD_BALANCER` with a `REQUEST_COUNT` scaler on the v2 create
- Sets the port, `PORT`/`PORT_HEALTH` and `timeout` explicitly
- Uses `requestUrls.base` rather than assembling the URL, and verifies with a real request
- Deletes a self-created template separately from the endpoint
