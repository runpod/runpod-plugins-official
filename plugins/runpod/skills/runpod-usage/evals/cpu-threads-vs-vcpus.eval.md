# CPU threads on a GPU pod

## Prompt

My video preprocessing on a GPU pod is way slower than on my laptop. `nproc` says 96 cores, so
I set my thread pool and data loader to 96, but it got even slower. What's going on?

## Expected behavior

The agent should:

1. Explain that the pod can see every core on the machine but can only use the vCPUs it rents,
   so `nproc` and `os.cpu_count()` overstate what the pod gets
2. Explain that starting a thread per visible core gets the extra threads throttled, which slows
   CPU-bound work down
3. Show how to read the real limit from the cgroup (`/sys/fs/cgroup/cpu.max`, or
   `cpu.cfs_quota_us` / `cpu.cfs_period_us` under `/sys/fs/cgroup/cpu/`)
4. Recommend capping threads to that limit: `OMP_NUM_THREADS`, `MKL_NUM_THREADS`,
   `torch.set_num_threads()` and data loader `num_workers`

## Assertions

- Says `nproc` / `os.cpu_count()` can report more cores than the pod's vCPUs
- Names CPU throttling from too many threads as the cause
- Gives a way to read the cgroup CPU limit
- Recommends setting thread counts to the vCPU limit, not the visible core count
- Does NOT recommend raising thread or worker counts further
