import type { Metadata } from 'next';
import './globals.css';
import './assistant.css';
import Console from '@/components/console';

export const metadata: Metadata = { title: 'Control Plane · Cloud Security', description: 'Governed preventive controls. Local demo only.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><Console/>{children}</body></html>;
}
