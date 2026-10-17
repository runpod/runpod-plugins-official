# Serve multiple HTTP routes from one pool of GPU workers

## Prompt

With the Runpod Python SDK, I want a single GPU endpoint that exposes two HTTP routes:
`POST /predict` for inference and `GET /health` for a health check, sharing the
same pool of workers (1 to 5). The model should load once per worker. Write the code.

## Expected behavior

The agent should:

1. Decorate a **class** with `@app.api(gpu=..., workers=(1, 5), ...)`
2. Load the model in a `@runpod.init` method
3. Register routes with `@runpod.post("/predict")` and `@runpod.get("/health")` methods
4. Show how to call it: `MyApi.post("/predict", {...})` in a dev session, or a raw POST of the
   JSON body itself to the deployed endpoint

## Assertions

- Uses `@app.api(...)` on a class, not one `@app.queue` per route
- Uses `workers=(1, 5)`, NOT `workers=5` (which means `(0, 5)`)
- Loads the model in `@runpod.init`, not inside the route methods
- Routes are `@runpod.post("/predict")` and `@runpod.get("/health")`
- The POST method takes one `body` argument; any raw HTTP example sends the object itself,
  not `{"data": {...}}`
- Does NOT import from `runpod_flash`
