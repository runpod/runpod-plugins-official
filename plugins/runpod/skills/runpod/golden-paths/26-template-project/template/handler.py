"""Queue adapter; SDK startup is separate so workload tests need no network."""

from workload import analyze


def handler(job):
    if not isinstance(job, dict) or "input" not in job:
        raise ValueError("job must contain input")
    return analyze(job["input"])


if __name__ == "__main__":
    import runpod

    runpod.serverless.start({"handler": handler})
