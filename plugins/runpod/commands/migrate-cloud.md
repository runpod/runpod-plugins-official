---
description: Migrate this project from another cloud or GPU platform (Modal, AWS, Vast.ai, Replicate and others) to Runpod. Inventory, plan, port, verify.
argument-hint: "[platform] [path]"
---

Invoke the **runpod-cloud-migrate** skill and run its workflow on this repository.

User input (a platform and/or a path to restrict the migration to): $ARGUMENTS

- If a platform is given, still run the inventory on the whole path first: report every
  platform it finds, then work on the named one.
- If a path is given, restrict the inventory and migration to that directory.
- If no arguments are given, inventory the current working directory and let the results
  decide which playbooks to open.

Start with the inventory step. Do not edit files, create Runpod resources or change
anything on the source platform before the inventory has run, the plan has been shown,
and the user has approved it.
