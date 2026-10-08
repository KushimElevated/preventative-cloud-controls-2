'use client';
import type { ReactNode } from 'react';

export function Icon({ name = 'shield' }: { name?: string }) {
  const paths: Record<string, ReactNode> = {
    shield: <><path d="M12 3 20 6v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/></>,
    dashboard: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    controls: <><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h3"/></>,
    exceptions: <><path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5m0 3h.01"/></>,
    rollouts: <><path d="M5 4v15h14M5 14l5-5 4 3 6-8M16 4h4v4"/></>,
    audit: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/></>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6"/>,
    plus: <path d="M12 5v14M5 12h14"/>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/></>,
  };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.shield}</svg>;
}
export function Badge({ value }: { value: string }) {
  const good = ['COMPLIANT','READY','APPROVED','VERIFIED','EFFECTIVE','APPLIED','BROAD'].includes(value);
  const bad = ['NON_COMPLIANT','EXPIRED','REJECTED','FAILED','DRIFTED','REVOKED','BLOCKED'].includes(value);
  const warn = ['UNKNOWN','PENDING','REQUESTED','APPROVED_UNAPPLIED','REMOVAL_PENDING','SECURITY_REVIEW','UNSUPPORTED','PAUSED'].includes(value);
  return <span className={`badge ${good ? 'good' : bad ? 'bad' : warn ? 'warn' : 'blue'}`}><i className="dot"/>{value.toLowerCase().replaceAll('_', ' ')}</span>;
}
export function Provider({ value }: { value: string }) {
  return <span className={`provider ${value === 'AWS' ? 'aws' : ''}`}><i>{value === 'AWS' ? 'a' : 'A'}</i>{value === 'AWS' ? 'AWS' : 'Azure'}</span>;
}
export function Panel({ title, subtitle, action, children, bare = false }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode; bare?: boolean }) {
  return <section className="panel"><div className="panel-header"><div><h2>{title}</h2>{subtitle && <small>{subtitle}</small>}</div>{action}</div><div className={bare ? '' : 'panel-body'}>{children}</div></section>;
}
export function Metric({ label, value, note, tone = '' }: { label: string; value: ReactNode; note: string; tone?: string }) {
  return <div className="metric"><div className="metric-label">{label}<Icon name="dashboard"/></div><div className={`metric-value ${tone}`}>{value}</div><div className="metric-note">{note}</div></div>;
}
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><Icon/><strong>{title}</strong>{children}</div>;
}
export function Heading({ eyebrow, title, subtitle, children }: { eyebrow: string; title: string; subtitle: string; children?: ReactNode }) {
  return <div className="page-heading"><div className="control-title"><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p className="subtitle">{subtitle}</p></div>{children}</div>;
}
export function Notice({ children, tone = '' }: { children: ReactNode; tone?: string }) {
  return <div className={`notice ${tone}`}><Icon name={tone === 'warning' || tone === 'error' ? 'exceptions' : 'shield'}/><div>{children}</div></div>;
}
export function date(value: string) { return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
