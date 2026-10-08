'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api, downloadJson } from '@/lib/api';
import type { Control, Exception, Rollout } from '@/lib/types';
import { useApp } from './context';
import { Badge, date, Empty, Heading, Icon, Metric, Notice, Panel, Provider } from './ui';

function ControlTable({ controls }: { controls: Control[] }) {
  return controls.length ? <div className="table-wrap"><table><thead><tr><th>Security control</th><th>Provider</th><th>Lifecycle</th><th>Assessment</th><th/></tr></thead><tbody>{controls.map(c => <tr key={c.id} className="click-row"><td><Link href={`/controls/${c.id}`}><strong>{c.name}</strong><small>Revision {c.latest_revision} · {c.security_owner}</small></Link></td><td><Provider value={c.provider}/></td><td><Badge value={c.lifecycle}/></td><td>{c.latest_assessment ? <Badge value={!c.latest_assessment.current ? 'UNKNOWN' : c.latest_assessment.report.ready ? 'READY' : 'BLOCKED'}/> : <span className="muted text-small">Not assessed</span>}</td><td><Link href={`/controls/${c.id}`} aria-label={`Open ${c.name}`}><Icon name="arrow"/></Link></td></tr>)}</tbody></table></div> : <Empty title="No controls in your scope">Create a control or select an authorized demo identity.</Empty>;
}

export function DashboardPage() {
  const app = useApp(), m = app.metrics;
  const colors: Record<string, string> = { COMPLIANT: '#5aa58c', NON_COMPLIANT: '#dcab61', UNKNOWN: '#a1b3bf', NOT_APPLICABLE: '#dce5e6' };
  const count = Object.values(m.configuration_counts).reduce((a, b) => a + b, 0);
  return <>
    <Heading eyebrow="Cloud Security / Overview" title="Build prevention. Prove coverage." subtitle="Turn recurring cloud risks into reviewed controls, with a clear path from intent to enforcement.">
      <button className="button" disabled={app.user.role !== 'CONTROL_ENGINEER'} onClick={() => app.openControl()}><Icon name="plus"/>New control</button>
    </Heading>
    <Notice>Local engineering workspace. All inventory, approvals, and pipeline results are synthetic. <strong>Live cloud deployment is disabled.</strong></Notice>
    <div className="metrics">
      <Metric label="Preventive controls" value={m.controls} note={`${m.assessed} assessed · AWS and Azure`}/>
      <Metric label="Verified demo coverage" value={m.coverage_percent === null ? 'N/A' : `${m.coverage_percent}%`} note={`${m.protected_pairs} of ${m.applicable_pairs} applicable control-resource pairs`} tone="green-text"/>
      <Metric label="Open exceptions" value={m.exceptions} note={`${m.expiring_soon} expiring soon · ${m.expired} expired`} tone="amber-text"/>
      <Metric label="Awaiting handoff" value={m.waiting_approval} note={`${m.rollouts} rollout packages · ${m.drifted} drifted`}/>
    </div>
    <div className="two-column"><div>
      <Panel title="Control portfolio" subtitle="Security intent, implementation readiness, and ownership" action={<Link className="subtle-link" href="/controls">View catalog →</Link>} bare><ControlTable controls={app.controls}/></Panel>
      <Panel title="Recent engineering activity" subtitle="Append-only record of decisions and changes" action={<Link href="/audit" className="subtle-link">View audit trail →</Link>} bare>
        <div className="timeline">{app.audit.slice(0, 5).map(a => <div className="timeline-row" key={a.id}><strong>{a.action.toLowerCase().replaceAll('_', ' ')}</strong><p>{a.actor_id} · {a.scope_id || 'Session'} · {date(a.created_at)}</p></div>)}</div>
      </Panel>
    </div><div>
      <Panel title="Configuration posture" subtitle="Current snapshot, not predicted application outages">
        <div className="stat-line"><span>Evaluated control-resource pairs</span><strong>{count}</strong></div>
        <div className="coverage-bar" role="img" aria-label={Object.entries(m.configuration_counts).map(([k, v]) => `${k}: ${v}`).join(', ')}>{Object.entries(m.configuration_counts).map(([k, v]) => <span key={k} style={{ width: `${count ? v / count * 100 : 0}%`, background: colors[k] }}/>)}</div>
        {Object.entries(m.configuration_counts).map(([k, v]) => <div className="legend" key={k}><i style={{ background: colors[k] }}/>{k.toLowerCase().replaceAll('_', ' ')}<b>{v}</b></div>)}
        <p className="text-small muted" style={{ marginTop: 17 }}>Exemptions remain separate from configuration compliance. Unknown evidence is never counted as protected.</p>
      </Panel>
      <Panel title="The path to prevention" subtitle="One change. Traceable evidence. Two reviewers.">
        {[['Define the intent', 'Connect recurring risk to a native control.'], ['Assess the impact', 'Separate posture, request effects, and readiness.'], ['Review and hand off', 'Approve exact revisions. Export to Cloud Engineering.'], ['Verify the outcome', 'Reconcile expected and observed enforcement.']].map(([title, description], i) => <div className="workflow-item" key={title}><div className="workflow-number">0{i + 1}</div><div><strong>{title}</strong><p>{description}</p></div></div>)}
      </Panel>
    </div></div>
  </>;
}

