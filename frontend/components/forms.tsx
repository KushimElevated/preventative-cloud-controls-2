'use client';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from '@/lib/api';
import type { Assessment, Control, Exception, Rollout } from '@/lib/types';
import { useApp } from './context';
import { Notice } from './ui';

export function Dialog({ title, subtitle, close, children }: { title: string; subtitle: string; close: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    ref.current?.querySelector<HTMLElement>('input, textarea, select, button')?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
      if (e.key === 'Tab') {
        const items = Array.from(ref.current?.querySelectorAll<HTMLElement>('input,textarea,select,button') || []).filter(x => !x.hasAttribute('disabled'));
        const first = items[0], last = items.at(-1);
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); previous?.focus(); };
  }, [close]);
  return <div className="dialog-backdrop"><div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-heading" ref={ref}><h2 id="dialog-heading">{title}</h2><p className="subtitle">{subtitle}</p>{children}</div></div>;
}
export function ControlForm({ existing, close }: { existing?: Control; close: () => void }) {
  const app = useApp();
  const [template, setTemplate] = useState(existing?.implementation.template_id || 'azure-search-public-access-v1');
  return <Dialog title={existing ? 'Create a new revision' : 'Define a preventive control'} subtitle="Start with intent. Implementation is a separate, versioned record." close={close}>
    <form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); const data = Object.fromEntries(f.entries());
      void app.action(existing ? 'Revision created. Previous approval evidence is now stale.' : 'Control created.', async () => {
        await api(existing ? `/controls/${existing.id}/revisions` : '/controls', 'POST', { ...data, ...(existing ? { expected_revision: existing.latest_revision } : {}) }); close();
      }); }}>
      <label className="field"><span>Control name</span><input name="name" className="input" required minLength={5} maxLength={160} defaultValue={existing?.name}/></label>
      <label className="field"><span>Security objective</span><textarea name="objective" className="input" required minLength={15} defaultValue={existing?.objective}/></label>
      <label className="field"><span>Rationale</span><textarea name="rationale" className="input" required minLength={10} defaultValue={existing?.rationale}/></label>
      <div className="equal-columns"><label className="field"><span>Supported implementation</span><select className="input" name="template_id" value={template} onChange={e => setTemplate(e.target.value)}><option value="azure-search-public-access-v1">Azure AI Search guardrail</option><option value="aws-s3-account-bpa-v1">AWS account BPA protection</option></select></label>
      <label className="field"><span>Owning scope</span><select className="input" name="scope_id" defaultValue={existing?.scope_id || 'az-prod'}>{app.scopes.filter(s => s.provider === (template.startsWith('azure') ? 'AZURE' : 'AWS') && (!existing || s.id === existing.scope_id)).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label></div>
      <div className="equal-columns"><label className="field"><span>Security owner</span><input className="input" name="security_owner" required minLength={2} defaultValue={existing?.security_owner || 'Cloud Security'}/></label><label className="field"><span>Engineering owner</span><input className="input" name="engineering_owner" required minLength={2} defaultValue={existing?.engineering_owner || 'Cloud Engineering'}/></label></div>
      <label className="field"><span>Severity</span><select name="severity" className="input" defaultValue={existing?.severity || 'HIGH'}><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select></label>
      <label className="field"><span>Source evidence</span><input className="input" name="evidence" required minLength={5} defaultValue={existing?.evidence || 'Synthetic local demonstration'}/></label>
      <label className="field"><span>Reason for this change</span><input className="input" name="change_reason" required minLength={5} placeholder="What changed and why?"/></label>
      <div className="dialog-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button className="button" disabled={app.busy}>{existing ? 'Create revision' : 'Create control'}</button></div>
    </form>
  </Dialog>;
}
export function ExceptionForm({ control, close }: { control?: Control; close: () => void }) {
  const app = useApp(); const [cid, setCid] = useState(control?.id || app.controls[0]?.id || '');
  const selected = app.controls.find(c => c.id === cid);
  const resources = app.inventory.resources.filter(r => selected && r.provider === selected.provider && r.type === (selected.provider === 'AZURE' ? 'Microsoft.Search/searchServices' : 'AWS::S3::Bucket'));
  return <Dialog title="Request a time-bound exception" subtitle="Governance approval and native enforcement are tracked separately." close={close}>
    <form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget);
      void app.action('Exception requested. It is not yet an effective exemption.', async () => {
        await api<Exception>('/exceptions', 'POST', { control_id: cid, scope_id: selected?.scope_id, resource_ids: f.getAll('resource_ids'), justification: f.get('justification'), compensating_controls: f.get('compensating_controls'), risk_owner: f.get('risk_owner'), expires_at: new Date(String(f.get('expires_at'))).toISOString() }); close();
      }); }}>
      <label className="field"><span>Control</span><select className="input" value={cid} onChange={e => setCid(e.target.value)}>{app.controls.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      {selected?.provider === 'AWS' && <Notice tone="warning">Bucket-level exceptions cannot bypass account protection. This template records the request as unsupported.</Notice>}
      <div className="field"><span>Resources</span><div className="checklist">{resources.map(r => <label key={r.id} className="checkbox-row"><input type="checkbox" name="resource_ids" value={r.id}/>{r.name} <small className="muted">{r.scope_id}</small></label>)}</div></div>
      <label className="field"><span>Business and technical justification</span><textarea className="input" name="justification" minLength={15} required/></label>
      <label className="field"><span>Compensating controls</span><textarea className="input" name="compensating_controls" minLength={10} required/></label>
      <div className="equal-columns"><label className="field"><span>Delegated risk owner</span><input className="input" name="risk_owner" minLength={3} required/></label><label className="field"><span>Expiration (local time, maximum 90 days)</span><input className="input" name="expires_at" type="datetime-local" required/></label></div>
      <div className="dialog-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button className="button" disabled={app.busy || !cid}>Submit request</button></div>
    </form>
  </Dialog>;
}
export function RolloutForm({ assessment, close }: { assessment: Assessment; close: () => void }) {
  const app = useApp();
  return <Dialog title="Prepare a rollout package" subtitle="The manifest binds the assessed revision, target scope, exceptions, and recovery plan." close={close}>
    <Notice tone={assessment.report.ready && assessment.current ? '' : 'warning'}>{assessment.report.ready && assessment.current ? 'Assessment is ready for review. Two distinct approvals will be required.' : 'You may record the plan, but readiness blockers prevent approval and export.'}</Notice>
    <form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); void app.action('Rollout package created. Open Rollouts to review it.', async () => {
      await api<Rollout>('/rollouts', 'POST', { assessment_id: assessment.id, rollback: f.get('rollback'), reason: f.get('reason') }); close();
    }); }}>
      <label className="field"><span>Change rationale</span><textarea name="reason" className="input" required minLength={10} defaultValue="Pilot the reviewed preventive control in the assessed scope."/></label>
      <label className="field"><span>Cloud Engineering rollback and recovery runbook</span><textarea name="rollback" className="input" minLength={30} required placeholder="Specify previous known-good assignment, review authority, rollback steps, and application recovery checks."/></label>
      <div className="dialog-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button className="button" disabled={app.busy}>Create package</button></div>
    </form>
  </Dialog>;
}
