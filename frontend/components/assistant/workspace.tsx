'use client';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { A2uiSurface, type ReactComponentImplementation } from '@a2ui/react/v0_9';
import { MessageProcessor, STRICT_VALIDATION, type ActionPayload } from '@a2ui/web_core/v0_9';
import { api } from '@/lib/api';
import { QUESTION, PROTOCOL, validateSurface, actionSchema, dataSchemas, type Draft, type SurfaceBundle } from '@/lib/a2ui-contract';
import type { Assessment } from '@/lib/types';
import { useApp } from '../context';
import { Dialog } from '../forms';
import { Heading, Icon, Notice } from '../ui';
import { engineeringCatalog, WorkspaceContext } from './catalog';

function HumanExceptionReview({ draft, close, submitted }: { draft: Draft; close: () => void; submitted: () => void }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const localDate = new Date(draft.suggested_exception_expiry);
  localDate.setMinutes(localDate.getMinutes() - localDate.getTimezoneOffset());
  return <Dialog title="Review the exception request" subtitle="Trusted application form · No request is submitted until you confirm." close={close}>
    <Notice>Resources: {draft.resource_ids.join(', ')} · Scope: {draft.scope_id}. The backend will recheck your identity, revision and evidence when you submit.</Notice>
    {error && <Notice tone="error">{error}</Notice>}
    <form onSubmit={async e => {
      e.preventDefault(); const f = new FormData(e.currentTarget); setBusy(true); setError('');
      try {
        await api(`/assistant/intents/${encodeURIComponent(draft.intent_id)}/confirm`, 'POST', {
          confirmed: f.get('confirmed') === 'on', justification: f.get('justification'),
          compensating_controls: f.get('compensating_controls'), risk_owner: f.get('risk_owner'),
          expires_at: new Date(String(f.get('expires_at'))).toISOString(),
        }); submitted(); close();
      } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
    }}>
      <label className="field"><span>Business and technical justification</span><textarea className="input" name="justification" minLength={15} maxLength={3000} required placeholder="Explain the dependency, impact and remediation plan."/></label>
      <label className="field"><span>Compensating controls</span><textarea className="input" name="compensating_controls" minLength={10} maxLength={3000} required placeholder="Describe controls supported by evidence; no safeguards are assumed."/></label>
      <div className="equal-columns"><label className="field"><span>Delegated risk owner</span><input className="input" name="risk_owner" minLength={3} maxLength={160} required/></label><label className="field"><span>Exception expiration</span><input className="input" type="datetime-local" name="expires_at" defaultValue={localDate.toISOString().slice(0, 16)} required/></label></div>
      <label className="checkbox-row"><input type="checkbox" name="confirmed" required/><span>I reviewed this request. Submission requests review; it does not approve an exception or change cloud enforcement.</span></label>
      <div className="dialog-actions"><button type="button" className="button secondary" disabled={busy} onClick={close}>Cancel draft</button><button className="button" disabled={busy}>Confirm and submit request</button></div>
    </form>
  </Dialog>;
}

function GeneratedSurface({ bundle, onAction }: { bundle: SurfaceBundle; onAction: (action: ActionPayload) => Promise<void> }) {
  const [processor, setProcessor] = useState<MessageProcessor<ReactComponentImplementation> | null>(null);
  const [error, setError] = useState('');
  const handler = useRef(onAction); handler.current = onAction;
  useEffect(() => {
    const p = new MessageProcessor<ReactComponentImplementation>([engineeringCatalog], a => handler.current(a), { version: PROTOCOL, validationConfig: STRICT_VALIDATION });
    try { p.processMessages(bundle.messages); setProcessor(p); setError(''); }
    catch { setError('This surface could not be validated. Reopen the workspace to load trusted evidence.'); }
    return () => p.dispose();
  }, [bundle]);
  const surface = processor?.getSurface(bundle.surface_id);
  if (error) return <Notice tone="error">{error}</Notice>;
  return surface ? <A2uiSurface surface={surface}/> : <div className="loading">Validating the engineering workspace…</div>;
}