export function CatalogPage() {
  const app = useApp(); const [query, setQuery] = useState('');
  const rows = app.controls.filter(c => `${c.name} ${c.provider} ${c.lifecycle}`.toLowerCase().includes(query.toLowerCase()));
  return <><Heading eyebrow="Control engineering" title="Security control catalog" subtitle="Provider-independent intent, backed by versioned native implementations."><button className="button" onClick={() => app.openControl()} disabled={app.user.role !== 'CONTROL_ENGINEER'}><Icon name="plus"/>New control</button></Heading>
    <div className="toolbar"><input className="input" aria-label="Search controls" placeholder="Search controls, providers, or status…" value={query} onChange={e => setQuery(e.target.value)}/><span className="text-small muted">{rows.length} controls</span></div>
    <Panel title="All controls" subtitle="Catalog ownership does not transfer deployment authority" bare><ControlTable controls={rows}/></Panel>
  </>;
}

export function DetailPage({ id, section = 'overview', refreshKey }: { id: string; section?: string; refreshKey: number }) {
  const app = useApp(); const [c, setControl] = useState<Control | null>(null), [error, setError] = useState('');
  const [scope, setScope] = useState('');
  useEffect(() => { let active = true; setError(''); void api<Control>(`/controls/${id}`).then(r => { if (active) { setControl(r); setScope(previous => previous || r.scope_id); } }).catch(e => { if (active) setError(e.message); }); return () => { active = false; }; }, [id, refreshKey, app.user.id]);
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!c) return <div className="loading">Loading control…</div>;
  const assessment = c.latest_assessment;
  const author = app.user.role === 'CONTROL_ENGINEER';
  const scopedOptions = app.scopes.filter(s => s.provider === c.provider && (s.id === c.scope_id || s.parent_id === c.scope_id));
  return <>
    <Heading eyebrow="Control catalog / Detail" title={c.name} subtitle={c.objective}>
      <button className="button secondary" disabled={!author || app.busy} onClick={() => app.openControl(c)}>New revision</button>
    </Heading>
    <div className="row-meta" style={{ marginTop: -12, marginBottom: 17 }}><Provider value={c.provider}/><Badge value={c.lifecycle}/><span className="badge">Revision {c.latest_revision}</span><span className="text-small muted">{c.scope_id} · {c.severity.toLowerCase()} priority</span></div>
    <div className="tabs">{[['overview','Overview'],['implementations','Implementation'],['simulation','Impact assessment'],['history','Revision history']].map(([key,label]) => <Link className={`tab ${section === key ? 'active' : ''}`} key={key} href={`/controls/${c.id}${key === 'overview' ? '' : '/' + key}`}>{label}</Link>)}</div>
    {section === 'overview' && <div className="two-column"><div>
      <Panel title="Security intent"><p className="description">{c.rationale}</p><div className="detail-grid"><div><label>Security owner</label>{c.security_owner}</div><div><label>Engineering owner</label>{c.engineering_owner}</div><div><label>Evidence source</label>{c.evidence}</div><div><label>Enforcement boundary</label>{c.provider === 'AZURE' ? 'Create/update guardrail; existing exposure requires remediation.' : 'Protect an established account Block Public Access baseline.'}</div></div></Panel>
      <Panel title="Existing native baseline" subtitle="Imported fixture · Cloud Engineering remains the operational owner" bare><div className="table-wrap"><table><thead><tr><th>Binding</th><th>Scope</th><th>Mode</th></tr></thead><tbody>{c.baseline?.map(b => <tr key={b.id}><td><strong>{b.id}</strong><small>{b.content.coverage}</small></td><td>{b.scope_id}</td><td><Badge value={b.content.effect.toUpperCase()}/></td></tr>)}</tbody></table></div></Panel>
      <Panel title="Exceptions" action={<button className="button secondary small" onClick={() => app.openException(c)} disabled={!['CONTROL_ENGINEER','EXCEPTION_REQUESTER'].includes(app.user.role)}>Request exception</button>} bare><ExceptionTable rows={c.exceptions || []} compact/></Panel>
    </div><div>
      <Panel title="Next engineering decision">
        <Badge value={!assessment ? 'DRAFT' : !assessment.current ? 'UNKNOWN' : assessment.report.ready ? 'READY' : 'BLOCKED'}/>
        <p className="description">{!assessment ? 'Run an impact assessment against the current inventory snapshot.' : !assessment.current ? 'Evidence changed. Run a fresh assessment before any further review.' : assessment.report.ready ? 'Prepare a package for separate security and Cloud Engineering review.' : 'Resolve readiness blockers, remediate resources, or implement reviewed exemptions.'}</p>
        <Link className="button" href={`/controls/${c.id}/simulation`}>Open assessment <Icon name="arrow"/></Link>
      </Panel>
      <Notice>Approving or exporting this control does not enforce it. Only matching observations support verified demo coverage.</Notice>
    </div></div>}
    {section === 'implementations' && <div className="two-column"><Panel title="Native implementation" subtitle={c.implementation.template_id}><div className="detail-grid"><div><label>Provider</label><Provider value={c.provider}/></div><div><label>Validation</label><Badge value="COMPLIANT"/> <span className="text-small muted">Exact supported template</span></div></div><pre className="code">{JSON.stringify(c.implementation.document, null, 2)}</pre><label className="text-small muted">Content SHA-256</label><p className="code">{c.implementation.document_digest}</p></Panel><div><Notice tone="warning">This is a review-only fixture. No cloud credentials, SDK deployment methods, or production enforcement switches exist.</Notice><Panel title="Capability limits"><p className="description">{c.provider === 'AZURE' ? 'The supported built-in definition is referenced by ID and version. Existing public endpoints are not changed by a deny assignment. Private endpoint, DNS, and client readiness must be verified independently.' : 'SCPs have no native audit effect and cannot configure Block Public Access. This template restricts changes to an already established account baseline. A bucket-level exception cannot bypass account protection.'}</p></Panel></div></div>}
    {section === 'simulation' && <>
      <div className="toolbar"><select className="input" style={{ maxWidth: 280 }} aria-label="Assessment target scope" value={scope || c.scope_id} onChange={e => setScope(e.target.value)}>{scopedOptions.map(s => <option value={s.id} key={s.id}>{s.name}</option>)}</select><button className="button" disabled={!author || app.busy} onClick={() => void app.action('Impact assessment completed.', () => api(`/controls/${c.id}/assessments`, 'POST', { scope_id: scope || c.scope_id }))}>Run assessment</button><span className="text-small muted">Read-only · Fixture evaluator v1</span></div>
      {assessment ? <>
        {!assessment.current && <Notice tone="warning">Stale assessment: {assessment.stale_reasons.join('; ')}. Run again before review.</Notice>}
        <div className="metrics"><Metric label="Resources evaluated" value={assessment.report.evaluated} note={`Target: ${assessment.scope_id}`}/><Metric label="Noncompliant" value={assessment.report.counts.NON_COMPLIANT} note="Existing configuration, not predicted outages" tone="amber-text"/><Metric label="Unknown configuration" value={assessment.report.counts.UNKNOWN} note="Missing evidence never passes"/><Metric label="Predicted denied requests" value={assessment.report.predicted_denied ?? 'Unknown'} note={`${assessment.report.requests.length} representative request fixtures`}/></div>
        <Notice tone={assessment.report.ready ? '' : 'warning'}><strong>{assessment.report.ready ? 'Ready for package review.' : `${assessment.report.blockers.length} readiness blockers.`}</strong> {assessment.report.limitation}</Notice>
        {assessment.report.blockers.length > 0 && <Panel title="Readiness blockers"><ul className="blockers">{assessment.report.blockers.map(x => <li key={x}>{x}</li>)}</ul></Panel>}
        <Panel title="Resource-level evidence" subtitle={`Assessment ${assessment.id.slice(0,8)} · ${date(assessment.created_at)}`} action={<button className="button secondary small" disabled={!['CONTROL_ENGINEER','CLOUD_ENGINEER'].includes(app.user.role) || app.busy} onClick={() => app.openRollout(assessment)}>Prepare rollout</button>} bare><div className="table-wrap"><table><thead><tr><th>Resource / Application</th><th>Configuration</th><th>Exception</th><th>Readiness</th></tr></thead><tbody>{assessment.report.rows.map(r => <tr key={r.id}><td><strong>{r.name}</strong><small>{r.application} · {r.owner || 'Owner unknown'}</small><small>{r.reason}</small></td><td><Badge value={r.result}/></td><td><Badge value={r.exception}/></td><td><Badge value={r.readiness_result}/></td></tr>)}</tbody></table></div></Panel>
        <Panel title="Representative request effects" subtitle="Not a general authorization simulator; no requests were sent to a cloud"><div className="table-wrap"><table><thead><tr><th>Fixture</th><th>Operation</th><th>Predicted result</th></tr></thead><tbody>{assessment.report.requests.map(r => <tr key={r.id}><td>{r.id}</td><td>{r.action}</td><td><Badge value={r.result}/></td></tr>)}</tbody></table></div></Panel>
      </> : <Panel title="Impact assessment"><Empty title="No assessment yet">Run against the current snapshot to identify configuration gaps and readiness blockers.</Empty></Panel>}
    </>}
    {section === 'history' && <Panel title="Immutable revision history" bare><div className="table-wrap"><table><thead><tr><th>Revision</th><th>Reason</th><th>Author</th><th>Created</th></tr></thead><tbody>{c.revisions?.map(r => <tr key={r.id}><td>v{r.revision}</td><td>{r.content.change_reason}</td><td>{r.author_id}</td><td>{date(r.created_at)}</td></tr>)}</tbody></table></div></Panel>}
  </>;
}

