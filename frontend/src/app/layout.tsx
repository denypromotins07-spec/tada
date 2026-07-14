import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';

// =============================================================================
// FONT CONFIGURATION
// =============================================================================

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
});

// =============================================================================
// METADATA
// =============================================================================

export const metadata: Metadata = {
  title: 'HFT Trading Dashboard | Ultra-Low Latency Crypto Trading',
  description: 'Real-time HFT trading dashboard with order flow visualization, ML regime detection, and risk metrics',
  keywords: [
    'HFT',
    'trading',
    'crypto',
    'bitcoin',
    'ethereum',
    'orderflow',
    'market-making',
  ],
  authors: [{ name: 'HFT Quant Team' }],
  robots: 'noindex, nofollow', // Private dashboard
  themeColor: '#0f172a',
};

// =============================================================================
// ROOT LAYOUT
// =============================================================================

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-slate-950 text-slate-100 antialiased">
        {/* Background gradient */}
        <div className="fixed inset-0 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 pointer-events-none" />
        
        {/* Grid pattern overlay */}
        <div 
          className="fixed inset-0 opacity-[0.02] pointer-events-none"
          style={{
            backgroundImage: `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px),
                              linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)`,
            backgroundSize: '50px 50px',
          }}
        />
        
        {/* Main content */}
        <main className="relative z-10 min-h-screen">
          {children}
        </main>
      </body>
    </html>
  );
}