export default function AssistantWorkspace({ controlId = 'azure-search', scopeId = 'az-prod' }: { controlId?: string; scopeId?: string }) {
  const app = useApp();
  const [question, setQuestion] = useState(QUESTION), [scope, setScope] = useState(scopeId);
  const [bundle, setBundle] = useState<SurfaceBundle | null>(null), [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const epoch = useRef(0);
  const closeDraft = useCallback(() => setDraft(null), []);
  const load = async (target = scope, prompt = question) => {
    const sequence = ++epoch.current; setBusy(true); setError('');
    try {
      const result = validateSurface(await api<unknown>('/assistant/surfaces', 'POST', { question: prompt, control_id: controlId, scope_id: target }));
      if (sequence === epoch.current) { setBundle(result); setScope(target); }
    } catch (e) { if (sequence === epoch.current) { setError((e as Error).message); setBundle(null); } }
    finally { if (sequence === epoch.current) setBusy(false); }
  };
  useEffect(() => { void load(scopeId, QUESTION); return () => { ++epoch.current; }; }, [controlId, scopeId]); // Explicit queries and scope selection drive subsequent updates.
  const onAction = async (event: ActionPayload) => {
    if (!bundle || busy || event.surfaceId !== bundle.surface_id) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const action = actionSchema.parse({ name: event.name, context: event.context });
      const response = await api<{ assessment_id: string } & Draft>('/assistant/commands', 'POST', {
        name: action.name, assessment_id: bundle.assessment_id, expected_revision: bundle.expected_revision,
        evidence_digest: bundle.evidence_digest, ...(action.name === 'draft_exception' ? action.context : {}),
      });
      if (action.name === 'draft_exception') setDraft(response);
      if (action.name === 'prepare_handoff') app.openRollout(await api<Assessment>(`/assessments/${encodeURIComponent(response.assessment_id)}`));
      if (action.name === 'refresh_assessment') { await load(); app.refresh(); setNotice('Assessment refreshed from current domain evidence.'); }
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const gateNode = bundle?.messages[1].updateComponents.components.find(n => n.component === 'ApprovalGate');
  const gate = gateNode && 'data' in gateNode ? dataSchemas.ApprovalGate.parse(gateNode.data) : null;
  return <div className="assistant-workspace">
    <Heading eyebrow="Control engineering / Interactive workspace" title="From question to governed decision." subtitle="A contextual Control Engineering Assistant, grounded in your control catalog and assessment evidence."><Link className="button secondary" href={`/controls/${encodeURIComponent(controlId)}`}>Conventional view <Icon name="arrow"/></Link></Heading>
    <div className="assistant-query"><div className="assistant-query-heading"><span className="assistant-symbol"><Icon/></span><span>Explore a security question</span><span className="demo-pill">DETERMINISTIC · NO AI REQUIRED</span></div><form onSubmit={e => { e.preventDefault(); void load(); }}><label className="sr-only" htmlFor="engineering-question">Security question</label><textarea id="engineering-question" value={question} maxLength={1000} minLength={5} required onChange={e => setQuestion(e.target.value)}/><button className="button" disabled={busy}>Explore impact <Icon name="arrow"/></button></form><p>Azure AI Search demonstration · A2UI {PROTOCOL} · Synthetic evidence · No infrastructure changes</p></div>
    {error && <Notice tone="error">{error} <button className="button secondary small" disabled={busy} onClick={() => void load(scope, QUESTION)}>Reload supported assessment</button></Notice>}
    {notice && <div role="status"><Notice>{notice}</Notice></div>}
    {bundle && gate && <><div className="assistant-status"><span><i className="dot"/>Evidence-backed workspace</span><span>{gate.current ? 'Current assessment' : 'Stale assessment'} · {gate.ready && gate.current ? 'Ready for review' : 'Review gaps before handoff'}</span>{busy && <span role="status">Updating…</span>}</div>
      {!gate.current && <Notice tone="warning">This assessment is stale. Its historical findings are shown for context; refresh before making a decision. {gate.stale_reasons.join(' · ')}</Notice>}
      <WorkspaceContext.Provider value={{ busy: busy || app.busy, gate, selectScope: target => void load(target) }}><GeneratedSurface bundle={bundle} onAction={onAction}/></WorkspaceContext.Provider></>}
    {!bundle && busy && <div className="loading">Gathering authorized control and assessment evidence…</div>}
    {draft && <HumanExceptionReview draft={draft} close={closeDraft} submitted={() => { setNotice('Exception requested. Security review and native exemption application are still required.'); app.refresh(); void load(); }}/>}
  </div>;
}
