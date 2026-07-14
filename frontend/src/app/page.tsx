'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import Dashboard from '@/components/Dashboard';

// =============================================================================
// WEBSOCKET PROVIDER
// =============================================================================

interface WebSocketMessage {
  type: string;
  data: any;
  timestamp: number;
}

export default function Home() {
  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState<WebSocketMessage[]>([]);
  const [latency, setLatency] = useState<number>(0);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: NodeJS.Timeout;
    let heartbeatInterval: NodeJS.Timeout;

    const connect = () => {
      const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:6379';
      
      console.log('Connecting to WebSocket:', wsUrl);
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        
        // Subscribe to HFT channels
        ws?.send(JSON.stringify({
          action: 'subscribe',
          channels: ['hft:status', 'hft:depth:*', 'hft:trades:*']
        }));

        // Start heartbeat
        heartbeatInterval = setInterval(() => {
          if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 10000);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const now = Date.now();
          
          setMessages(prev => [...prev.slice(-99), {
            type: data.type || 'unknown',
            data,
            timestamp: now,
          }]);

          // Calculate latency if this is a pong response
          if (data.type === 'pong' && data.timestamp) {
            setLatency(now - data.timestamp);
          }
        } catch (e) {
          console.error('Failed to parse message:', e);
        }
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        setIsConnected(false);
        
        if (heartbeatInterval) {
          clearInterval(heartbeatInterval);
        }

        // Reconnect after delay
        reconnectTimeout = setTimeout(connect, 3000);
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
    };

    connect();

    return () => {
      if (ws) {
        ws.close();
      }
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      if (heartbeatInterval) {
        clearInterval(heartbeatInterval);
      }
    };
  }, []);

  return (
    <div className="container mx-auto px-4 py-6">
      {/* Header */}
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-6"
      >
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-cyan-400 via-blue-500 to-purple-500 bg-clip-text text-transparent">
              HFT Trading Dashboard
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Ultra-Low Latency Crypto Trading System
            </p>
          </div>

          <div className="flex items-center gap-4">
            {/* Connection Status */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800/50 backdrop-blur-sm border border-slate-700">
              <div
                className={`w-2 h-2 rounded-full ${
                  isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'
                }`}
              />
              <span className="text-xs font-mono text-slate-300">
                {isConnected ? 'CONNECTED' : 'DISCONNECTED'}
              </span>
            </div>

            {/* Latency Display */}
            <div className="px-3 py-1.5 rounded-full bg-slate-800/50 backdrop-blur-sm border border-slate-700">
              <span className="text-xs font-mono">
                <span className="text-slate-400">LATENCY:</span>{' '}
                <span className={latency < 50 ? 'text-green-400' : latency < 100 ? 'text-yellow-400' : 'text-red-400'}>
                  {latency}ms
                </span>
              </span>
            </div>
          </div>
        </div>
      </motion.header>

      {/* Main Dashboard Grid */}
      <Dashboard isConnected={isConnected} messages={messages} />

      {/* Footer */}
      <motion.footer
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
        className="mt-6 text-center text-xs text-slate-500"
      >
        <p>
          Built with Rust Core • Nautilus Trader • Ray • Next.js
        </p>
        <p className="mt-1">
          ⚠️ For educational purposes only. Trade at your own risk.
        </p>
      </motion.footer>
    </div>
  );
}
