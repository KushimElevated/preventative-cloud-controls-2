'use client';
import Link from 'next/link';
import { createContext, useContext, useState } from 'react';
import { z } from 'zod';
import { Catalog, CommonSchemas } from '@a2ui/web_core/v0_9';
import { createComponentImplementation } from '@a2ui/react/v0_9';
import { CATALOG_ID, PROTOCOL, dataSchemas, type ComponentData } from '@/lib/a2ui-contract';
import { Badge, date, Icon, Notice } from '../ui';

type WorkspaceContextType = { busy: boolean; gate: ComponentData<'ApprovalGate'>; selectScope: (scope: string) => void };
export const WorkspaceContext = createContext<WorkspaceContextType | null>(null);
function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error('Engineering workspace context is required');
  return value;
}
const api = <K extends keyof typeof dataSchemas>(name: K) => ({ name, schema: z.object({ data: dataSchemas[name] }).strict() });
function Source({ kind }: { kind: string }) {
  const labels: Record<string, string> = { OBSERVED: 'Observed · fixture', SIMULATION_ESTIMATE: 'Simulation estimate', DETERMINISTIC_GUIDANCE: 'Rule-based guidance', AI_SUGGESTION: 'AI suggestion · unverified' };
  return <span className={`evidence-kind kind-${kind.toLowerCase()}`}>{labels[kind] || kind}</span>;
}

export const EngineeringWorkspace = createComponentImplementation({ name: 'EngineeringWorkspace', schema: z.object({ children: CommonSchemas.ChildList }).strict() }, ({ props, buildChild }) =>
  <div className="engineering-grid">{Array.isArray(props.children) && props.children.map(child => { const id = typeof child === 'string' ? child : child.id; return <div key={id} className={`engineering-cell cell-${id}`}>{buildChild(id, typeof child === 'string' ? undefined : child.basePath)}</div>; })}</div>);

export const ControlSummary = createComponentImplementation(api('ControlSummary'), ({ props }) => {
  const d = props.data;
  return <section className="engineering-card intent-card"><div className="engineering-card-top"><span className="eyebrow">01 / Security intent</span><Source kind="OBSERVED"/></div>
    <h2>{d.name}</h2><p>{d.objective}</p><div className="row-meta"><span className="provider"><i>A</i>Azure Policy</span><span className="badge">Revision {d.revision}</span><span className="badge">{d.scope_name}</span><Badge value={d.severity}/></div>
    <Link className="subtle-link" href={`/controls/${encodeURIComponent(d.control_id)}`}>Open conventional control detail →</Link></section>;
});

