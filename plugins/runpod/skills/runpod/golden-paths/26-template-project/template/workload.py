"""Small useful CPU workload shared by HTTP and queue adapters."""

from collections import Counter


def analyze(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be an object")
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    if len(text) > 100_000:
        raise ValueError("text must contain at most 100000 characters")
    words = text.casefold().split()
    return {"words": len(words), "counts": dict(sorted(Counter(words).items()))}
