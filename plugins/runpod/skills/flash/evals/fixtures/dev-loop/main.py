import runpod

app = runpod.App("dev-loop-eval")


# BUG (intentional — do NOT "pre-fix" this): describe() imports humanize, but
# the decorator does not declare it, so the worker raises
# `No module named 'humanize'`. The eval's job is to reproduce it in a live dev
# session, read the worker error, and fix the decorator.
@app.queue(cpu="cpu3c-1-2", workers=(0, 1), dependencies=[])
def describe(size_bytes: int) -> str:
    import humanize

    return humanize.naturalsize(size_bytes)


@runpod.local_entrypoint
def main():
    out = describe.remote(3_000_000)
    print(out)
    assert out == "3.0 MB", out
