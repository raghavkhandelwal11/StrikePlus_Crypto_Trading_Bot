'use client';
// Combined chart-top control: clickable pair dropdown + live WS price +
// interval selector. Lives as an absolute overlay over the chart top-left.
//
// Click the pair label or the chevron to open the dropdown sorted by 24h
// volatility, with each row's live price and % change.
import { useEffect, useRef, useState } from 'react';
import { Pair, api } from '../lib/api';
import { fmtPrice } from '../lib/format';
import { useBinanceTicker } from '../lib/useBinanceTicker';

const INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d'] as const;
type Interval = typeof INTERVALS[number];

type Props = {
  selectedSymbol: string;
  selectedInterval: Interval;
  onPairChange: (symbol: string, token: string) => void;
  onIntervalChange: (interval: Interval) => void;
};

export default function ChartHeader({
  selectedSymbol, selectedInterval, onPairChange, onIntervalChange,
}: Props) {
  const [pairs, setPairs] = useState<Pair[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const tick = useBinanceTicker(selectedSymbol);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await api.pairs();
        if (!cancelled) setPairs(res.pairs || []);
      } catch (e) { console.error(e); }
    }
    load();
    const t = setInterval(load, 15_000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const selected = pairs.find(p => p.symbol === selectedSymbol);
  const sortedByVol = [...pairs].sort(
    (a, b) => Math.abs(b.price_change_pct ?? 0) - Math.abs(a.price_change_pct ?? 0)
  );
  // Prefer live WS price; fall back to the REST-cached snapshot.
  const livePrice = tick?.price ?? selected?.last_price ?? null;
  const live = tick != null;

  return (
    <div ref={ref} className="flex items-center gap-2">
      {/* The clickable pair pill */}
      <button
        onClick={() => setOpen(o => !o)}
        className="bg-panel/90 hover:bg-panel border border-panel2 rounded-md
                   pl-2.5 pr-2 py-1 flex items-center gap-2 backdrop-blur-sm
                   shadow-sm transition-colors"
        title="Click to switch pair"
      >
        <span className={`h-1.5 w-1.5 rounded-full ${live ? 'bg-good animate-pulse' : 'bg-gray-500'}`} />
        <span className="font-medium text-sm">{selected?.label || selectedSymbol}</span>
        {livePrice != null && (
          <span className="font-mono text-sm text-gray-200">${fmtPrice(livePrice)}</span>
        )}
        {selected?.price_change_pct != null && (
          <span className={`text-[11px] font-medium ${
            selected.price_change_pct >= 0 ? 'text-good' : 'text-bad'
          }`}>
            {selected.price_change_pct >= 0 ? '+' : ''}{selected.price_change_pct.toFixed(2)}%
          </span>
        )}
        <span className="text-gray-500 text-xs ml-0.5">▾</span>
      </button>

      {/* Interval selector — kept compact next to the pair pill */}
      <div className="bg-panel/90 border border-panel2 rounded-md p-0.5 flex items-center gap-0.5">
        {INTERVALS.map(i => (
          <button key={i}
                  onClick={() => onIntervalChange(i)}
                  className={`px-1.5 py-0.5 text-[11px] rounded transition-colors
                    ${i === selectedInterval
                      ? 'bg-accent/20 text-accent font-medium'
                      : 'text-gray-400 hover:text-gray-200 hover:bg-panel2'}`}>
            {i}
          </button>
        ))}
      </div>

      {/* Dropdown */}
      {open && (
        <div className="absolute z-30 mt-1 left-0 top-full bg-panel rounded-lg shadow-xl
                        border border-panel2 w-[340px] max-h-96 overflow-auto">
          <div className="px-3 py-2 border-b border-panel2 text-[10px] uppercase tracking-widest text-gray-500">
            Pairs sorted by 24h volatility
          </div>
          {sortedByVol.length === 0 && (
            <div className="px-3 py-4 text-gray-500 text-sm">loading…</div>
          )}
          {sortedByVol.map(p => (
            <button
              key={p.symbol}
              onClick={() => { onPairChange(p.symbol, p.token); setOpen(false); }}
              className={`w-full px-3 py-2 hover:bg-panel2 flex items-center gap-3 text-sm text-left transition-colors
                ${p.symbol === selectedSymbol ? 'bg-panel2' : ''}`}
            >
              <span className="font-medium w-28 truncate">{p.label}</span>
              <span className="font-mono text-xs text-gray-400 w-24">
                {p.last_price != null ? `$${fmtPrice(p.last_price)}` : '—'}
              </span>
              <span className={`text-xs ml-auto font-medium ${
                p.price_change_pct == null ? 'text-gray-500'
                : p.price_change_pct >= 0 ? 'text-good' : 'text-bad'
              }`}>
                {p.price_change_pct != null
                  ? `${p.price_change_pct >= 0 ? '+' : ''}${p.price_change_pct.toFixed(2)}%`
                  : '—'}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
