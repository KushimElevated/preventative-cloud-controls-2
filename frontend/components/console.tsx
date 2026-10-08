'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { Assessment, Audit, Control, Dashboard, Exception, List, Rollout, Scope, User } from '@/lib/types';
import { Context, type AppData } from './context';
import { ControlForm, ExceptionForm, RolloutForm } from './forms';
import { AuditPage, CatalogPage, DashboardPage, DemoPage, DetailPage, ExceptionsPage, RolloutsPage } from './pages';
import { Icon, Notice } from './ui';
import AssistantWorkspace from './assistant/workspace';

const navigation = [['dashboard','Overview'],['assistant','Engineering assistant'],['controls','Control catalog'],['exceptions','Exceptions'],['rollouts','Rollouts & handoff'],['audit','Audit trail'],['demo','Demo workspace']];
type Modal = { kind: 'control'; control?: Control } | { kind: 'exception'; control?: Control } | { kind: 'rollout'; assessment: Assessment };

export default function Console() {
  const pathname = usePathname(), parts = pathname.split('/').filter(Boolean), page = parts[0] || 'dashboard';
  const [users, setUsers] = useState<User[]>([]), [user, setUser] = useState<User | null>(null), [selected, setSelected] = useState('engineer');
  const [data, setData] = useState<AppData | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [refreshKey, setRefresh] = useState(0), [modal, setModal] = useState<Modal | null>(null);
  const [toast, setToast] = useState<{ text: string; error?: boolean } | null>(null);
  const close = useCallback(() => setModal(null), []);
  const refresh = useCallback(() => setRefresh(x => x + 1), []);
  useEffect(() => { void api<User[]>('/auth/demo-users').then(setUsers).catch(e => setError(e.message));
    if (sessionStorage.getItem('control-token')) void api<User>('/me').then(setUser).catch(() => sessionStorage.removeItem('control-token'));
  }, []);
  useEffect(() => { if (!toast) return; const id = setTimeout(() => setToast(null), toast.error ? 15000 : 6000); return () => clearTimeout(id); }, [toast]);
  useEffect(() => {
    if (!user) return;
    let active = true;
    void Promise.all([api<List<Control>>('/controls?limit=100'), api<List<Exception>>('/exceptions?limit=100'), api<List<Rollout>>('/rollouts?limit=100'), api<List<Audit>>('/audit?limit=100'), api<Dashboard>('/dashboard'), api<Scope[]>('/scopes'), api<AppData['inventory']>('/inventory')])
      .then(([controls, exceptions, rollouts, audit, metrics, scopes, inventory]) => { if (active) { setData({ controls: controls.items, exceptions: exceptions.items, rollouts: rollouts.items, audit: audit.items, metrics, scopes, inventory }); setError(''); } })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [user, refreshKey]);
  const login = async (id: string) => {
    setBusy(true);
    try {
      if (user) await api('/auth/logout', 'POST').catch(() => undefined);
      const result = await api<{ access_token: string; user: User }>('/auth/demo','POST',{ user_id: id });
      sessionStorage.setItem('control-token', result.access_token); setData(null); setUser(result.user); setSelected(id); setError('');
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const action = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    try { await fn(); setToast({ text: label }); refresh(); }
    catch (e) { setToast({ text: (e as Error).message, error: true }); }
    finally { setBusy(false); }
  };
  if (!user) return <main className="login"><div className="eyebrow">Cloud Security Control Engineering</div><h1>A workspace for prevention.</h1><p className="description">Define controls, understand impact, and prepare governed policy changes for Cloud Engineering.</p><Notice>Local demo authentication only. Identity switching demonstrates separation of duties, not production SSO.</Notice>{error && <Notice tone="error">{error}</Notice>}<label className="field"><span>Demo identity</span><select className="identity" aria-label="Demo identity" value={selected} onChange={e => setSelected(e.target.value)}>{users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label><button className="button" disabled={busy || !users.length} onClick={() => void login(selected)}>Enter workspace <Icon name="arrow"/></button></main>;
  const content = data ? (page === 'assistant' ? <AssistantWorkspace key={user.id}/> : page === 'controls' && parts[1] ? <DetailPage key={parts[1]} id={parts[1]} section={parts[2]} refreshKey={refreshKey}/> : page === 'controls' ? <CatalogPage/> : page === 'exceptions' ? <ExceptionsPage/> : page === 'rollouts' ? <RolloutsPage/> : page === 'audit' ? <AuditPage/> : page === 'demo' ? <DemoPage/> : page === 'dashboard' ? <DashboardPage/> : <Notice tone="error">Page not found. Open a section from the navigation.</Notice>) : <div className="loading">Loading governed control workspace…</div>;
  return <div className="app"><aside className="sidebar"><Link className="brand" href="/dashboard"><span className="brand-mark">c</span>Control Plane</Link><div className="nav-caption">ENGINEERING WORKSPACE</div><nav>{navigation.map(([key,label]) => <Link className={`nav-link ${page === key ? 'active' : ''}`} key={key} href={`/${key}`}><Icon name={key}/>{label}{key === 'controls' && data && <span className="nav-count">{data.controls.length}</span>}</Link>)}</nav><div className="sidebar-bottom"><strong>Preventive by design.</strong>Cloud Security owns the intent.<br/>Cloud Engineering owns execution.<div style={{ marginTop: 20 }}><span className="dot" style={{ background:'#83d7ad', display:'inline-block', marginRight:6 }}/>Local workspace · v0.1</div></div></aside>
    <div className="shell"><header className="topbar"><div className="breadcrumb">Cloud Security <span style={{ margin:'0 10px',color:'#aab9bd' }}>/</span><b>{navigation.find(([key]) => key === page)?.[1] || 'Control detail'}</b></div><div className="top-actions"><span className="demo-pill">DEMO · NO LIVE DEPLOYMENT</span><select className="identity" aria-label="Switch demo identity" disabled={busy} value={user.id} onChange={e => void login(e.target.value)}>{users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</select></div></header>
      <main className="content">{error && <Notice tone="error">{error} <button className="button secondary small" onClick={refresh}>Retry</button></Notice>}
        {data ? <Context.Provider value={{ ...data, user, busy, action, refresh, openControl: control => setModal({ kind:'control', control }), openException: control => setModal({ kind:'exception', control }), openRollout: assessment => setModal({ kind:'rollout', assessment }) }}>{content}
          {modal?.kind === 'control' && <ControlForm existing={modal.control} close={close}/>}{modal?.kind === 'exception' && <ExceptionForm control={modal.control} close={close}/>}{modal?.kind === 'rollout' && <RolloutForm assessment={modal.assessment} close={close}/>}</Context.Provider> : content}
        <footer className="footer-note"><span>Control engineering, with evidence at every step.</span><span>Synthetic data · Lists show up to 100 records · No infrastructure changes</span></footer>
      </main></div>{toast && <div role={toast.error ? 'alert' : 'status'} className={`toast ${toast.error ? 'error' : ''}`} onClick={() => setToast(null)}>{toast.text}</div>}
  </div>;
}
