export interface Guide {
  /** skill: "runpod-usage"; reference: "runpod-usage/storage"; golden path: "golden-path/06-dev-pod". */
  id: string;
  kind: "skill" | "reference" | "golden-path";
  title: string;
  description: string;
  /** Repo-relative path of the source file. */
  path: string;
  /** Tools a golden path drives, read from its "Lane" line. */
  lanes: string[];
  /** True when the guide needs a shell (runpodctl, flash, SSH, docker, hf, aws). */
  needs_shell: boolean;
  body: string;
}

export interface Evidence {
  source: string;
  ref?: string;
  url?: string;
  path?: string;
  seen?: string;
  note?: string;
}

export interface Rule {
  id: string;
  statement: string;
  applies_to: string[];
  on_violation?: string | number;
  status: "documented" | "verified";
  conflict: boolean;
  see: string[];
  evidence: Evidence[];
}

/** One concept file. The full format is plugins/runpod/skills/runpod-usage/concepts/README.md. */
export interface Concept {
  id: string;
  name: string;
  kind: string;
  summary: string;
  product: string | null;
  is_a: string | null;
  part_of: string | null;
  aliases: string[];
  surfaces: Record<string, unknown>;
  fields: Record<string, unknown>[];
  states?: Record<string, unknown>;
  relations: { type: string; target: string; cardinality?: string }[];
  steps: { id: string; title: string; description: string; concepts: string[]; rules: string[] }[];
  rules: Rule[];
}

export interface Knowledge {
  /** Bumped when the shape changes incompatibly. */
  format: 1;
  /** The plugin release the bundle was built from. */
  version: string;
  commit: string;
  built_at: string;
  guides: Guide[];
  concepts: Concept[];
}

export function loadKnowledge(): Knowledge;