function ExceptionTable({ rows, compact = false }: { rows: Exception[]; compact?: boolean }) {
  const app = useApp();
  const [reasons, setReasons] = useState<Record<string, string>>({});
  return rows.length ? <div className="table-wrap"><table><thead><tr><th>Exception / Scope</th><th>Governance</th><th>Native state</th><th>Expires</th>{!compact && <th>Review action</th>}</tr></thead><tbody>{rows.map(e => <tr key={e.id}><td><strong>{e.resource_ids.join(', ')}</strong><small>{e.scope_id}</small><small>{e.justification}</small>{e.cleanup_required && <small className="amber-text">Native cleanup follow-up required</small>}</td><td><Badge value={e.disposition}/><small>{e.status.toLowerCase().replaceAll('_',' ')}</small></td><td><Badge value={e.native_status}/></td><td>{date(e.expires_at)}</td>{!compact && <td>
    {app.user.role === 'SECURITY_APPROVER' && <><input className="input" style={{ minWidth: 200, marginBottom: 7 }} placeholder="Review rationale (10+ characters)" aria-label={`Rationale for ${e.id}`} value={reasons[e.id] || ''} onChange={event => setReasons({ ...reasons, [e.id]: event.target.value })}/><div className="button-row">{(e.status === 'REQUESTED' ? ['REVIEW','REJECT'] : e.status === 'SECURITY_REVIEW' ? ['APPROVE','REJECT'] : e.status === 'APPROVED' ? ['REVOKE'] : []).map(decision => <button key={decision} className="button secondary small" disabled={app.busy || (reasons[e.id] || '').length < 10} onClick={() => void app.action('Exception decision recorded.', () => api(`/exceptions/${e.id}/decision`, 'POST', { decision, reason: reasons[e.id], expected_version: e.version }))}>{decision.toLowerCase()}</button>)}</div></>}
    {app.user.role === 'CLOUD_ENGINEER' && <button className="button secondary small" disabled={app.busy || e.representation === 'UNSUPPORTED' || (e.disposition !== 'APPROVED_UNAPPLIED' && !e.cleanup_required)} onClick={() => void app.action('Mock native observation recorded. No cloud changes made.', () => api(`/exceptions/${e.id}/mock-native-receipt`, 'POST', { status: e.cleanup_required ? 'REMOVED' : 'APPLIED', expected_version: e.version, reference: `mock:azure/assignment/search/exemptions/${e.id}` }))}>{e.cleanup_required ? 'Record mock removal' : 'Record mock application'}</button>}
    {!['SECURITY_APPROVER','CLOUD_ENGINEER'].includes(app.user.role) && <span className="text-small muted">Review requires delegated approver</span>}
    </td>}</tr>)}</tbody></table></div> : <Empty title="No exceptions in this scope">Requests, approvals, and effective exemptions will appear here.</Empty>;
}

