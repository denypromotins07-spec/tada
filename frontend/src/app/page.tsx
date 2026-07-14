'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import LiveChart from '../components/LiveChart';

export default function Home() {
  const [systemStats, setSystemStats] = useState({
    totalPnL: 1247.83,
    dailyPnL: 127.45,
    activeAgents: 4,
    ordersToday: 342,
    winRate: 67.8,
    avgLatency: 47,
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-3xl font-bold text-white">Command Center</h1>
          <p className="text-gray-400 mt-1">Real-time trading system monitoring</p>
        </div>
        <div className="flex items-center space-x-4">
          <button className="px-4 py-2 bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 rounded-lg hover:bg-cyan-500/20 transition-colors">
            Export Data
          </button>
          <button className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-blue-600 text-white rounded-lg hover:opacity-90 transition-opacity">
            Quick Trade
          </button>
        </div>
      </motion.div>

      {/* PnL Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Total P&L"
          value={`$${systemStats.totalPnL.toLocaleString()}`}
          change="+12.3%"
          positive={true}
          icon="💰"
        />
        <StatCard
          title="Daily P&L"
          value={`$${systemStats.dailyPnL.toLocaleString()}`}
          change="+5.7%"
          positive={true}
          icon="📊"
        />
        <StatCard
          title="Win Rate"
          value={`${systemStats.winRate}%`}
          change="+2.1%"
          positive={true}
          icon="🎯"
        />
        <StatCard
          title="Avg Latency"
          value={`${systemStats.avgLatency}μs`}
          change="-8μs"
          positive={true}
          icon="⚡"
        />
      </div>

      {/* Main Chart */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="bg-gray-900/50 border border-cyan-500/10 rounded-xl p-6"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">BTC/USDT - Real-Time</h2>
          <div className="flex items-center space-x-2">
            <span className="px-2 py-1 bg-green-500/10 text-green-400 text-xs rounded">LIVE</span>
            <span className="text-xs text-gray-400">1m candles</span>
          </div>
        </div>
        <LiveChart symbol="BTCUSDT" />
      </motion.div>

      {/* System Metrics & Active Orders */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Agent Status */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-gray-900/50 border border-cyan-500/10 rounded-xl p-6"
        >
          <h2 className="text-lg font-semibold text-white mb-4">AI Agents Status</h2>
          <div className="space-y-3">
            <AgentRow name="Market Data Agent" status="running" cpu={12.3} memory={245} />
            <AgentRow name="Technical Analysis Agent" status="running" cpu={8.7} memory={189} />
            <AgentRow name="Risk Management Agent" status="running" cpu={5.2} memory={134} />
            <AgentRow name="Supervisor Agent" status="running" cpu={15.8} memory={312} />
          </div>
        </motion.div>

        {/* Recent Activity */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-gray-900/50 border border-cyan-500/10 rounded-xl p-6"
        >
          <h2 className="text-lg font-semibold text-white mb-4">Recent Activity</h2>
          <div className="space-y-3">
            <ActivityRow
              time="12:34:56"
              type="ORDER_FILLED"
              symbol="BTCUSDT"
              side="BUY"
              amount="0.15"
              price="$42,350"
            />
            <ActivityRow
              time="12:33:21"
              type="SIGNAL_GENERATED"
              symbol="ETHUSDT"
              side="SELL"
              amount="CONFIDENCE: 0.87"
              price=""
            />
            <ActivityRow
              time="12:31:45"
              type="ORDER_CANCELLED"
              symbol="BTCUSDT"
              side="SELL"
              amount="0.08"
              price="$43,100"
            />
            <ActivityRow
              time="12:29:12"
              type="RISK_ALERT"
              symbol="PORTFOLIO"
              side=""
              amount="EXPOSURE: 67%"
              price=""
            />
          </div>
        </motion.div>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  change,
  positive,
  icon,
}: {
  title: string;
  value: string;
  change: string;
  positive: boolean;
  icon: string;
}) {
  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      className="bg-gray-900/50 border border-cyan-500/10 rounded-xl p-5"
    >
      <div className="flex items-center justify-between">
        <span className="text-2xl">{icon}</span>
        <span
          className={`text-sm font-medium ${
            positive ? 'text-green-400' : 'text-red-400'
          }`}
        >
          {change}
        </span>
      </div>
      <div className="mt-3">
        <p className="text-gray-400 text-sm">{title}</p>
        <p className="text-2xl font-bold text-white mt-1">{value}</p>
      </div>
    </motion.div>
  );
}

function AgentRow({
  name,
  status,
  cpu,
  memory,
}: {
  name: string;
  status: string;
  cpu: number;
  memory: number;
}) {
  return (
    <div className="flex items-center justify-between p-3 bg-gray-800/30 rounded-lg">
      <div className="flex items-center space-x-3">
        <div
          className={`w-2 h-2 rounded-full ${
            status === 'running' ? 'bg-green-500 animate-pulse' : 'bg-gray-500'
          }`}
        ></div>
        <span className="text-sm text-gray-300">{name}</span>
      </div>
      <div className="flex items-center space-x-4 text-xs font-mono">
        <span className="text-gray-400">CPU: {cpu}%</span>
        <span className="text-gray-400">MEM: {memory}MB</span>
      </div>
    </div>
  );
}

function ActivityRow({
  time,
  type,
  symbol,
  side,
  amount,
  price,
}: {
  time: string;
  type: string;
  symbol: string;
  side: string;
  amount: string;
  price: string;
}) {
  const typeColors: Record<string, string> = {
    ORDER_FILLED: 'text-green-400',
    SIGNAL_GENERATED: 'text-blue-400',
    ORDER_CANCELLED: 'text-yellow-400',
    RISK_ALERT: 'text-red-400',
  };

  return (
    <div className="flex items-center justify-between p-3 bg-gray-800/30 rounded-lg text-sm">
      <div className="flex items-center space-x-3">
        <span className="text-gray-500 font-mono text-xs">{time}</span>
        <span className={`font-medium ${typeColors[type] || 'text-gray-400'}`}>
          {type}
        </span>
        <span className="text-gray-300">{symbol}</span>
      </div>
      <div className="flex items-center space-x-4 text-gray-400">
        {side && <span className={side === 'BUY' ? 'text-green-400' : 'text-red-400'}>{side}</span>}
        <span>{amount}</span>
        {price && <span className="font-mono">{price}</span>}
      </div>
    </div>
  );
}
