---
description: Migrate this codebase from the Runpod GraphQL API or REST v1 to REST v2 — inventory, rewrite, verify.
argument-hint: [scope: all | rest | graphql] [path]
---

Invoke the **runpod-migrate** skill and run its full workflow on this repository.

User input (scope and/or a path to restrict the migration to): $ARGUMENTS

- If a scope is given (`all`, `rest`, or `graphql`), use it directly instead of
  inferring one from conversation.
- If a path is given, restrict the inventory and migration to that directory.
- If no arguments are given, default to scope `all` on the current working
  directory — state that default in one line and proceed. Do not open with
  questions; the inventory results are the right moment for any real fork
  (e.g. code depending on a capability v2 removed).

Start with the inventory step — do not edit any files before the inventory has run
and its results have been shown to the user.
