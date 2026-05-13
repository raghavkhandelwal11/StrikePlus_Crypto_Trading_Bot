'use client';
// Trade history tab — shows completed/killed/stopped windows in a compact
// list, plus the full trades table.
import { Pair, TradingWindow } from '../lib/api';
import { fmtUsd } from '../lib/format';
import TradesTable from './TradesTable';

type Props = {
  windows: TradingWindow[];
  pairs: Pair[];
  trades: any[];
};

function fmtDuration(seconds: number): string {
  if (seconds <= 0) return '0s';
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m ${s % 60}s`;
}

export default function HistoryTab({ windows, pairs, trades }: Props) {
  // Sort newest first by deadline.
  const sorted = [...windows].sort((a, b) =>
    new Date(b.deadline_at).getTime() - new Date(a.deadline_at).getTime()
  );

  return (
    <div className="space-y-4">
      <div className="bg-panel rounded-xl p-4">
        <h3 className="text-sm uppercase tracking-wider text-gray-400 mb-3">
          Past trading windows ({sorted.length})
        </h3>
        {sorted.length === 0 ? (
          <p className="text-gray-500 text-sm">No completed windows yet.</p>
        ) : (
          <div className="space-y-2">
            {sorted.map(w => <PastWindowRow key={w.id} w={w} pairs={pairs} />)}
          </div>
        )}
      </div>

      <TradesTable trades={trades} />
    </div>
  );
}

function PastWindowRow({ w, pairs }: { w: TradingWindow; pairs: Pair[] }) {
  const started = new Date(w.started_at);
  const ended = new Date(w.deadline_at);
  const ranSec = Math.max(0, Math.floor((Date.now() - started.getTime()) / 1000));
  const pnlGood = w.realized_pnl_usd >= 0;

  const statusColor =
    w.status === 'killed'    ? 'text-bad' :
    w.status === 'completed' ? 'text-accent' :
    w.status === 'stopped'   ? 'text-gray-300' :
                                'text-gray-400';

  const symbols = w.tokens.map(t => {
    const p = pairs.find(pp => pp.token.toLowerCase() === t.toLowerCase());
    return p ? p.label.split('/')[0] : `${t.slice(0, 6)}…`;
  });

  return (
    <div className="bg-panel2 rounded-lg p-3 grid grid-cols-12 gap-3 items-center text-xs">
      <div className="col-span-2 flex items-center gap-2 min-w-0">
        <span className="font-mono text-gray-400">#{w.id}</span>
        <span className={`text-[10px] uppercase tracking-widest font-medium ${statusColor}`}>
          {w.status}
        </span>
      </div>

      <div className="col-span-3 flex items-center gap-1 flex-wrap min-w-0">
        {symbols.map((s, i) => (
          <span key={i} className="bg-panel px-1.5 py-0.5 rounded text-[11px] font-medium">{s}</span>
        ))}
      </div>

      <div className="col-span-2 text-gray-400">
        {started.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        <span className="text-gray-600 mx-1">→</span>
        {ended.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </div>

      <div className="col-span-2 text-gray-400 font-mono">
        {fmtDuration(w.duration_seconds)} planned
      </div>

      <div className="col-span-1 text-gray-400 font-mono">{w.trade_count} trades</div>

      <div className={`col-span-2 font-mono text-right text-sm font-medium ${pnlGood ? 'text-good' : 'text-bad'}`}>
        {fmtUsd(w.realized_pnl_usd, 2, true)}
      </div>
    </div>
  );
}
