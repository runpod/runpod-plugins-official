// The shape of one concept file. Zod checks each file on its own; the checks
// that need more than one file (does this relation target exist?) live in
// validate.ts.

import { z } from "zod";

export const KINDS = [
  "platform", // the root: Runpod itself
  "resource", // has its own id and CRUD in the API
  "component", // part of a resource, no CRUD of its own
  "catalog", // read-only reference data
  "capability", // something you do with a resource
  "billing", // money
  "limit", // a cap or quota
  "tool", // a Runpod SDK or CLI the customer runs
  "external", // something Runpod references but does not own (an image)
  "infrastructure", // Runpod hardware a resource runs on, not managed directly (a machine)
  "process", // an ordered flow across concepts (how deploying a pod works)
] as const;

export const PRODUCTS = [
  "pods",
  "clusters",
  "serverless",
  "public-endpoints",
  "flash",
  "templates",
  "hub",
  "storage",
  "billing",
  "account",
] as const;

export const RELATION_TYPES = [
  "requires", // cannot exist without the target
  "uses", // optionally references the target
  "located_in", // pinned to the target
  "runs_on", // executes on the target
  "billed_by", // charges appear under the target
  "constrained_by", // a limit or catalog entry caps it
] as const;

// Every file is public-facing, so every rule stands on a public source.
export const STATUSES = [
  "verified", // observed on a live account
  "documented", // stated in the live REST v2 spec, the public docs or a public skill
] as const;

export const SOURCES = [
  "rest-v2-spec", // https://api.runpod.io/v2/openapi.json
  "public-docs", // docs.runpod.io and the public GraphQL reference
  "skill", // a skill file in this repo, cited by path
  "live-probe", // a request made against a live account
  "other", // anything else public; say what in ref, url or note
] as const;

const id = z.string().regex(/^[a-z0-9]+(-[a-z0-9]+)*$/, "kebab-case");
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "YYYY-MM-DD");

// Where a statement comes from. Any mix of a citation (ref), a link (url), a
// file (path) and a free-text note; at least one is required.
export const Evidence = z
  .strictObject({
    source: z.enum(SOURCES),
    ref: z.string().min(1).optional(),
    url: z.url().optional(),
    path: z.string().min(1).optional(),
    seen: date.optional(),
    note: z.string().optional(),
  })
  .refine((e) => e.ref || e.url || e.path || e.note, "evidence needs at least one of ref, url, path or note");

export const Field = z.strictObject({
  name: z.string().min(1),
  type: z.string().min(1),
  set: z.enum(["create", "update", "create,update", "read"]),
  required: z.boolean().optional(),
  ref: id.optional(),
  unit: z.string().optional(),
  default: z.union([z.string(), z.number(), z.boolean()]).optional(),
  values: z.array(z.string()).optional(),
  note: z.string().optional(),
});

export const Transition = z.strictObject({
  action: z.string().min(1),
  from: z.array(z.string()).min(1),
  to: z.string().min(1),
});

export const States = z.strictObject({
  field: z.string().min(1),
  values: z.record(z.string(), z.string()),
  transitions: z.array(Transition).default([]),
  on_invalid_action: z.union([z.number(), z.string()]).optional(),
  evidence: z.array(Evidence).default([]),
});

export const Relation = z.strictObject({
  type: z.enum(RELATION_TYPES),
  target: id,
  cardinality: z.enum(["0..1", "1", "0..n", "1..n"]).optional(),
});

export const Rule = z.strictObject({
  id: z.string().regex(/^[a-z0-9-]+\.[a-z0-9-]+$/, "<concept-id>.<kebab-slug>"),
  // Omitted or empty means the rule is about the concept as a whole.
  applies_to: z.array(z.string().regex(/^(field|state|action):.+$/)).default([]),
  statement: z.string().min(1),
  on_violation: z.union([z.string(), z.number()]).optional(),
  status: z.enum(STATUSES),
  conflict: z.boolean().default(false),
  see: z.array(z.string()).default([]),
  evidence: z.array(Evidence).min(1),
});

// One step of a process: what happens, which concepts take part, and which
// existing rules govern it. Rules live on their concepts; steps point at them.
export const Step = z.strictObject({
  id,
  title: z.string().min(1),
  description: z.string().min(1),
  concepts: z.array(id).min(1),
  rules: z.array(z.string()).default([]),
});

export const Surfaces = z.strictObject({
  rest_v2: z.strictObject({ schema: z.string().optional(), paths: z.array(z.string()).default([]) }).optional(),
  graphql: z
    .strictObject({
      type: z.string().optional(),
      queries: z.array(z.string()).default([]),
      mutations: z.array(z.string()).default([]),
    })
    .optional(),
  mcp: z.array(z.string()).default([]),
  runpodctl: z.array(z.string()).default([]),
  console: z.string().optional(),
});

export const Concept = z.strictObject({
  id,
  name: z.string().min(1),
  kind: z.enum(KINDS),
  summary: z.string().min(1),
  product: z.enum(PRODUCTS).nullable(),
  is_a: id.nullable(),
  part_of: id.nullable(),
  aliases: z.array(z.string()).default([]),
  surfaces: Surfaces.default({ mcp: [], runpodctl: [] }),
  fields: z.array(Field).default([]),
  states: States.optional(),
  // Only on kind: process, in order.
  steps: z.array(Step).default([]),
  relations: z.array(Relation).default([]),
  rules: z.array(Rule).default([]),
});

export type Concept = z.infer<typeof Concept>;
export type Rule = z.infer<typeof Rule>;
export type Field = z.infer<typeof Field>;
export type Step = z.infer<typeof Step>;