export function ExceptionsPage() {
  const app = useApp(); const [filter, setFilter] = useState('ALL');
  const rows = app.exceptions.filter(e => filter === 'ALL' || e.disposition === filter);
  return <><Heading eyebrow="Risk governance" title="Exceptions with an end date" subtitle="Risk acceptance is not a cloud exemption. Track both, including what happens at expiry."><button className="button" disabled={!['CONTROL_ENGINEER','EXCEPTION_REQUESTER'].includes(app.user.role)} onClick={() => app.openException()}><Icon name="plus"/>Request exception</button></Heading>
    <div className="metrics three"><Metric label="Tracked exceptions" value={app.exceptions.length} note="Across authorized control scopes"/><Metric label="Expiring soon" value={app.metrics.expiring_soon} note="Approved · next seven days" tone="amber-text"/><Metric label="Expired" value={app.metrics.expired} note="Derived from time, independent of scheduler"/></div>
    <div className="toolbar"><select className="input" style={{ maxWidth: 250 }} aria-label="Filter exceptions" value={filter} onChange={e => setFilter(e.target.value)}>{['ALL','PENDING','APPROVED_UNAPPLIED','EFFECTIVE','EXPIRED','UNSUPPORTED'].map(x => <option key={x} value={x}>{x.toLowerCase().replaceAll('_',' ')}</option>)}</select></div>
    <Panel title="Exception register" subtitle="Permanent exemptions are not supported" bare><ExceptionTable rows={rows}/></Panel>
  </>;
}

