'use client';
// Candlestick chart with EMA20/EMA50 overlays, avg-entry line, SL & TP lines,
// 2s candle fast-ticks via backend, and direct Binance WS for sub-second
// live price overlay (so the chart never looks "dead").
import {
  createChart, IChartApi, ISeriesApi, IPriceLine, LineStyle,
} from 'lightweight-charts';
import { useEffect, useRef } from 'react';
import { api } from '../lib/api';
import { fmtPrice } from '../lib/format';
import { useBinanceTicker } from '../lib/useBinanceTicker';

type Props = {
  symbol: string;
  interval: string;
  height?: number;
  avgEntryPrice?: number | null;
  stopLoss?: number | null;
  takeProfit?: number | null;
  unrealizedPnlPct?: number | null;
  showEMA20?: boolean;
  showEMA50?: boolean;
};

// --- EMA helper (frontend-side; matches `ta` semantics closely enough) ---
function ema(values: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const out: (number | null)[] = [];
  let prev: number | null = null;
  for (let i = 0; i < values.length; i++) {
    if (i < period - 1) { out.push(null); continue; }
    if (prev === null) {
      let sum = 0;
      for (let j = 0; j < period; j++) sum += values[j];
      prev = sum / period;
    } else {
      prev = values[i] * k + prev * (1 - k);
    }
    out.push(prev);
  }
  return out;
}

