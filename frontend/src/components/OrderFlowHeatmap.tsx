/**
 * OrderFlowHeatmap - High-Performance Canvas/WebGL Component
 * 
 * Renders Footprint charts and Volume Profile in real-time using
 * requestAnimationFrame for 60fps performance.
 */

import React, { useRef, useEffect, useMemo, useCallback } from 'react';

interface FootprintBar {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  buy_volume: number;
  sell_volume: number;
  price_levels?: Array<{
    price: number;
    buy_vol: number;
    sell_vol: number;
  }>;
}

interface VolumeProfile {
  levels: Array<{
    price: number;
    volume: number;
    buy_volume: number;
    sell_volume: number;
  }>;
  poc: number; // Point of Control
  value_area_high: number;
  value_area_low: number;
}

interface OrderFlowHeatmapProps {
  footprintBars: FootprintBar[];
  volumeProfile?: VolumeProfile;
  width?: number;
  height?: number;
  colorScheme?: 'cyberpunk' | 'professional' | 'dark';
  showVolumeProfile?: boolean;
  autoScale?: boolean;
}

const CYBERPUNK_COLORS = {
  background: '#0a0a0f',
  grid: '#1a1a2e',
  buy: '#00ff88',
  sell: '#ff0066',
  buyWeak: 'rgba(0, 255, 136, 0.3)',
  sellWeak: 'rgba(255, 0, 102, 0.3)',
  text: '#e0e0e0',
  textDim: '#666680',
  highlight: '#00ffff',
  poc: '#ffff00',
  valueArea: 'rgba(255, 255, 0, 0.1)',
};

const PROFESSIONAL_COLORS = {
  background: '#ffffff',
  grid: '#e0e0e0',
  buy: '#22c55e',
  sell: '#ef4444',
  buyWeak: 'rgba(34, 197, 94, 0.3)',
  sellWeak: 'rgba(239, 68, 68, 0.3)',
  text: '#1f2937',
  textDim: '#9ca3af',
  highlight: '#3b82f6',
  poc: '#f59e0b',
  valueArea: 'rgba(245, 158, 11, 0.1)',
};

