/**
 * AgentStatusPanel - Glassmorphism UI for 20 Autonomous Agents
 * 
 * Displays agents as glowing nodes with Framer Motion animations.
 * Active agents pulse, and their current "thoughts" stream in terminal readout.
 */

'use client';

import React, { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface AgentNode {
  id: string;
  name: string;
  domain: string;
  status: 'idle' | 'observing' | 'thinking' | 'acting' | 'signaling' | 'error';
  lastActivity: number;
  thoughts?: string;
  confidence?: number;
}

interface AgentStatusPanelProps {
  agents: AgentNode[];
  selectedAgent?: string;
  onAgentSelect?: (agentId: string) => void;
  maxThoughts?: number;
}

const STATUS_COLORS = {
  idle: { glow: '#4b5563', bg: '#1f2937', text: '#9ca3af' },
  observing: { glow: '#3b82f6', bg: '#1e3a5f', text: '#60a5fa' },
  thinking: { glow: '#8b5cf6', bg: '#2e1065', text: '#a78bfa' },
  acting: { glow: '#f59e0b', bg: '#451a03', text: '#fbbf24' },
  signaling: { glow: '#10b981', bg: '#064e3b', text: '#34d399' },
  error: { glow: '#ef4444', bg: '#450a0a', text: '#f87171' },
};

const AGENT_GROUPS = [
  { name: 'Data Layer', agents: ['MarketDataAgent', 'OrderBookAgent', 'TradeFlowAgent'] },
  { name: 'Analysis Layer', agents: ['TechnicalAnalysisAgent', 'OrderFlowAgent', 'SentimentAgent'] },
  { name: 'Strategy Layer', agents: ['MomentumAgent', 'MeanReversionAgent', 'ArbitrageAgent'] },
  { name: 'Risk Layer', agents: ['RiskManagerAgent', 'PositionSizerAgent', 'PortfolioAgent'] },
  { name: 'Execution Layer', agents: ['ExecutionAgent', 'SmartRouterAgent', 'SlippageAgent'] },
];

export function AgentStatusPanel({
  agents,
  selectedAgent,
  onAgentSelect,
  maxThoughts = 5,
}: AgentStatusPanelProps) {
  const selectedAgentData = useMemo(() => {
    return agents.find(a => a.id === selectedAgent);
  }, [agents, selectedAgent]);

  const recentThoughts = useMemo(() => {
    return agents
      .filter(a => a.thoughts && a.thoughts.length > 0)
      .sort((a, b) => b.lastActivity - a.lastActivity)
      .slice(0, maxThoughts);
  }, [agents, maxThoughts]);

  return (
    <div className="bg-gray-900/80 backdrop-blur-xl rounded-2xl border border-gray-800 p-6 shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <span className="w-3 h-3 bg-green-500 rounded-full animate-pulse" />
          Agent Network
        </h2>
        <span className="text-xs text-gray-400 font-mono">
          {agents.filter(a => a.status !== 'idle').length}/{agents.length} Active
        </span>
      </div>

      {/* Agent Nodes Grid */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {agents.map(agent => (
          <AgentNodeComponent
            key={agent.id}
            agent={agent}
            isSelected={agent.id === selectedAgent}
            onClick={() => onAgentSelect?.(agent.id)}
          />
        ))}
      </div>

      {/* Selected Agent Details & Thoughts Stream */}
      <div className="grid grid-cols-2 gap-4">
        {/* Agent Details */}
        <AnimatePresence mode="wait">
          {selectedAgentData ? (
            <motion.div
              key={selectedAgentData.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="bg-gray-800/50 rounded-xl p-4 border border-gray-700"
            >
              <h3 className="text-lg font-semibold text-white mb-2">
                {selectedAgentData.name}
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Domain:</span>
                  <span className="text-cyan-400">{selectedAgentData.domain}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Status:</span>
                  <StatusBadge status={selectedAgentData.status} />
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Last Activity:</span>
                  <span className="text-gray-300 font-mono">
                    {formatTimestamp(selectedAgentData.lastActivity)}
                  </span>
                </div>
                {selectedAgentData.confidence !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Confidence:</span>
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-2 bg-gray-700 rounded-full overflow-hidden">
                        <motion.div
                          className="h-full bg-gradient-to-r from-cyan-500 to-green-500"
                          initial={{ width: 0 }}
                          animate={{ width: `${selectedAgentData.confidence * 100}%` }}
                          transition={{ duration: 0.3 }}
                        />
                      </div>
                      <span className="text-cyan-400 font-mono">
                        {(selectedAgentData.confidence * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          ) : (
            <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700 flex items-center justify-center">
              <p className="text-gray-500">Select an agent to view details</p>
            </div>
          )}
        </AnimatePresence>

        {/* Thoughts Terminal */}
        <div className="bg-black/60 rounded-xl p-4 border border-gray-800 font-mono text-xs overflow-hidden">
          <h3 className="text-sm font-semibold text-gray-400 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-green-500 rounded-full" />
            Agent Thoughts Stream
          </h3>
          <div className="space-y-2 h-32 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-700">
            <AnimatePresence>
              {recentThoughts.length > 0 ? (
                recentThoughts.map((agent, idx) => (
                  <motion.div
                    key={`${agent.id}-${agent.lastActivity}`}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 20 }}
                    transition={{ delay: idx * 0.05 }}
                    className="text-gray-300 border-l-2 pl-2 py-1"
                    style={{ borderColor: STATUS_COLORS[agent.status].glow }}
                  >
                    <span className="text-cyan-400">[{agent.name}]</span>{' '}
                    <span className="text-gray-400">{agent.thoughts}</span>
                  </motion.div>
                ))
              ) : (
                <div className="text-gray-600 italic">Waiting for agent signals...</div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}

function AgentNodeComponent({
  agent,
  isSelected,
  onClick,
}: {
  agent: AgentNode;
  isSelected: boolean;
  onClick: () => void;
}) {
  const colors = STATUS_COLORS[agent.status];

  return (
    <motion.button
      onClick={onClick}
      className={`relative p-3 rounded-xl border transition-all duration-200 ${
        isSelected
          ? 'border-cyan-500 bg-cyan-900/30'
          : 'border-gray-800 bg-gray-800/30 hover:border-gray-600'
      }`}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
    >
      {/* Glowing Node */}
      <div className="flex flex-col items-center gap-2">
        <motion.div
          className="relative"
          animate={{
            boxShadow: [
              `0 0 5px ${colors.glow}`,
              `0 0 20px ${colors.glow}`,
              `0 0 5px ${colors.glow}`,
            ],
          }}
          transition={{
            duration: agent.status === 'idle' ? 0 : 2,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        >
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center"
            style={{ backgroundColor: colors.bg }}
          >
            <AgentIcon status={agent.status} />
          </div>
          {/* Status Indicator Dot */}
          <div
            className="absolute -bottom-1 -right-1 w-4 h-4 rounded-full border-2 border-gray-900"
            style={{ backgroundColor: colors.glow }}
          />
        </motion.div>

        {/* Agent Name */}
        <span className="text-xs text-gray-300 font-medium truncate max-w-full">
          {agent.name.replace('Agent', '')}
        </span>

        {/* Status Label */}
        <span
          className="text-[10px] uppercase tracking-wider"
          style={{ color: colors.text }}
        >
          {agent.status}
        </span>
      </div>
    </motion.button>
  );
}

function AgentIcon({ status }: { status: AgentNode['status'] }) {
  const icons = {
    idle: (
      <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
      </svg>
    ),
    observing: (
      <svg className="w-5 h-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
      </svg>
    ),
    thinking: (
      <svg className="w-5 h-5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
    acting: (
      <svg className="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    signaling: (
      <svg className="w-5 h-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    error: (
      <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  };

  return icons[status] || icons.idle;
}

function StatusBadge({ status }: { status: AgentNode['status'] }) {
  const colors = STATUS_COLORS[status];

  return (
    <span
      className="px-2 py-1 rounded-full text-xs font-medium"
      style={{ backgroundColor: colors.bg, color: colors.text }}
    >
      {status.toUpperCase()}
    </span>
  );
}

function formatTimestamp(timestamp: number): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now.getTime() - timestamp;

  if (diff < 1000) return 'Just now';
  if (diff < 60000) return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;

  return date.toLocaleTimeString();
}

export default AgentStatusPanel;
