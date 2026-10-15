"""Exercise the real Dockerfile with a small service-owning base, not a GPU image.

This checks the Pod command, service liveness and restart/storage contract. The
mock base provides neither PyTorch nor SSH/Jupyter; test those on the chosen base.
"""

import json
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4


def docker(*args, check=True, timeout=30):
    return subprocess.run(["docker", *map(str, args)], check=check,
                          text=True, capture_output=True, timeout=timeout)


def main():
    fixture = Path(__file__).resolve().parent
    name = f"gp26-lifecycle-{uuid4().hex[:12]}"
    base, image, volume = f"{name}:base", f"{name}:app", f"{name}-data"
    try:
        with tempfile.TemporaryDirectory() as directory:
            context = Path(directory)
            (context / "Dockerfile").write_text(
                "FROM python:3.12-slim-bookworm\n"
                "COPY --chmod=755 start.sh /start.sh\n"
                'CMD ["/start.sh"]\n', encoding="utf-8", newline="\n")
            (context / "start.sh").write_text(
                "#!/bin/sh\nset -eu\n"
                "exec python -u -m http.server 8080 --bind 127.0.0.1\n",
                encoding="utf-8", newline="\n")
            print(docker("build", "-t", base, context, timeout=300).stdout)
        print(docker("build", "--build-arg", f"BASE_IMAGE={base}",
                     "-t", image, fixture, timeout=120).stdout)
        docker("volume", "create", volume)
        docker("run", "-d", "--name", name, "--restart", "always",
               "--mount", f"type=volume,source={volume},target=/workspace", image)
        first_start = wait_for_service(name)
        # State stands in for a previous probe result and the user's edited source.
        docker("exec", name, "python", "-c",
               "from pathlib import Path; "
               "Path('/workspace/probe.json').write_text('retained result'); "
               "Path('/workspace/user.py').write_text('# retained user edit')")
        docker("restart", "--time", "2", name)
        second_start = wait_for_service(name)
        if first_start == second_start:
            raise AssertionError("the restart did not change StartedAt")
        docker("exec", name, "python", "-c",
               "from pathlib import Path; "
               "assert Path('/workspace/probe.json').read_text() == 'retained result'; "
               "assert Path('/workspace/user.py').read_text() == '# retained user edit'")
        print("PASS: default command keeps the mock base service alive before and "
              "after restart; prior workspace files remain unchanged. No GPU proof.")
    except subprocess.CalledProcessError as error:
        print(error.stdout or "")
        print(error.stderr or "")
        raise
    finally:
        # Only this run's random names; never prune other images or user storage.
        docker("rm", "-f", name, check=False)
        docker("volume", "rm", volume, check=False)
        docker("image", "rm", image, base, check=False)


def wait_for_service(name):
    for attempt in range(20):
        response = docker("exec", name, "python", "-c",
                          "from urllib.request import urlopen; "
                          "assert urlopen('http://127.0.0.1:8080/', timeout=2).status == 200",
                          check=False, timeout=5)
        if response.returncode == 0:
            break
        if attempt == 19:
            raise AssertionError(f"base service did not become ready: {response.stderr}")
        time.sleep(0.5)
    # A short successful response alone must not pass an immediately exiting Pod.
    time.sleep(2)
    state = json.loads(docker("inspect", name).stdout)[0]
    if not state["State"]["Running"] or state["RestartCount"] != 0:
        raise AssertionError(f"container exited or automatically restarted: {state['State']}")
    return state["State"]["StartedAt"]


if __name__ == "__main__":
    main()
