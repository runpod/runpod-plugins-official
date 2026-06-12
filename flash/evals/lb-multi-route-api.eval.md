# Serve multiple HTTP routes from one pool of GPU workers

## Prompt

Using runpod-flash, I want a single GPU endpoint that exposes two HTTP routes:
`POST /predict` for inference and `GET /health` for a health check, sharing the
same pool of workers (1 to 5). Write the code.

## Expected behavior

The agent should:

1. Create an `Endpoint` INSTANCE (not a decorator on a function): `api = Endpoint(name=..., gpu=..., workers=(1, 5), ...)`
2. Register routes with `@api.post("/predict")` and `@api.get("/health")`
3. Put heavy imports inside the route handlers
4. Make handlers `async def`

## Assertions

- Creates an `Endpoint(...)` instance assigned to a variable (load-balanced mode)
- Uses `@<instance>.post("/predict")` and `@<instance>.get("/health")` to register routes
- Uses `workers=(1, 5)` (explicit min/max tuple), NOT `workers=5`
- Does NOT define each route as its own separate `@Endpoint(name=...)` decorator (that would be separate endpoints, not shared workers)
- Route handlers are `async def`
- Heavy/GPU imports are inside the handler functions
