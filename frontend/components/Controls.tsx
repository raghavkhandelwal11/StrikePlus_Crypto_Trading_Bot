'use client';
import { useState } from 'react';
import { api } from '../lib/api';

const DURATIONS = ['15m', '30m', '1h', '3h', '6h', '12h', '1d', '1w'];
const CATEGORIES = ['low', 'medium', 'high'];

type Props = { running: boolean; onChange: () => void };

export default function Controls({ running, onChange }: Props) {
  const [duration, setDuration] = useState('1h');
  const [category, setCategory] = useState('medium');
  const [autoSwitch, setAutoSwitch] = useState(true);
  const [paperMode, setPaperMode] = useState(true);
  const [tokens, setTokens] = useState('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c'); // WBNB
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function start() {
    setBusy(true); setErr(null);
    try {
      await api.start({
        duration, strategy_category: category,
        auto_switch: autoSwitch, paper_mode: paperMode,
        tokens: tokens.split(',').map(t => t.trim()).filter(Boolean),
      });
      onChange();
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  async function stop() {
    setBusy(true); setErr(null);
    try { await api.stop('user_stop'); onChange(); }
    catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  async function kill() {
    if (!confirm('Engage kill switch and halt the bot? You will need to release it manually before restarting.')) return;
    setBusy(true);
    try { await api.kill(); onChange(); }
    catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="bg-panel rounded-xl p-4 space-y-3">
      <h3 className="text-sm uppercase tracking-wider text-gray-400">Controls</h3>

      <div className="grid grid-cols-2 gap-3">
        <label className="text-sm">
          <span className="text-gray-400">Duration</span>
          <select className="bg-panel2 mt-1 w-full p-2 rounded" value={duration}
                  onChange={e => setDuration(e.target.value)} disabled={running}>
            {DURATIONS.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>

        <label className="text-sm">
          <span className="text-gray-400">Risk category</span>
          <select className="bg-panel2 mt-1 w-full p-2 rounded" value={category}
                  onChange={e => setCategory(e.target.value)} disabled={running}>
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </div>

      <label className="text-sm block">
        <span className="text-gray-400">Tokens (comma-separated BEP20)</span>
        <input className="bg-panel2 mt-1 w-full p-2 rounded font-mono text-xs"
               value={tokens} onChange={e => setTokens(e.target.value)} disabled={running} />
      </label>

      <div className="flex gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={autoSwitch} onChange={e => setAutoSwitch(e.target.checked)} disabled={running} />
          auto-switch by regime
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={paperMode} onChange={e => setPaperMode(e.target.checked)} disabled={running} />
          paper mode
        </label>
      </div>

      <div className="flex gap-2 pt-2">
        {!running ? (
          <button className="bg-good text-black px-4 py-2 rounded font-medium disabled:opacity-50"
                  disabled={busy} onClick={start}>Start bot</button>
        ) : (
          <button className="bg-warn text-black px-4 py-2 rounded font-medium disabled:opacity-50"
                  disabled={busy} onClick={stop}>Stop</button>
        )}
        <button className="bg-bad text-black px-4 py-2 rounded font-medium disabled:opacity-50"
                disabled={busy} onClick={kill}>Kill switch</button>
      </div>

      {err && <p className="text-bad text-xs">{err}</p>}
    </div>
  );
}