export default function Chart({
  symbol, interval, height = 380,
  avgEntryPrice = null, stopLoss = null, takeProfit = null,
  unrealizedPnlPct = null,
  showEMA20 = true, showEMA50 = true,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const ema20Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ema50Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const entryLineRef = useRef<IPriceLine | null>(null);
  const stopLineRef = useRef<IPriceLine | null>(null);
  const tpLineRef = useRef<IPriceLine | null>(null);
  const lastCandleRef = useRef<{ time: number; open: number; high: number; low: number; close: number } | null>(null);

  // Live sub-second price straight from Binance WS (also used to drive the
  // chart-overlay header, but kept here so the open candle's close morphs).
  const liveTick = useBinanceTicker(symbol);

  // --- Create chart once ---
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: { background: { color: '#13161b' }, textColor: '#9ba3ad' },
      grid: { vertLines: { color: '#1a1f26' }, horzLines: { color: '#1a1f26' } },
      timeScale: { timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: '#2a2f36' },
      crosshair: { mode: 1 },
    });
    chartRef.current = chart;
    candleRef.current = chart.addCandlestickSeries({
      upColor: '#4ade80', downColor: '#f87171', borderVisible: false,
      wickUpColor: '#4ade80', wickDownColor: '#f87171',
      priceFormat: { type: 'price', precision: 4, minMove: 0.0001 },
    });
    ema20Ref.current = chart.addLineSeries({
      color: '#22d3ee', lineWidth: 1, priceLineVisible: false, lastValueVisible: true,
      title: 'EMA20',
    });
    ema50Ref.current = chart.addLineSeries({
      color: '#facc15', lineWidth: 1, priceLineVisible: false, lastValueVisible: true,
      title: 'EMA50',
    });

    const onResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener('resize', onResize);
    return () => { window.removeEventListener('resize', onResize); chart.remove(); };
  }, [height]);

  // --- Full reload on symbol/interval change (every 30s thereafter) ---
  useEffect(() => {
    let cancelled = false;
    async function loadFull() {
      try {
        const data = await api.ohlcv(symbol, interval, 300);
        if (cancelled || !candleRef.current) return;
        const candles = data.map((c: any) => ({
          time: Math.floor(c.ts / 1000) as any,
          open: c.open, high: c.high, low: c.low, close: c.close,
        }));
        candleRef.current.setData(candles);
        lastCandleRef.current = candles[candles.length - 1] ?? null;
        const closes = data.map((c: any) => c.close);
        if (showEMA20 && ema20Ref.current) {
          const e = ema(closes, 20);
          ema20Ref.current.setData(
            candles.map((c, i) => e[i] != null ? { time: c.time, value: e[i]! } : null)
                   .filter(Boolean) as any
          );
        }
        if (showEMA50 && ema50Ref.current) {
          const e = ema(closes, 50);
          ema50Ref.current.setData(
            candles.map((c, i) => e[i] != null ? { time: c.time, value: e[i]! } : null)
                   .filter(Boolean) as any
          );
        }
      } catch (e) {
        console.error(e);
      }
    }
    loadFull();
    const t = setInterval(loadFull, 30_000);
    return () => { cancelled = true; clearInterval(t); };
  }, [symbol, interval, showEMA20, showEMA50]);

  // --- Fast candle tick every 2s (backend hits Binance kline endpoint) ---
  useEffect(() => {
    let cancelled = false;
    async function tickLast() {
      try {
        const data = await api.ohlcv(symbol, interval, 2);
        if (cancelled || !candleRef.current || data.length === 0) return;
        const last = data[data.length - 1];
        const candle = {
          time: Math.floor(last.ts / 1000) as any,
          open: last.open, high: last.high, low: last.low, close: last.close,
        };
        candleRef.current.update(candle);
        lastCandleRef.current = candle as any;
      } catch (e) { /* silent */ }
    }
    const t = setInterval(tickLast, 2_000);
    return () => { cancelled = true; clearInterval(t); };
  }, [symbol, interval]);

  // --- Sub-second tick from Binance WS: morph the last candle's close ---
  useEffect(() => {
    if (!liveTick || !candleRef.current || !lastCandleRef.current) return;
    if (liveTick.symbol.toUpperCase() !== symbol.toUpperCase()) return;
    const c = lastCandleRef.current;
    // Update the current candle's close + extend high/low if exceeded.
    const updated = {
      time: c.time as any,
      open: c.open,
      high: Math.max(c.high, liveTick.price),
      low:  Math.min(c.low,  liveTick.price),
      close: liveTick.price,
    };
    candleRef.current.update(updated);
    lastCandleRef.current = updated as any;
  }, [liveTick, symbol]);

  // --- Avg-entry line ---
  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;
    if (entryLineRef.current) {
      try { series.removePriceLine(entryLineRef.current); } catch {}
      entryLineRef.current = null;
    }
    if (avgEntryPrice && avgEntryPrice > 0) {
      const pnl = unrealizedPnlPct == null ? '' :
        ` (${unrealizedPnlPct >= 0 ? '+' : ''}${unrealizedPnlPct.toFixed(2)}%)`;
      const color = unrealizedPnlPct == null ? '#22d3ee'
        : unrealizedPnlPct >= 0 ? '#4ade80' : '#f87171';
      entryLineRef.current = series.createPriceLine({
        price: avgEntryPrice, color, lineWidth: 2, lineStyle: LineStyle.Dashed,
        axisLabelVisible: true, title: `entry ${fmtPrice(avgEntryPrice)}${pnl}`,
      });
    }
  }, [avgEntryPrice, unrealizedPnlPct]);

  // --- Stop-loss line ---
  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;
    if (stopLineRef.current) {
      try { series.removePriceLine(stopLineRef.current); } catch {}
      stopLineRef.current = null;
    }
    if (stopLoss && stopLoss > 0) {
      stopLineRef.current = series.createPriceLine({
        price: stopLoss, color: '#f87171', lineWidth: 1, lineStyle: LineStyle.Dotted,
        axisLabelVisible: true, title: `SL ${fmtPrice(stopLoss)}`,
      });
    }
  }, [stopLoss]);

  // --- Take-profit line ---
  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;
    if (tpLineRef.current) {
      try { series.removePriceLine(tpLineRef.current); } catch {}
      tpLineRef.current = null;
    }
    if (takeProfit && takeProfit > 0) {
      tpLineRef.current = series.createPriceLine({
        price: takeProfit, color: '#4ade80', lineWidth: 1, lineStyle: LineStyle.Dotted,
        axisLabelVisible: true, title: `TP ${fmtPrice(takeProfit)}`,
      });
    }
  }, [takeProfit]);

  // Price/symbol badge is owned by ChartHeader now, rendered as an absolute
  // overlay by the parent (page.tsx). Keeps this component a pure chart.
  return <div ref={containerRef} className="w-full" style={{ height }} />;
}