function RolloutCard({ r }: { r: Rollout }) {
  const app = useApp(); const [reason, setReason] = useState('');
  const name = app.controls.find(c => c.id === r.manifest.control_id)?.name || r.manifest.control_id;
  const approver = ['SECURITY_APPROVER','CLOUD_ENGINEER'].includes(app.user.role);
  const canPlan = ['CONTROL_ENGINEER','CLOUD_ENGINEER'].includes(app.user.role);
  const canExport = ['CONTROL_ENGINEER','SECURITY_APPROVER','CLOUD_ENGINEER'].includes(app.user.role);
  const stages = ['ASSESSMENT','OBSERVATION','PILOT','LIMITED','BROAD'];
  const next = stages[stages.indexOf(r.stage)+1];
  const doExport = (draft: boolean) => app.action(draft ? 'Draft bundle downloaded.' : 'Approved demo handoff downloaded.', async () => { const bundle = await api(`/rollouts/${r.id}/export${draft ? '?draft=true' : ''}`, 'POST'); downloadJson(bundle, `${r.id}-${draft ? 'draft' : 'approved-demo'}.json`); });
  return <Panel title={name} subtitle={`${r.manifest.scope_id} · ${date(r.created_at)} · ${r.id.slice(0,8)}`} action={<Badge value={r.delivery_state}/>}>
    <div className="ring-track">{stages.map(s => <span key={s} className={s === r.stage ? 'active' : ''}>{s.toLowerCase()}</span>)}{['PAUSED','CANCELLED'].includes(r.stage) && <Badge value={r.stage}/>}</div>
    {r.blockers.length > 0 && <Notice tone="warning"><strong>Not ready for handoff.</strong><ul className="blockers">{r.blockers.map(b => <li key={b}>{b}</li>)}</ul></Notice>}
    <div className="equal-columns"><div><div className="eyebrow">Review decisions</div>{['SECURITY','ENGINEERING'].map(kind => { const vote = r.approvals.find(a => a.kind === kind); return <div className="stat-line" key={kind}><span>{kind === 'SECURITY' ? 'Security review' : 'Cloud Engineering review'}</span>{vote ? <Badge value={vote.decision}/> : <span className="badge">Awaiting review</span>}</div>; })}
      {approver && !r.approvals.some(a => a.actor_id === app.user.id) && <><label className="field"><span>Decision rationale</span><input className="input" aria-label={`Review rationale ${r.id}`} value={reason} onChange={e => setReason(e.target.value)} placeholder="What did you verify?"/></label><div className="button-row">{['APPROVED','REJECTED'].map(decision => <button className={`button ${decision === 'REJECTED' ? 'secondary' : ''} small`} key={decision} disabled={app.busy || reason.length < 10 || (decision === 'APPROVED' && r.blockers.length > 0)} onClick={() => void app.action('Review recorded against the exact manifest.', () => api(`/rollouts/${r.id}/approvals`, 'POST', { decision, reason, expected_version: r.version }))}>{decision === 'APPROVED' ? 'Approve package' : 'Reject package'}</button>)}</div></>}
    </div><div><div className="eyebrow">Recovery & evidence</div><p className="text-small muted">{r.manifest.rollback}</p><p className="code" style={{ fontSize: 10 }}>{r.manifest_digest}</p><span className="text-small muted">Manifest is sealed. A changed scope, revision, exception set, or inventory requires a new assessment.</span></div></div>
    <div className="button-row" style={{ marginTop: 22 }}>
      {canPlan && next && !['PAUSED','CANCELLED'].includes(r.stage) && <button className="button small" disabled={app.busy || r.blockers.length > 0} onClick={() => void app.action('Rollout stage updated.', () => api(`/rollouts/${r.id}/transition`, 'POST', { stage: next, expected_version: r.version }))}>Advance to {next.toLowerCase()}</button>}
      {canExport && <><button className="button secondary small" disabled={app.busy} onClick={() => void doExport(true)}><Icon name="download"/>Draft bundle</button><button className="button secondary small" disabled={app.busy || r.blockers.length > 0 || r.approvals.filter(a => a.decision === 'APPROVED').length < 2 || !['PILOT','LIMITED','BROAD'].includes(r.stage)} onClick={() => void doExport(false)}><Icon name="download"/>Approved handoff</button></>}
      {canPlan && r.stage !== 'CANCELLED' && <button className="button secondary small" disabled={app.busy} onClick={() => void app.action('Rollout paused. New reviewed plan required to resume.', () => api(`/rollouts/${r.id}/transition`, 'POST', { stage: 'PAUSED', expected_version: r.version }))}>Pause</button>}
    </div>
    {app.user.role === 'CLOUD_ENGINEER' && r.delivery_state !== 'NOT_EXPORTED' && <div style={{ marginTop: 18, borderTop: '1px solid var(--line)', paddingTop: 14 }}><p className="text-small muted">Mock pipeline results only. These actions make no cloud changes.</p><div className="button-row">{['VERIFIED','FAILED','DRIFTED'].map(status => <button className="button secondary small" key={status} disabled={app.busy || r.blockers.length > 0} onClick={() => void app.action(`Mock ${status.toLowerCase()} receipt recorded.`, () => api(`/rollouts/${r.id}/mock-receipts`, 'POST', { event_id: crypto.randomUUID(), manifest_digest: r.manifest_digest, implementation_digest: status === 'DRIFTED' ? '0'.repeat(64) : r.manifest.implementation_digest, scope_id: r.manifest.scope_id, observed_at: new Date().toISOString(), status, provenance: 'DEMO' }))}>Record mock {status.toLowerCase()}</button>)}</div></div>}
  </Panel>;
}

