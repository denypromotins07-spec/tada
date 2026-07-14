'use client';

import { motion } from 'framer-motion';
import { useMemo } from 'react';

// =============================================================================
// DASHBOARD COMPONENT
// =============================================================================

interface DashboardProps {
  isConnected: boolean;
  messages: Array<{ type: string; data: any; timestamp: number }>;
}

export default function Dashboard({ isConnected, messages }: DashboardProps) {
  // Calculate statistics from messages
  const stats = useMemo(() => {
    const depthUpdates = messages.filter(m => m.type === 'depthUpdate').length;
    const trades = messages.filter(m => m.type === 'aggTrade').length;
    const heartbeats = messages.filter(m => m.type === 'heartbeat').length;

    return { depthUpdates, trades, heartbeats };
  }, [messages]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Order Book Heatmap */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.1 }}
        className="lg:col-span-2 bg-slate-900/50 backdrop-blur-sm rounded-xl border border-slate-800 p-4"
      >
        <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-500" />
          Order Book Heatmap
        </h3>
        <div className="h-64 bg-slate-950/50 rounded-lg flex items-center justify-center border border-slate-800">
          <div className="text-center">
            <p className="text-slate-500 text-sm">WebGL Order Book Visualization</p>
            <p className="text-slate-600 text-xs mt-1">Real-time bid/ask heatmap with footprint charts</p>
            {isConnected && stats.depthUpdates > 0 && (
              <p className="text-green-500 text-xs mt-2 font-mono">
                Updates: {stats.depthUpdates}
              </p>
            )}
          </div>
        </div>
      </motion.div>

      {/* Live Trades / Tape */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.15 }}
        className="bg-slate-900/50 backdrop-blur-sm rounded-xl border border-slate-800 p-4"
      >
        <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-purple-500" />
          Live Trades
        </h3>
        <div className="h-64 overflow-hidden">
          <div className="space-y-1 font-mono text-xs">
            {messages
              .filter(m => m.type === 'aggTrade')
              .slice(-10)
              .reverse()
              .map((msg, i) => (
                <div
                  key={i}
                  className={`flex justify-between px-2 py-1 rounded ${
                    msg.data.is_buyer_maker
                      ? 'bg-red-500/10 text-red-400'
                      : 'bg-green-500/10 text-green-400'
                  }`}
                >
                  <span>{msg.data.price}</span>
                  <span>{msg.data.quantity}</span>
                </div>
              ))}
            {stats.trades === 0 && (
              <p className="text-slate-600 text-center py-8">Waiting for trades...</p>
            )}
          </div>
        </div>
      </motion.div>

      {/* ML Regime Indicator */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2 }}
        className="bg-slate-900/50 backdrop-blur-sm rounded-xl border border-slate-800 p-4"
      >
        <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-yellow-500" />
          ML Regime Detection
        </h3>
        <div className="space-y-3">
          <div className="bg-slate-950/50 rounded-lg p-3 border border-slate-800">
            <p className="text-xs text-slate-500 mb-1">Current Regime</p>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
              <span className="text-lg font-bold text-white">BULL</span>
            </div>
            <p className="text-xs text-slate-400 mt-1">Probability: 78.5%</p>
          </div>
          
          <div className="bg-slate-950/50 rounded-lg p-3 border border-slate-800">
            <p className="text-xs text-slate-500 mb-1">Volatility (GARCH)</p>
            <p className="text-lg font-mono text-white">0.0234</p>
            <p className="text-xs text-green-400 mt-1">↓ Low volatility regime</p>
          </div>
        </div>
      </motion.div>

      {/* Risk Metrics */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.25 }}
        className="bg-slate-900/50 backdrop-blur-sm rounded-xl border border-slate-800 p-4"
      >
        <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-red-500" />
          Risk Metrics
        </h3>
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">VaR (95%)</span>
            <span className="text-sm font-mono text-red-400">-$1,234</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">Expected Shortfall</span>
            <span className="text-sm font-mono text-orange-400">-$2,456</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">Max Drawdown</span>
            <span className="text-sm font-mono text-yellow-400">-3.45%</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">Sharpe Ratio</span>
            <span className="text-sm font-mono text-green-400">2.34</span>
          </div>
        </div>
      </motion.div>

      {/* Position Summary */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.3 }}
        className="bg-slate-900/50 backdrop-blur-sm rounded-xl border border-slate-800 p-4"
      >
        <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-500" />
          Positions
        </h3>
        <div className="space-y-3">
          <div className="bg-gradient-to-r from-green-500/10 to-emerald-500/10 rounded-lg p-3 border border-green-500/20">
            <div className="flex justify-between items-start mb-2">
              <span className="text-sm font-bold text-white">BTCUSDT</span>
              <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded">LONG</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-slate-500">Qty:</span>
                <span className="text-white ml-1">0.543</span>
              </div>
              <div>
                <span className="text-slate-500">Entry:</span>
                <span className="text-white ml-1">$42,350</span>
              </div>
              <div>
                <span className="text-slate-500">P&L:</span>
                <span className="text-green-400 ml-1">+$234.56</span>
              </div>
              <div>
                <span className="text-slate-500">Leverage:</span>
                <span className="text-white ml-1">3x</span>
              </div>
            </div>
          </div>
          
          <div className="text-center text-xs text-slate-500">
            Total Equity: <span className="text-white font-mono">$10,234.56</span>
          </div>
        </div>
      </motion.div>

      {/* System Status */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.35 }}
        className="bg-slate-900/50 backdrop-blur-sm rounded-xl border border-slate-800 p-4"
      >
        <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-500" />
          System Status
        </h3>
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">Rust Core</span>
            <span className="flex items-center gap-1 text-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
              <span className="text-green-400">Running</span>
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">Ray Cluster</span>
            <span className="flex items-center gap-1 text-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
              <span className="text-green-400">6 CPUs</span>
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">QuestDB</span>
            <span className="flex items-center gap-1 text-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
              <span className="text-green-400">Connected</span>
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">Memory Usage</span>
            <span className="text-xs font-mono text-slate-300">11.2 / 14 GB</span>
          </div>
        </div>
      </motion.div>

      {/* Recent Activity Log */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.4 }}
        className="lg:col-span-2 bg-slate-900/50 backdrop-blur-sm rounded-xl border border-slate-800 p-4"
      >
        <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-slate-500" />
          Activity Log
        </h3>
        <div className="h-32 overflow-y-auto font-mono text-xs space-y-1">
          {messages.slice(-20).reverse().map((msg, i) => (
            <div key={i} className="flex gap-2 text-slate-400">
              <span className="text-slate-600">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </span>
              <span className="text-cyan-500">{msg.type}</span>
              <span className="truncate">{JSON.stringify(msg.data).slice(0, 80)}</span>
            </div>
          ))}
          {messages.length === 0 && (
            <p className="text-slate-600 text-center py-8">Waiting for activity...</p>
          )}
        </div>
      </motion.div>
    </div>
  );
}
