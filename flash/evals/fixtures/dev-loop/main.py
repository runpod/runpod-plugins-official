from runpod_flash import Endpoint, GpuGroup

# BUG (intentional — do NOT "pre-fix" this): a module-level constant referenced
# inside the handler. Under `flash dev` only the function body ships to the
# remote worker, so this raises `NameError: name 'VOL' is not defined` remotely
# until it is moved inside predict(). `flash deploy` imports the whole module and
# masks the bug; `flash dev` surfaces it. The eval's job is to reproduce, observe
# in the live worker logs, and fix it.
VOL = "/runpod-volume/models"

api = Endpoint(name="dev-loop-eval", gpu=GpuGroup.AMPERE_16, workers=(0, 1), dependencies=[])


@api.post("/predict")
async def predict(data: dict):
    return {"ok": True, "vol": VOL, "echo": data}


@api.get("/health")
async def health():
    return {"status": "ok"}
