import './globals.css';
import type { Metadata } from 'next';
export const metadata: Metadata = { title: 'AI Trading Intelligence', description: 'Professional multi-asset market analysis terminal' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
