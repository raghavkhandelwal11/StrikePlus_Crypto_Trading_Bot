'use client';
// Form to start a new trading window. Includes capital deploy slider.
import { useState } from 'react';
import { api, Pair } from '../lib/api';

const DURATIONS = ['15m', '30m', '1h', '3h', '6h', '12h', '1d', '1w'] as const;
const CATEGORIES = ['low', 'medium', 'high'] as const;

type Props = {
  availableCash: number;
  selectedPair: { symbol: string; token: string } | null;
  pairs: Pair[];
  onCreated: () => void;
};

export default function NewWindowForm({ availableCash, selectedPair, pairs, onCreated }: Props) {
  const [duration, setDuration] = useState<typeof DURATIONS[number]>('1h');
  const [category, setCategory] = useState<typeof CATEGORIES[number]>('medium');
  const [autoSwitch, setAutoSwitch] = useState(true);
  const [paperMode, setPaperMode] = useState(true);
  // multi-select tokens by symbol; default to the currently displayed pair
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(
    selectedPair ? [selectedPair.symbol] : []
  );
  const [maxDeploy, setMaxDeploy] = useState<number>(Math.min(200, Math.max(50, availableCash * 0.3)));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function toggleSymbol(sym: string) {
    setSelectedSymbols(s => s.includes(sym) ? s.filter(x => x !== sym) : [...s, sym]);
  }

  async function start() {
    setErr(null);
    setBusy(true);
    try {
      const tokens = selectedSymbols
        .map(sym => pairs.find(p => p.symbol === sym)?.token)
        .filter((t): t is string => !!t);
      if (tokens.length === 0) throw new Error('Pick at least one pair to trade');
      await api.createWindow({
        duration, strategy_category: category,
        auto_switch: autoSwitch, paper_mode: paperMode,
        tokens, max_deploy_usd: maxDeploy,
      });
      onCreated();
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  const sliderMax = Math.max(50, Math.ceil(availableCash));
  const pctOfCash = availableCash > 0 ? ((maxDeploy / availableCash) * 100).toFixed(0) : '–';

  return (
    <div className="bg-panel rounded-xl p-4 space-y-3">
      <h3 className="text-sm uppercase tracking-wider text-gray-400">New trading window</h3>

      <div className="grid grid-cols-2 gap-3">
        <label className="text-sm">
          <span className="text-gray-400 text-xs">Duration</span>
          <select className="bg-panel2 mt-1 w-full p-2 rounded"
                  value={duration} onChange={e => setDuration(e.target.value as any)}>
            {DURATIONS.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
        <label className="text-sm">
          <span className="text-gray-400 text-xs">Risk category</span>
          <select className="bg-panel2 mt-1 w-full p-2 rounded"
                  value={category} onChange={e => setCategory(e.target.value as any)}>
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </div>

      {/* Max deploy slider */}
      <div>
        <div className="flex justify-between text-xs mb-1">
          <span className="text-gray-400">Max deploy</span>
          <span className="font-mono">${maxDeploy.toFixed(0)} <span className="text-gray-500">({pctOfCash}% of cash)</span></span>
        </div>
        <input
          type="range" min={10} max={sliderMax} step={10}
          value={maxDeploy} onChange={e => setMaxDeploy(Number(e.target.value))}
          className="w-full accent-accent"
        />
        <input
          type="number" min={10} step={10}
          value={maxDeploy} onChange={e => setMaxDeploy(Math.max(10, Number(e.target.value) || 0))}
          className="bg-panel2 mt-1 w-full p-1 rounded text-xs font-mono"
        />
      </div>

      {/* Pair multi-select */}
      <div>
        <div className="text-xs text-gray-400 mb-1">Pairs to trade</div>
        <div className="flex flex-wrap gap-1">
          {pairs.map(p => {
            const sel = selectedSymbols.includes(p.symbol);
            return (
              <button key={p.symbol}
                onClick={() => toggleSymbol(p.symbol)}
                className={`text-[11px] px-2 py-1 rounded border ${
                  sel ? 'bg-accent/20 border-accent text-accent' : 'border-panel2 hover:bg-panel2'
                }`}>
                {p.label.split('/')[0]}
                {p.price_change_pct != null && (
                  <span className={`ml-1 ${p.price_change_pct >= 0 ? 'text-good' : 'text-bad'}`}>
                    {p.price_change_pct >= 0 ? '+' : ''}{p.price_change_pct.toFixed(1)}%
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex gap-4 text-xs">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={autoSwitch} onChange={e => setAutoSwitch(e.target.checked)} />
          auto-switch by regime
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={paperMode} onChange={e => setPaperMode(e.target.checked)} />
          paper mode
        </label>
      </div>

      <button
        onClick={start}
        disabled={busy || selectedSymbols.length === 0}
        className="bg-good text-black px-4 py-2 rounded font-medium w-full disabled:opacity-50">
        {busy ? 'Starting…' : 'Start trading window'}
      </button>
      {err && <p className="text-bad text-xs">{err}</p>}
    </div>
  );
}
