# Heavy layers and retained user state

## Prompt

“Optimize this template. It copies PyTorch and the whole environment into /workspace
on every boot. My old volume contains custom code I need.” Provide its real source and
baseline. Add a code-only rebuild, conflicting app dependency, empty mounted directory,
interrupted download/init, and two incompatible worker versions sharing storage.
Also change an app-version build argument declared before an unrelated system-install
step; inspect whether its scope causes that step to miss the build cache.

## Expected behavior

Keep compatible heavy dependencies in published image layers outside mounts. Preserve
user source and previous working state; use optional compatible persistent environments
only when required. Diagnose package shadowing without blind torch upgrades. Compare
actual layer identities and measured setup phases under stated cache conditions.

## Assertions

- No workspace deletion, wholesale venv sync, guaranteed host cache or universal
  `--system-site-packages` rule.
- Mount shadowing is checked; app code remains accessible with a real mount.
- Incompatible shared mutable versions are isolated; staged completion/locking fits
  the filesystem; live environments are not migrated in place.
- Partial model downloads remain unready until usable; retries preserve user data.
- Same-package-version claims do not substitute for identical published layer identity.
- Frequently changing build arguments are scoped near their consumers; a cache probe
  is not reported as a measured full-image pull or application-startup improvement.
