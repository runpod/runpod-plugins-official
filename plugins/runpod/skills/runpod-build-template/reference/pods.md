---
concepts: [pod, container-image, exposed-port, container-disk, pod-volume-disk, network-volume, pod-ssh-access]
---

# Pod contract

A Pod runs the promised application, development environment, or batch command.
SSH/Jupyter are optional interfaces, not universal requirements. When promised,
preserve the selected base's startup hooks and verify those interfaces. Inspect the
actual base entrypoint before overriding it; hook names and ordering can differ.

Keep required foreground processes alive; use `exec` for a single application or
deliberate supervision for multiple required services. Surface failed child processes
and forward shutdown signals. A fixed sleep does not prove another service is ready.
For batch workloads, successful completion/outputs are the signal; an exited process
is not automatically a failure or proof that billing stopped.

For network services bind the intended interface (usually `0.0.0.0`) and align app,
container and Runpod ports. Expose only required services and configure access controls
appropriate to their capabilities. Verify from the user's external interface, not
only `localhost`. Do not assume the proxy provides application authentication.

## Data and editable applications

Inspect actual mounts and their lifecycle. `/workspace` does not itself mean network
storage. Attaching a mount can hide baked files; keep stable runtimes outside it.
Persist the requested outputs/configuration/models, not an entire copied Python stack.
Only copy editable source when the workflow needs it. A persistent environment using
image packages requires compatible interpreter/ABI and checks for package shadowing.

If initialization maintains mutable source/environments, make it repeatable and
non-destructive. Stage changes, record compatible app/runtime versions, and retain the
previous working state. For shared storage, use locks supported by that filesystem,
namespace incompatible versions, and make replacements atomically on the same
filesystem. Never migrate a shared environment in place while another worker uses it.
Simple immutable applications need none of this migration machinery.

## Verify

- Fresh container/storage: run the real workload and retrieve useful output.
- Restart and stop/start: verify promised services, data retention and configuration.
- Reused storage/new image: preserve user changes; surface incompatible old state.
- Missing configuration/artifact: actionable logs and recoverable initialization.
- GPU workload: actual operation on the intended GPU, with representative VRAM/RAM.

Document container disk, persistent disk/network volume, mount paths, port types,
secret names, startup override if needed, and measured/provisional hardware needs.
Deployment mechanics belong to the infra lanes. Stop/delete only the task's disposable
test resources, preserving results and reporting any continuing storage charges.
