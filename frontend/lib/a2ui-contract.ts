import { z } from 'zod';

export const PROTOCOL = 'v0.9.1' as const;
export const CATALOG_ID = 'urn:cloud-control:engineering-catalog:1';
export const QUESTION = 'What would happen if we prevented public network access for Azure AI Search in production?';
export const children = ['summary', 'impact', 'policy', 'evidence', 'exceptions', 'rollout', 'gate'];
const text = z.string().max(5000), key = z.string().min(1).max(100), count = z.number().int().nonnegative();
const sha = z.string().regex(/^[a-f0-9]{64}$/);
const choice = z.object({ id: key, label: text }).strict();
export const resourceSchema = z.object({
  id: key, name: text, application: text, owner: text.nullable(),
  result: z.enum(['COMPLIANT', 'NON_COMPLIANT', 'UNKNOWN', 'NOT_APPLICABLE']),
  reason: text, exception: text, readiness_result: z.enum(['READY', 'BLOCKED', 'NOT_APPLICABLE']),
}).strict();
export const dataSchemas = {
  ControlSummary: z.object({ control_id: key, name: text, objective: text, revision: count.min(1), severity: text, scope_name: text }).strict(),
  ImpactAssessment: z.object({ assessment_id: key, scope_id: key, scopes: z.array(choice).max(100), evaluated: count,
    counts: z.object({ COMPLIANT: count, NON_COMPLIANT: count, UNKNOWN: count, NOT_APPLICABLE: count }).strict(),
    rows: z.array(resourceSchema).max(100), predicted_denied: count.nullable(), requests_total: count,
    applications: z.array(text).max(100),
  }).strict(),
  PolicyDiffViewer: z.object({ baseline: z.array(z.object({ id: key, scope_id: key, effect: text, observed_at: text }).strict()).max(100),
    proposed_document: z.string().max(12000), implementation_digest: sha, limitation: text,
  }).strict(),
  ExceptionReview: z.object({ items: z.array(z.object({ id: key, resource_ids: z.array(key).max(50), status: text, disposition: text, expires_at: text }).strict()).max(100),
    request_options: z.array(choice).max(100),
  }).strict(),
  EvidencePanel: z.object({ snapshot_id: key, assessed_at: text, collected_at: text,
    items: z.array(z.object({ label: text, detail: text, kind: z.enum(['OBSERVED', 'SIMULATION_ESTIMATE', 'DETERMINISTIC_GUIDANCE', 'AI_SUGGESTION']) }).strict()).max(100),
    blockers: z.array(text).max(200),
  }).strict(),
  RolloutTimeline: z.object({ ready: z.boolean(), existing: z.array(z.object({ id: key, stage: text, delivery_state: text }).strict()).max(100), next_steps: z.array(text).max(10) }).strict(),
  ApprovalGate: z.object({ current: z.boolean(), ready: z.boolean(), stale_reasons: z.array(text).max(30), can_assess: z.boolean(), can_request: z.boolean(), can_plan: z.boolean() }).strict(),
};
export type ComponentData<K extends keyof typeof dataSchemas> = z.infer<(typeof dataSchemas)[K]>;
const component = <K extends keyof typeof dataSchemas>(name: K, id: string) => z.object({ id: z.literal(id), component: z.literal(name), data: dataSchemas[name] }).strict();
export const componentSchema = z.discriminatedUnion('component', [
  z.object({ id: z.literal('root'), component: z.literal('EngineeringWorkspace'), children: z.array(key).length(7) }).strict(),
  component('ControlSummary', 'summary'), component('ImpactAssessment', 'impact'), component('PolicyDiffViewer', 'policy'),
  component('EvidencePanel', 'evidence'), component('ExceptionReview', 'exceptions'), component('RolloutTimeline', 'rollout'), component('ApprovalGate', 'gate'),
]);
const create = z.object({ version: z.literal(PROTOCOL), createSurface: z.object({ surfaceId: key, catalogId: z.literal(CATALOG_ID) }).strict() }).strict();
const update = z.object({ version: z.literal(PROTOCOL), updateComponents: z.object({ surfaceId: key, components: z.array(componentSchema).length(8) }).strict() }).strict();
export const bundleSchema = z.object({ mode: z.literal('DETERMINISTIC'), surface_id: key, assessment_id: key,
  expected_revision: count.min(1), evidence_digest: sha, messages: z.tuple([create, update]),
}).strict().superRefine((bundle, ctx) => {
  const [first, second] = bundle.messages, nodes = second.updateComponents.components;
  if (first.createSurface.surfaceId !== bundle.surface_id || second.updateComponents.surfaceId !== bundle.surface_id ||
      JSON.stringify(nodes.map(n => n.id)) !== JSON.stringify(['root', ...children]) ||
      nodes[0].component !== 'EngineeringWorkspace' || JSON.stringify(nodes[0].children) !== JSON.stringify(children)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Invalid or unbounded engineering workspace topology' });
  }
});
export type SurfaceBundle = z.infer<typeof bundleSchema>;
export function validateSurface(value: unknown): SurfaceBundle {
  if (JSON.stringify(value).length > 200000) throw new Error('Surface exceeds the workspace size limit');
  return bundleSchema.parse(value);
}
export const actionSchema = z.discriminatedUnion('name', [
  z.object({ name: z.literal('refresh_assessment'), context: z.object({}).strict() }).strict(),
  z.object({ name: z.literal('prepare_handoff'), context: z.object({}).strict() }).strict(),
  z.object({ name: z.literal('draft_exception'), context: z.object({ resource_ids: z.array(key).min(1).max(50) }).strict() }).strict(),
]);
export type Draft = { intent_id: string; resource_ids: string[]; scope_id: string; expires_at: string; suggested_exception_expiry: string };