export const ImpactAssessment = createComponentImplementation(api('ImpactAssessment'), ({ props }) => {
  const d = props.data, workspace = useWorkspace();
  const [filter, setFilter] = useState('ALL'), [query, setQuery] = useState('');
  const rows = d.rows.filter(r => (filter === 'ALL' || r.result === filter) && `${r.name} ${r.application} ${r.owner || ''}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="engineering-card"><div className="engineering-card-top"><span className="eyebrow">02 / Impact assessment</span><Source kind="OBSERVED"/></div>
    <div className="assistant-scope"><h2>Understand the affected estate</h2><label>Target scope<select aria-label="Assistant target scope" className="input" disabled={workspace.busy} value={d.scope_id} onChange={e => workspace.selectScope(e.target.value)}>{d.scopes.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select></label></div>
    <div className="impact-counts">{[['ALL', 'Evaluated', d.evaluated], ['COMPLIANT', 'Compliant', d.counts.COMPLIANT], ['NON_COMPLIANT', 'Noncompliant', d.counts.NON_COMPLIANT], ['UNKNOWN', 'Unknown', d.counts.UNKNOWN]].map(([value, label, n]) => <button type="button" key={value} aria-pressed={filter === value} className={`impact-count count-${String(value).toLowerCase()} ${filter === value ? 'selected' : ''}`} onClick={() => setFilter(String(value))}><span>{label}</span><strong>{n}</strong></button>)}</div>
    <div className="assistant-search"><input className="input" aria-label="Filter assessed resources" placeholder="Filter by resource, application, or owner…" value={query} onChange={e => setQuery(e.target.value)}/><small>{rows.length} of {d.evaluated} shown · {d.counts.NOT_APPLICABLE} not applicable</small></div>
    <div className="table-wrap"><table><thead><tr><th>Resource / application</th><th>Configuration</th><th>Readiness</th></tr></thead><tbody>{rows.map(r => <tr key={r.id}><td><strong>{r.name}</strong><small>{r.application} · {r.owner || 'Owner missing'}</small><details><summary className="subtle-link">Evidence</summary><p>{r.reason}</p><Badge value={r.exception}/></details></td><td><Badge value={r.result}/></td><td><Badge value={r.readiness_result}/></td></tr>)}</tbody></table>{!rows.length && <div className="empty">No resources match this filter.</div>}</div>
    <div className="impact-foot"><div><Source kind="SIMULATION_ESTIMATE"/><p><strong>{d.predicted_denied ?? 'Unknown'}</strong> predicted denied requests out of {d.requests_total} recorded request fixtures. This does not predict application outages.</p></div><div><span className="eyebrow">Potentially affected applications</span><div className="app-chips">{d.applications.map(a => <span className="badge" key={a}>{a}</span>)}{!d.applications.length && <span className="muted">No noncompliant or unknown applications in this assessment.</span>}</div></div></div>
  </section>;
});

export const PolicyDiffViewer = createComponentImplementation(api('PolicyDiffViewer'), ({ props }) => {
  const d = props.data;
  return <section className="engineering-card"><div className="engineering-card-top"><span className="eyebrow">03 / Policy change</span><Source kind="SIMULATION_ESTIMATE"/></div><h2>From visibility to prevention</h2>
    <div className="policy-comparison"><div><span className="diff-label">Observed baseline · fixture</span>{d.baseline.map(b => <p key={b.id}><Badge value={b.effect.toUpperCase()}/><small>{b.id} · {b.scope_id}</small></p>)}{!d.baseline.length && <p>No baseline evidence.</p>}</div><div><span className="diff-label">Proposed implementation</span><p><Badge value="DENY"/><small>Create / update guardrail</small></p></div></div>
    <p className="text-small muted">Semantic comparison only. The baseline fixture does not contain a full deployed policy document.</p><details><summary className="subtle-link">Inspect proposed policy JSON</summary><pre className="code">{d.proposed_document}</pre><small className="digest-text">SHA-256 {d.implementation_digest}</small></details><p className="text-small">{d.limitation}</p></section>;
});

export const EvidencePanel = createComponentImplementation(api('EvidencePanel'), ({ props }) => {
  const d = props.data, [checked, setChecked] = useState<string[]>([]);
  return <section className="engineering-card"><div className="engineering-card-top"><span className="eyebrow">04 / Evidence & readiness</span><span className="badge">{d.blockers.length} blockers</span></div><h2>What do we know—and what is missing?</h2>
    <div className="evidence-list">{d.items.map(item => <div className="evidence-item" key={item.label}><Source kind={item.kind}/><h3>{item.label}</h3><p>{item.detail}</p></div>)}</div>
    <details open={d.blockers.length > 0}><summary className="subtle-link">Readiness review checklist</summary><p className="text-small muted">Checkmarks are local review notes. They do not change readiness evidence, metrics, or approvals.</p><div className="checklist">{d.blockers.map(item => <label className="checkbox-row" key={item}><input type="checkbox" checked={checked.includes(item)} onChange={e => setChecked(v => e.target.checked ? [...v, item] : v.filter(x => x !== item))}/><span>{item}</span></label>)}{!d.blockers.length && <p>No blockers in the synthetic assessment. Independent connectivity proof is still required for real deployment.</p>}</div></details>
    <div className="evidence-stamp">Snapshot {d.snapshot_id.slice(0, 8)} · Collected {date(d.collected_at)} · Assessed {date(d.assessed_at)}</div></section>;
});

export const ExceptionReview = createComponentImplementation(api('ExceptionReview'), ({ props, context }) => {
  const d = props.data, w = useWorkspace(), [resource, setResource] = useState(d.request_options[0]?.id || '');
  return <section className="engineering-card"><div className="engineering-card-top"><span className="eyebrow">05 / Exception review</span><Source kind="OBSERVED"/></div><h2>Keep acceptance separate from enforcement</h2>
    <div className="exception-list">{d.items.map(e => <div key={e.id}><div><strong>{e.id}</strong><small>{e.resource_ids.join(', ')} · Expires {date(e.expires_at)}</small></div><Badge value={e.disposition}/></div>)}{!d.items.length && <p>No exceptions recorded for the selected resources.</p>}</div>
    <div className="draft-box"><label className="field"><span>Prepare an exception-request draft</span><select className="input" aria-label="Exception draft resource" value={resource} onChange={e => setResource(e.target.value)} disabled={!w.gate.can_request || w.busy}>{d.request_options.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}</select></label>
      <button className="button secondary small" disabled={w.busy || !w.gate.can_request || !w.gate.current || !resource} onClick={() => void context.dispatchAction({ event: { name: 'draft_exception', context: { resource_ids: [resource] } } })}>Draft exception for review</button><p className="text-small muted">A trusted review form opens before anything is submitted. Drafts expire after 10 minutes.</p></div>
    <Link className="subtle-link" href="/exceptions">Open exception register →</Link></section>;
});

export const RolloutTimeline = createComponentImplementation(api('RolloutTimeline'), ({ props }) => {
  const d = props.data;
  return <section className="engineering-card"><div className="engineering-card-top"><span className="eyebrow">06 / Draft rollout plan</span><Source kind="DETERMINISTIC_GUIDANCE"/></div><h2>A path to a governed pilot</h2>
    <ol className="assistant-plan">{d.next_steps.map((s, i) => <li key={s}><span>{String(i + 1).padStart(2, '0')}</span><p>{s}</p></li>)}</ol><Notice tone={d.ready ? '' : 'warning'}>{d.ready ? 'The current fixture is ready to prepare for review.' : 'Resolve evidence and readiness blockers before approval or handoff.'}</Notice>
    {d.existing.map(r => <div className="stat-line" key={r.id}><Link className="subtle-link" href="/rollouts">Package {r.id.slice(0, 8)}</Link><Badge value={r.stage}/><Badge value={r.delivery_state}/></div>)}<Link className="subtle-link" href="/rollouts">Open governed rollouts →</Link></section>;
});

export const ApprovalGate = createComponentImplementation(api('ApprovalGate'), ({ props, context }) => {
  const d = props.data, w = useWorkspace();
  return <section className="engineering-card approval-gate"><div><div className="eyebrow">07 / Human decision</div><h2>{!d.current ? 'Evidence changed. Reassess before continuing.' : d.ready ? 'Prepare the governed handoff' : 'Review the gaps before enforcement'}</h2><p>Security and Cloud Engineering approve separately. This workspace cannot approve or deploy a control.</p>{!d.current && <p role="alert">{d.stale_reasons.join(' · ')}</p>}</div><div className="gate-actions"><button className="button secondary" disabled={w.busy || !d.can_assess} onClick={() => void context.dispatchAction({ event: { name: 'refresh_assessment', context: {} } })}>Refresh assessment</button><button className="button" disabled={w.busy || !d.can_plan || !d.current} onClick={() => void context.dispatchAction({ event: { name: 'prepare_handoff', context: {} } })}>Prepare governed handoff <Icon name="arrow"/></button></div></section>;
});

// No basic catalog, expression functions, HTML, URL components, styles or executable plugins.
export const engineeringCatalog = new Catalog(CATALOG_ID, PROTOCOL, [EngineeringWorkspace, ControlSummary,
  ImpactAssessment, PolicyDiffViewer, EvidencePanel, ExceptionReview, RolloutTimeline, ApprovalGate], []);
