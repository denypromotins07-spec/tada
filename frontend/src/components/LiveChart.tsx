'use client';

import { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, ISeriesApi, CandlestickData } from 'lightweight-charts';

interface LiveChartProps {
  symbol: string;
}

export default function LiveChart({ symbol }: LiveChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const [currentPrice, setCurrentPrice] = useState<number>(42350.00);
  const [priceChange, setPriceChange] = useState<number>(1.23);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Create chart with cyberpunk theme
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 400,
      layout: {
        background: { type: 'solid', color: '#0B0F19' },
        textColor: '#94A3B8',
      },
      grid: {
        vertLines: { color: 'rgba(6, 182, 212, 0.1)' },
        horzLines: { color: 'rgba(6, 182, 212, 0.1)' },
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: 'rgba(6, 182, 212, 0.5)',
          style: 2,
          labelBackgroundColor: '#06B6D4',
        },
        horzLine: {
          color: 'rgba(6, 182, 212, 0.5)',
          style: 2,
          labelBackgroundColor: '#06B6D4',
        },
      },
      rightPriceScale: {
        borderColor: 'rgba(6, 182, 212, 0.3)',
      },
      timeScale: {
        borderColor: 'rgba(6, 182, 212, 0.3)',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    // Create candlestick series with neon colors
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10B981',
      downColor: '#EF4444',
      borderUpColor: '#10B981',
      borderDownColor: '#EF4444',
      wickUpColor: '#10B981',
      wickDownColor: '#EF4444',
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;

    // Generate initial data (last 100 candles)
    const initialData = generateInitialData();
    candleSeries.setData(initialData);

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chart) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener('resize', handleResize);

    // Simulate real-time updates
    const updateInterval = setInterval(() => {
      simulateRealTimeUpdate(candleSeries);
    }, 1000);

    return () => {
      window.removeEventListener('resize', handleResize);
      clearInterval(updateInterval);
      chart.remove();
    };
  }, []);

  function generateInitialData(): CandlestickData[] {
    const data: CandlestickData[] = [];
    const now = Math.floor(Date.now() / 1000);
    let price = 42000;

    for (let i = 100; i >= 0; i--) {
      const time = now - i * 60 as any;
      const volatility = 50 + Math.random() * 100;
      const change = (Math.random() - 0.5) * volatility;
      const open = price;
      const close = price + change;
      const high = Math.max(open, close) + Math.random() * volatility * 0.5;
      const low = Math.min(open, close) - Math.random() * volatility * 0.5;

      data.push({
        time,
        open,
        high,
        low,
        close,
      });

      price = close;
    }

    setCurrentPrice(price);
    return data;
  }

  function simulateRealTimeUpdate(series: ISeriesApi<'Candlestick'>) {
    if (!candleSeriesRef.current) return;

    const lastBar = {
      time: Math.floor(Date.now() / 1000) as any,
      open: currentPrice,
      high: currentPrice + Math.random() * 20,
      low: currentPrice - Math.random() * 20,
      close: currentPrice + (Math.random() - 0.5) * 30,
    };

    const newPrice = lastBar.close;
    const change = ((newPrice - currentPrice) / currentPrice) * 100;

    setCurrentPrice(newPrice);
    setPriceChange(change);

    series.update(lastBar);
  }

  return (
    <div className="relative">
      {/* Price Overlay */}
      <div className="absolute top-4 left-4 z-10 flex items-center space-x-4">
        <div className="text-2xl font-bold text-white">
          ${currentPrice.toFixed(2)}
        </div>
        <div
          className={`px-2 py-1 rounded text-sm font-medium ${
            priceChange >= 0
              ? 'bg-green-500/20 text-green-400'
              : 'bg-red-500/20 text-red-400'
          }`}
        >
          {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
        </div>
      </div>

      {/* Volume bars toggle */}
      <div className="absolute top-4 right-4 z-10 flex items-center space-x-2">
        <button className="px-3 py-1 bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 text-xs rounded hover:bg-cyan-500/20 transition-colors">
          Indicators
        </button>
        <button className="px-3 py-1 bg-purple-500/10 border border-purple-500/30 text-purple-400 text-xs rounded hover:bg-purple-500/20 transition-colors">
          Depth
        </button>
      </div>

      {/* Chart Container */}
      <div
        ref={chartContainerRef}
        className="w-full"
        style={{ height: '400px' }}
      />
    </div>
  );
}