export function RolloutsPage() {
  const app = useApp();
  return <><Heading eyebrow="Governed delivery" title="Progressive rollout & handoff" subtitle="Two distinct reviewers approve an exact change. Cloud Engineering owns deployment execution."/>
    <Notice>Exported is not enforced. Pipeline receipts are mock observations; fresh matching evidence is required for verified demo coverage.</Notice>
    {app.rollouts.length ? app.rollouts.map(r => <RolloutCard key={r.id} r={r}/>) : <Panel title="Rollout packages"><Empty title="No rollout packages yet">Open a control, run an impact assessment, then select Prepare rollout.</Empty></Panel>}
  </>;
}

export function AuditPage() {
  const app = useApp(); const [query, setQuery] = useState('');
  const rows = app.audit.filter(a => `${a.action} ${a.actor_id} ${a.object_id}`.toLowerCase().includes(query.toLowerCase()));
  return <><Heading eyebrow="Evidence & accountability" title="Audit trail" subtitle="Append-only application events. Database protections are not a claim of administrator-proof retention."/>
    <div className="toolbar"><input className="input" aria-label="Search audit events" placeholder="Search action, actor, or object…" value={query} onChange={e => setQuery(e.target.value)}/><span className="text-small muted">{rows.length} events loaded</span></div>
    <Panel title="Engineering decisions" subtitle="Tokens and credentials are never included" bare><div className="table-wrap"><table><thead><tr><th>Event</th><th>Actor / Scope</th><th>Evidence</th><th>Time</th></tr></thead><tbody>{rows.map(a => <tr key={a.id}><td><strong>{a.action.toLowerCase().replaceAll('_',' ')}</strong><small>{a.object_id}</small></td><td>{a.actor_id}<small>{a.scope_id || 'Session'}</small></td><td><details><summary className="subtle-link">View event details</summary><pre className="code">{JSON.stringify(a.detail,null,2)}</pre></details></td><td>{date(a.created_at)}</td></tr>)}</tbody></table></div></Panel>
  </>;
}

