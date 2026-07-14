import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' });
const jetbrainsMono = JetBrains_Mono({ 
  subsets: ['latin'], 
  variable: '--font-mono',
});

export const metadata: Metadata = {
  title: 'QuantumHFT - Command Center',
  description: 'Institutional-Grade Autonomous Crypto Trading Bot',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} ${jetbrainsMono.variable} font-sans bg-gray-950 text-white antialiased`}>
        {/* Top Navigation Bar */}
        <nav className="fixed top-0 left-0 right-0 h-14 bg-gray-900/80 backdrop-blur-md border-b border-cyan-500/20 z-50 flex items-center justify-between px-6">
          {/* Logo */}
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">Q</span>
            </div>
            <span className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
              QuantumHFT
            </span>
          </div>
          
          {/* System Status */}
          <div className="flex items-center space-x-6 text-xs font-mono">
            <div className="flex items-center space-x-2">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              <span className="text-gray-400">Engine:</span>
              <span className="text-green-400">ONLINE</span>
            </div>
            <div className="flex items-center space-x-2">
              <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
              </svg>
              <span className="text-gray-400">NPU:</span>
              <span className="text-purple-400">ACTIVE</span>
            </div>
            <div className="flex items-center space-x-2">
              <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <span className="text-gray-400">Latency:</span>
              <span className="text-cyan-400">47μs</span>
            </div>
            <div className="flex items-center space-x-2">
              <svg className="w-4 h-4 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              <span className="text-gray-400">Memory:</span>
              <span className="text-yellow-400">8.2/16 GB</span>
            </div>
          </div>
        </nav>
        
        {/* Main Content Area */}
        <div className="pt-14 min-h-screen">
          {/* Sidebar */}
          <aside className="fixed left-0 top-14 bottom-0 w-64 bg-gray-900/50 border-r border-cyan-500/10 p-4 overflow-y-auto">
            <div className="space-y-2">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">Navigation</h3>
              <NavItem icon="📊" label="Dashboard" active />
              <NavItem icon="🤖" label="Agents" />
              <NavItem icon="📈" label="Analytics" />
              <NavItem icon="⚡" label="Execution" />
              <NavItem icon="🔧" label="Settings" />
            </div>
            
            <div className="mt-8 space-y-2">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">Active Agents</h3>
              <AgentStatus name="Market Data" status="running" />
              <AgentStatus name="Technical Analysis" status="running" />
              <AgentStatus name="Risk Management" status="running" />
              <AgentStatus name="Supervisor" status="running" />
            </div>
          </aside>
          
          {/* Main Content */}
          <main className="ml-64 p-6">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}

function NavItem({ icon, label, active = false }: { icon: string; label: string; active?: boolean }) {
  return (
    <button
      className={`w-full flex items-center space-x-3 px-3 py-2 rounded-lg transition-all duration-200 ${
        active 
          ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' 
          : 'text-gray-400 hover:bg-gray-800 hover:text-white'
      }`}
    >
      <span>{icon}</span>
      <span className="text-sm font-medium">{label}</span>
    </button>
  );
}

function AgentStatus({ name, status }: { name: string; status: string }) {
  const statusColors: Record<string, string> = {
    running: 'bg-green-500',
    paused: 'bg-yellow-500',
    stopped: 'bg-red-500',
  };
  
  return (
    <div className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-gray-800/50 cursor-pointer transition-colors">
      <span className="text-xs text-gray-400">{name}</span>
      <div className={`w-2 h-2 rounded-full ${statusColors[status] || 'bg-gray-500'} ${status === 'running' ? 'animate-pulse' : ''}`}></div>
    </div>
  );
}
