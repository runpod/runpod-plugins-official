export interface Guide {
  /** skill: "runpod-usage"; reference: "runpod-usage/storage"; golden path: "golden-path/06-dev-pod". */
  id: string;
  kind: "skill" | "reference" | "golden-path";
  title: string;
  description: string;
  /** Repo-relative path of the source file. */
  path: string;
  /** True when a golden path declares lanes, mcp and concepts in frontmatter. */
  tagged: boolean;
  /** Tools the guide drives: runpod-mcp, runpodctl, flash, ssh, docker, hf, aws, rest, console. */
  lanes: string[];
  /** Whether an agent with only the Runpod MCP tools can finish it. Null when not declared. */
  mcp: "full" | "partial" | "none" | null;
  /** True when the guide needs a shell (runpodctl, flash, SSH, docker, hf, aws). */
  needs_shell: boolean;
  /** Concepts the guide is linked to. */
  concepts: string[];
  body: string;
}

/**
 * A link from a guide to a concept. `uses`: a golden path works with the concept.
 * `explains`: a skill or reference doc is cited as evidence by the concept's rules.
 */
export interface Link {
  from: string;
  to: string;
  type: "uses" | "explains";
  via: "frontmatter" | "evidence";
  /** For via: evidence, the rules that cite the guide. */
  rules?: string[];
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
  format: 2;
  /** The plugin release the bundle was built from. */
  version: string;
  commit: string;
  built_at: string;
  guides: Guide[];
  concepts: Concept[];
  links: Link[];
}

export function loadKnowledge(): Knowledge;