export function OrderFlowHeatmap({
  footprintBars,
  volumeProfile,
  width = 800,
  height = 400,
  colorScheme = 'cyberpunk',
  showVolumeProfile = true,
  autoScale = true,
}: OrderFlowHeatmapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationFrameRef = useRef<number>();
  const lastRenderTimeRef = useRef<number>(0);

  const colors = useMemo(() => {
    return colorScheme === 'cyberpunk' ? CYBERPUNK_COLORS : PROFESSIONAL_COLORS;
  }, [colorScheme]);

  // Calculate price range from footprint bars
  const priceRange = useMemo(() => {
    if (!footprintBars || footprintBars.length === 0) {
      return { min: 0, max: 0, range: 0 };
    }

    let min = Infinity;
    let max = -Infinity;

    footprintBars.forEach(bar => {
      if (bar.low < min) min = bar.low;
      if (bar.high > max) max = bar.high;
    });

    const padding = (max - min) * 0.1;
    return {
      min: min - padding,
      max: max + padding,
      range: (max + padding) - (min - padding),
    };
  }, [footprintBars]);

  // Calculate volume scale
  const volumeScale = useMemo(() => {
    if (!footprintBars || footprintBars.length === 0) {
      return { max: 0 };
    }

    let maxVol = 0;
    footprintBars.forEach(bar => {
      const totalVol = bar.buy_volume + bar.sell_volume;
      if (totalVol > maxVol) maxVol = totalVol;
    });

    return { max: maxVol || 1 };
  }, [footprintBars]);

  // Render function
  const render = useCallback((timestamp: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Limit to 60fps
    const elapsed = timestamp - lastRenderTimeRef.current;
    if (elapsed < 16.67) {
      animationFrameRef.current = requestAnimationFrame(render);
      return;
    }
    lastRenderTimeRef.current = timestamp;

    // Clear canvas
    ctx.fillStyle = colors.background;
    ctx.fillRect(0, 0, width, height);

    // Draw grid
    drawGrid(ctx, width, height, colors);

    // Draw volume profile on the right
    if (showVolumeProfile && volumeProfile) {
      drawVolumeProfile(ctx, volumeProfile, width, height, priceRange, volumeScale, colors);
    }

    // Draw footprint heatmap
    if (footprintBars && footprintBars.length > 0) {
      drawFootprintHeatmap(ctx, footprintBars, width, height, priceRange, volumeScale, colors);
    }

    // Draw price labels
    drawPriceLabels(ctx, width, height, priceRange, colors);

    animationFrameRef.current = requestAnimationFrame(render);
  }, [width, height, footprintBars, volumeProfile, showVolumeProfile, priceRange, volumeScale, colors]);

  // Start/stop animation loop
  useEffect(() => {
    animationFrameRef.current = requestAnimationFrame(render);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [render]);

  return (
    <div className="relative rounded-lg overflow-hidden border border-gray-800">
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        className="block"
        style={{ width: `${width}px`, height: `${height}px` }}
      />
      <div className="absolute top-2 left-2 text-xs text-gray-400 font-mono">
        Order Flow • {footprintBars?.length || 0} bars
      </div>
    </div>
  );
}

function drawGrid(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  colors: typeof CYBERPUNK_COLORS
) {
  ctx.strokeStyle = colors.grid;
  ctx.lineWidth = 0.5;

  // Vertical lines (time)
  const timeDivisions = 10;
  for (let i = 0; i <= timeDivisions; i++) {
    const x = (i / timeDivisions) * width;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }

  // Horizontal lines (price)
  const priceDivisions = 8;
  for (let i = 0; i <= priceDivisions; i++) {
    const y = (i / priceDivisions) * height;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
}

function drawFootprintHeatmap(
  ctx: CanvasRenderingContext2D,
  bars: FootprintBar[],
  width: number,
  height: number,
  priceRange: { min: number; max: number; range: number },
  volumeScale: { max: number },
  colors: typeof CYBERPUNK_COLORS
) {
  const chartWidth = width * 0.85; // Leave room for volume profile
  const barWidth = Math.max(2, chartWidth / bars.length - 1);

  bars.forEach((bar, barIndex) => {
    const x = (barIndex / bars.length) * chartWidth;

    // Draw price levels within each bar
    if (bar.price_levels && bar.price_levels.length > 0) {
      bar.price_levels.forEach(level => {
        const y = priceToY(level.price, priceRange, height);
        const levelHeight = Math.max(2, height / 50); // Minimum height per level

        // Buy volume (left side)
        const buyIntensity = level.buy_vol / volumeScale.max;
        ctx.fillStyle = `rgba(0, 255, 136, ${0.2 + buyIntensity * 0.8})`;
        ctx.fillRect(x, y, barWidth / 2, levelHeight);

        // Sell volume (right side)
        const sellIntensity = level.sell_vol / volumeScale.max;
        ctx.fillStyle = `rgba(255, 0, 102, ${0.2 + sellIntensity * 0.8})`;
        ctx.fillRect(x + barWidth / 2, y, barWidth / 2, levelHeight);
      });
    } else {
      // Simple bar without price levels
      const y = priceToY(bar.close, priceRange, height);
      const barHeight = Math.abs(priceToY(bar.open, priceRange, height) - y) || 2;

      // Buy/Sell split
      const totalVol = bar.buy_volume + bar.sell_volume;
      const buyRatio = totalVol > 0 ? bar.buy_volume / totalVol : 0.5;

      ctx.fillStyle = colors.buyWeak;
      ctx.fillRect(x, y, barWidth * buyRatio, barHeight);

      ctx.fillStyle = colors.sellWeak;
      ctx.fillRect(x + barWidth * buyRatio, y, barWidth * (1 - buyRatio), barHeight);
    }
  });
}

function drawVolumeProfile(
  ctx: CanvasRenderingContext2D,
  profile: VolumeProfile,
  width: number,
  height: number,
  priceRange: { min: number; max: number; range: number },
  volumeScale: { max: number },
  colors: typeof CYBERPUNK_COLORS
) {
  const profileWidth = width * 0.15;
  const startX = width - profileWidth;

  // Draw value area background
  const vaTopY = priceToY(profile.value_area_low, priceRange, height);
  const vaBottomY = priceToY(profile.value_area_high, priceRange, height);
  
  ctx.fillStyle = colors.valueArea;
  ctx.fillRect(startX, vaBottomY, profileWidth, vaTopY - vaBottomY);

  // Draw POC line
  const pocY = priceToY(profile.poc, priceRange, height);
  ctx.strokeStyle = colors.poc;
  ctx.lineWidth = 2;
  ctx.setLineDash([5, 5]);
  ctx.beginPath();
  ctx.moveTo(startX, pocY);
  ctx.lineTo(width, pocY);
  ctx.stroke();
  ctx.setLineDash([]);

  // Draw volume bars
  if (profile.levels) {
    const maxProfileVol = Math.max(...profile.levels.map(l => l.volume));

    profile.levels.forEach(level => {
      const y = priceToY(level.price, priceRange, height);
      const barLength = (level.volume / maxProfileVol) * profileWidth * 0.8;

      // Buy volume
      ctx.fillStyle = colors.buyWeak;
      ctx.fillRect(startX, y, barLength * 0.5, 3);

      // Sell volume
      ctx.fillStyle = colors.sellWeak;
      ctx.fillRect(startX + barLength * 0.5, y, barLength * 0.5, 3);
    });
  }

  // POC label
  ctx.fillStyle = colors.poc;
  ctx.font = '10px monospace';
  ctx.fillText(`POC: ${profile.poc.toFixed(2)}`, startX + 5, pocY - 5);
}

function drawPriceLabels(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  priceRange: { min: number; max: number; range: number },
  colors: typeof CYBERPUNK_COLORS
) {
  ctx.fillStyle = colors.textDim;
  ctx.font = '10px monospace';
  ctx.textAlign = 'left';

  const labelCount = 8;
  for (let i = 0; i <= labelCount; i++) {
    const y = (i / labelCount) * height;
    const price = priceRange.max - (i / labelCount) * priceRange.range;
    ctx.fillText(price.toFixed(2), width * 0.86, y + 3);
  }
}

function priceToY(price: number, priceRange: { min: number; max: number; range: number }, height: number): number {
  const normalized = (price - priceRange.min) / priceRange.range;
  return height - normalized * height;
}

export default OrderFlowHeatmap;
