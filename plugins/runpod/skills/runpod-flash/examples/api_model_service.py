"""A load-balanced HTTP service that loads a model once per worker.

    rp flash dev api_model_service.py --once
    rp flash deploy api_model_service.py

@runpod.init runs once when a worker starts, before it takes traffic, so
the pipeline stays in memory across requests. In a dev session you call
routes through the class; once deployed, the endpoint serves them over HTTP.
"""

import runpod

app = runpod.App("text-gen")


@app.api(gpu="ADA_24", workers=(0, 3), idle_timeout=300, dependencies=["transformers"])
class TextGen:
    @runpod.init
    def load(self):
        from transformers import pipeline

        # swap the model id for the real one once the wiring works
        self.pipe = pipeline("text-generation", model="gpt2", device=0)

    @runpod.post("/generate")
    async def generate(self, body: dict):
        out = self.pipe(body["prompt"], max_new_tokens=body.get("max_new_tokens", 20))
        return {"text": out[0]["generated_text"]}

    @runpod.get("/health")
    async def health(self):
        return {"status": "ok"}


@runpod.local_entrypoint
def main():
    print(TextGen.get("/health"))
    resp = TextGen.post("/generate", {"prompt": "Runpod is"})
    print(resp)
    assert resp["text"].startswith("Runpod is"), resp
