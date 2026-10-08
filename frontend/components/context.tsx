'use client';
import { createContext, useContext } from 'react';
import type { Assessment, Audit, Control, Dashboard, Exception, Resource, Rollout, Scope, User } from '@/lib/types';

export type AppData = {
  controls: Control[]; exceptions: Exception[]; rollouts: Rollout[]; audit: Audit[]; metrics: Dashboard;
  scopes: Scope[]; inventory: { id: string; label: string; collected_at: string; resources: Resource[] };
};
export type AppContext = AppData & {
  user: User; busy: boolean;
  action: (label: string, fn: () => Promise<unknown>) => Promise<void>;
  refresh: () => void;
  openControl: (control?: Control) => void;
  openException: (control?: Control) => void;
  openRollout: (assessment: Assessment) => void;
};
export const Context = createContext<AppContext | null>(null);
export function useApp() { const ctx = useContext(Context); if (!ctx) throw new Error('App context missing'); return ctx; }