export function DemoPage() {
  const app = useApp();
  return <><Heading eyebrow="Local-only tools" title="Demo workspace" subtitle="These tools replace synthetic fixture data only. They cannot touch cloud infrastructure."/>
    <Panel title="Inventory scenarios" subtitle={`${app.inventory.label} · collected ${date(app.inventory.collected_at)}`}>
      <p className="description">Start with the initial risk fixture to see blockers. Load the remediated fixture to demonstrate review, export, and mock verification. Every replacement creates a new immutable snapshot and makes older assessment packages stale.</p>
      <div className="button-row">{['baseline','ready'].map(scenario => <button key={scenario} className="button secondary" disabled={app.busy || app.user.role !== 'ADMIN'} onClick={() => void app.action('New synthetic snapshot created. Reassess affected controls.', () => api('/demo/inventory','POST',{scenario}))}>{scenario === 'ready' ? 'Load remediated fixture' : 'Load initial risk fixture'}</button>)}</div>
      {app.user.role !== 'ADMIN' && <p className="text-small muted">Select the Demo administrator identity to change fixtures.</p>}
    </Panel>
    <Panel title="Expiry reconciliation"><p className="description">Effective expiry is evaluated on every read. This idempotent task records expiry and pending native cleanup without deploying anything.</p><button className="button secondary" disabled={app.busy || app.user.role !== 'ADMIN'} onClick={() => void app.action('Expiry reconciled. Cloud mutations: zero.', () => api('/reconcile','POST'))}>Run reconciliation</button></Panel>
    <Panel title="Five-minute demonstration"><ol className="description" style={{ paddingLeft: 20 }}><li>As Control engineer, inspect the initial Azure assessment and its blockers.</li><li>As Demo administrator, load the remediated fixture.</li><li>As Control engineer, reassess Azure and prepare a rollout with a recovery plan.</li><li>As Security approver and Cloud engineer, record two separate approvals.</li><li>As Control engineer, advance through observation to pilot and export the approved bundle.</li><li>As Cloud engineer, record a mock verified receipt. Inspect coverage on the dashboard.</li><li>Record a mock drifted receipt or create a new revision. Verified coverage must fall.</li></ol></Panel>
  </>;
}
