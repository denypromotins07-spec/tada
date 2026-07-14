/**
 * useWebSocketTelemetry - Custom React Hook for Live Agent Signals
 * 
 * Multiplexes WebSocket connections to receive live agent signals,
 * order flow metrics, and market telemetry data.
 */

import { useState, useEffect, useCallback, useRef } from 'react';

export interface AgentSignal {
  agent: string;
  signal_type: string;
  symbol: string;
  confidence: number;
  timestamp: number;
  data?: Record<string, unknown>;
}

export interface OrderFlowMetrics {
  symbol: string;
  cvd: number;
  buy_volume: number;
  sell_volume: number;
  imbalance_ratio: number;
  footprint_bars: FootprintBar[];
}

export interface FootprintBar {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  buy_volume: number;
  sell_volume: number;
}

export interface MarketRegime {
  symbol: string;
  regime: string;
  volatility: number;
  liquidity: number;
  timestamp: number;
}

interface UseWebSocketTelemetryOptions {
  wsUrl?: string;
  autoReconnect?: boolean;
  reconnectInterval?: number;
  enabled?: boolean;
}

interface UseWebSocketTelemetryReturn {
  connected: boolean;
  connecting: boolean;
  error: string | null;
  signals: AgentSignal[];
  orderFlowMetrics: Record<string, OrderFlowMetrics>;
  marketRegimes: Record<string, MarketRegime>;
  agentStatuses: Record<string, AgentStatus>;
  sendMessage: (channel: string, message: unknown) => void;
  subscribe: (channel: string) => void;
  unsubscribe: (channel: string) => void;
  clearSignals: () => void;
}

interface AgentStatus {
  name: string;
  status: 'idle' | 'observing' | 'thinking' | 'acting' | 'signaling';
  lastActivity: number;
  thoughts?: string;
}

const DEFAULT_WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8080/ws';
const DEFAULT_RECONNECT_INTERVAL = 3000;

export function useWebSocketTelemetry(options: UseWebSocketTelemetryOptions = {}): UseWebSocketTelemetryReturn {
  const {
    wsUrl = DEFAULT_WS_URL,
    autoReconnect = true,
    reconnectInterval = DEFAULT_RECONNECT_INTERVAL,
    enabled = true,
  } = options;

  // Connection state
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Data state
  const [signals, setSignals] = useState<AgentSignal[]>([]);
  const [orderFlowMetrics, setOrderFlowMetrics] = useState<Record<string, OrderFlowMetrics>>({});
  const [marketRegimes, setMarketRegimes] = useState<Record<string, MarketRegime>>({});
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});

  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const channelsRef = useRef<Set<string>>(new Set([
    'agent:supervisor:signals',
    'rust:orderflow:metrics',
    'agent:status',
  ]));

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (!enabled || connecting || connected) return;

    setConnecting(true);
    setError(null);

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setConnected(true);
        setConnecting(false);
        console.log('[WebSocket] Connected to telemetry stream');

        // Subscribe to channels
        channelsRef.current.forEach(channel => {
          ws.send(JSON.stringify({ type: 'subscribe', channel }));
        });
      };

      ws.onclose = () => {
        setConnected(false);
        setConnecting(false);
        console.log('[WebSocket] Disconnected');

        if (autoReconnect) {
          reconnectTimeoutRef.current = setTimeout(connect, reconnectInterval);
        }
      };

      ws.onerror = (event) => {
        setError('WebSocket connection error');
        setConnecting(false);
        console.error('[WebSocket] Error:', event);
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          handleMessage(message);
        } catch (e) {
          console.error('[WebSocket] Failed to parse message:', e);
        }
      };

      wsRef.current = ws;
    } catch (e) {
      setError('Failed to create WebSocket connection');
      setConnecting(false);
    }
  }, [wsUrl, enabled, autoReconnect, reconnectInterval, connecting, connected]);

  // Handle incoming messages
  const handleMessage = useCallback((message: {
    type: string;
    channel: string;
    data: unknown;
  }) => {
    const { type, channel, data } = message;

    switch (channel) {
      case 'agent:supervisor:signals':
        if (type === 'signal') {
          const signal = data as AgentSignal;
          setSignals(prev => [signal, ...prev].slice(0, 100)); // Keep last 100 signals
        }
        break;

      case 'rust:orderflow:metrics':
        if (type === 'metrics') {
          const metrics = data as OrderFlowMetrics;
          setOrderFlowMetrics(prev => ({
            ...prev,
            [metrics.symbol]: metrics,
          }));
        }
        break;

      case 'agent:market:regime':
        if (type === 'regime') {
          const regime = data as MarketRegime;
          setMarketRegimes(prev => ({
            ...prev,
            [regime.symbol]: regime,
          }));
        }
        break;

      case 'agent:status':
        if (type === 'status_update') {
          const status = data as AgentStatus;
          setAgentStatuses(prev => ({
            ...prev,
            [status.name]: status,
          }));
        }
        break;

      default:
        console.log('[WebSocket] Unknown channel:', channel);
    }
  }, []);

  // Send message through WebSocket
  const sendMessage = useCallback((channel: string, message: unknown) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'publish',
        channel,
        data: message,
      }));
    } else {
      console.warn('[WebSocket] Cannot send message - not connected');
    }
  }, []);

  // Subscribe to a channel
  const subscribe = useCallback((channel: string) => {
    channelsRef.current.add(channel);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'subscribe', channel }));
    }
  }, []);

  // Unsubscribe from a channel
  const unsubscribe = useCallback((channel: string) => {
    channelsRef.current.delete(channel);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'unsubscribe', channel }));
    }
  }, []);

  // Clear all signals
  const clearSignals = useCallback(() => {
    setSignals([]);
  }, []);

  // Initialize connection when enabled
  useEffect(() => {
    if (enabled) {
      connect();
    } else {
      if (wsRef.current) {
        wsRef.current.close();
      }
      setConnected(false);
    }
  }, [enabled, connect]);

  return {
    connected,
    connecting,
    error,
    signals,
    orderFlowMetrics,
    marketRegimes,
    agentStatuses,
    sendMessage,
    subscribe,
    unsubscribe,
    clearSignals,
  };
}

// Convenience hooks for specific data types
export function useAgentSignals() {
  const { signals, connected } = useWebSocketTelemetry();
  return { signals, connected };
}

export function useOrderFlow(symbol: string) {
  const { orderFlowMetrics, connected } = useWebSocketTelemetry();
  const metrics = orderFlowMetrics[symbol];
  return { metrics, connected };
}

export function useMarketRegime(symbol: string) {
  const { marketRegimes, connected } = useWebSocketTelemetry();
  const regime = marketRegimes[symbol];
  return { regime, connected };
}

export function useAgentStatus(agentName: string) {
  const { agentStatuses, connected } = useWebSocketTelemetry();
  const status = agentStatuses[agentName];
  return { status, connected };
}

export default useWebSocketTelemetry;
