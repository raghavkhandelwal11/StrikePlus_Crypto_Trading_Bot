'use client';
// Multi-window list. Each card shows: status banner, time progress,
// per-pair open positions with their own Exit button, stats, controls.
import { useEffect, useState } from 'react';
import { api, Pair, Position, TradingWindow } from '../lib/api';
import { fmtPrice, fmtUsd } from '../lib/format';

type Props = {
  windows: TradingWindow[];
  pairs: Pair[];
  positions: Position[];          // global positions list; we filter per window
  onChange: () => void;
};

function fmtDuration(seconds: number): string {
  if (seconds <= 0) return '0s';
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

const EXTEND_OPTIONS: { label: string; seconds: number }[] = [
  { label: '+15m', seconds: 15 * 60 },
  { label: '+1h',  seconds: 60 * 60 },
  { label: '+3h',  seconds: 3 * 60 * 60 },
];

export default function WindowsPanel({ windows, pairs, positions, onChange }: Props) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick(x => x + 1), 1000);
    return () => clearInterval(t);
  }, []);

  if (windows.length === 0) {
    return (
      <div className="bg-panel rounded-xl p-4 text-sm text-gray-500">
        No trading windows. Start one in the sidebar →
      </div>
    );
  }

  return (
    <div className="bg-panel rounded-xl p-4">
      <h3 className="text-sm uppercase tracking-wider text-gray-400 mb-3">
        Trading windows ({windows.length})
      </h3>
      <div className="space-y-3">
        {windows.map(w => (
          <WindowCard
            key={w.id}
            w={w}
            pairs={pairs}
            positions={positions.filter(p => p.window_id === w.id)}
            onChange={onChange}
          />
        ))}
      </div>
    </div>
  );
}

function WindowCard({
  w, pairs, positions, onChange,
}: { w: TradingWindow; pairs: Pair[]; positions: Position[]; onChange: () => void }) {
  const [busy, setBusy] = useState(false);

  async function kill() {
    if (!confirm(`Kill window ${w.id}? This closes its open positions.`)) return;
    setBusy(true);
    try { await api.killWindow(w.id); onChange(); }
    catch (e: any) { alert(e.message); }
    finally { setBusy(false); }
  }
  async function extend(sec: number) {
    setBusy(true);
    try { await api.extendWindow(w.id, sec); onChange(); }
    catch (e: any) { alert(e.message); }
    finally { setBusy(false); }
  }

  const isRunning = w.status === 'running';
  const utilPct = w.max_deploy_usd > 0
    ? Math.min(100, (w.deployed_usd / w.max_deploy_usd) * 100)
    : 0;
  const statusColor =
    w.status === 'running'   ? 'text-good' :
    w.status === 'killed'    ? 'text-bad' :
    w.status === 'completed' ? 'text-accent' :
                                'text-gray-400';

  // Duration math
  const now = Date.now();
  const started = new Date(w.started_at).getTime();
  const deadline = new Date(w.deadline_at).getTime();
  const elapsedSec = Math.max(0, Math.floor((now - started) / 1000));
  const remainingSec = Math.max(0, Math.floor((deadline - now) / 1000));
  const totalSec = w.duration_seconds;
  const progressPct = totalSec > 0
    ? Math.min(100, Math.max(0, (elapsedSec / totalSec) * 100))
    : 0;

  return (
    <div className="bg-panel2 rounded-lg p-3">
      {/* Header: id + status + remaining time */}
      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-gray-400">#{w.id}</span>
          <span className={`text-[10px] font-medium uppercase tracking-widest ${statusColor}`}>
            {w.status}
          </span>
          {w.paper_mode && (
            <span className="text-[10px] bg-panel px-1.5 py-0.5 rounded text-gray-400">paper</span>
          )}
          {w.extended_by_seconds > 0 && (
            <span className="text-[10px] bg-accent/20 text-accent px-1.5 py-0.5 rounded">
              extended +{fmtDuration(w.extended_by_seconds)}
            </span>
          )}
        </div>
        <span className="text-xs font-mono">
          {isRunning ? (
            <>
              <span className="text-gray-400">{fmtDuration(elapsedSec)}</span>
              <span className="text-gray-600 mx-1">/</span>
              <span className="text-gray-200">{fmtDuration(totalSec)}</span>
              <span className="text-gray-500 ml-2">({fmtDuration(remainingSec)} left)</span>
            </>
          ) : (
            <span className="text-gray-500">{fmtDuration(elapsedSec)} ran</span>
          )}
        </span>
      </div>

      {/* Time progress bar */}
      <div className="h-1 bg-panel rounded overflow-hidden mb-3">
        <div className="h-full bg-accent/60 transition-all duration-1000"
             style={{ width: `${progressPct}%` }} />
      </div>

      {/* Live bot reasoning */}
      {isRunning && (w.phase || w.reasoning) && (
        <PhaseBanner phase={w.phase} reasoning={w.reasoning} />
      )}

      {/* Pairs being watched (just market context — NOT held positions).
          Styled deliberately muted: smaller text, low-opacity colors,
          explicit "24h" prefix, tooltip — so this row never gets mistaken
          for the user's actual portfolio. */}
      <div className="flex items-baseline gap-x-2 gap-y-1 mb-2 flex-wrap">
        <span className="text-[9px] uppercase tracking-widest text-gray-600">
          Watching · 24h
        </span>
        {w.tokens.map(t => {
          const pair = pairs.find(p => p.token.toLowerCase() === t.toLowerCase());
          const sym = pair ? pair.label.split('/')[0] : `${t.slice(0, 6)}…`;
          const chg = pair?.price_change_pct;
          return (
            <span
              key={t}
              title="24h price change on Binance — this is market context, not a held position"
              className="text-[11px] inline-flex items-baseline gap-1">
              <span className="text-gray-300 font-medium">{sym}</span>
              {chg != null && (
                <span className={`tabular-nums ${chg >= 0 ? 'text-good/70' : 'text-bad/70'}`}>
                  {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%
                </span>
              )}
            </span>
          );
        })}
      </div>

      {/* Per-pair open positions */}
      <div className="mb-3 space-y-1.5">
        <div className="text-[10px] uppercase tracking-widest text-gray-500 flex items-center gap-2">
          <span>Open positions</span>
          <span className="bg-panel px-1.5 py-0.5 rounded text-gray-400 font-mono">
            {positions.length}
          </span>
        </div>
        {positions.length === 0 ? (
          <div className="text-[11px] text-gray-500 italic py-1">
            No positions yet — waiting for a qualifying setup.
          </div>
        ) : (
          positions.map(p => (
            <PositionRow key={p.token} p={p} pairs={pairs} windowId={w.id} onChange={onChange} />
          ))
        )}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-2 text-xs mb-2">
        <Stat label="Deployed" value={`$${w.deployed_usd.toFixed(2)} / $${w.max_deploy_usd.toFixed(0)}`} />
        <Stat
          label="Realized"
          value={`${w.realized_pnl_usd >= 0 ? '+' : ''}$${w.realized_pnl_usd.toFixed(2)}`}
          cls={w.realized_pnl_usd >= 0 ? 'text-good' : 'text-bad'}
        />
        <Stat label="Open / Trades" value={`${w.open_positions} / ${w.trade_count}`} />
      </div>

      {/* Deploy utilization bar */}
      <div className="h-1 bg-panel rounded overflow-hidden mb-2">
        <div className="h-full bg-good/60" style={{ width: `${utilPct}%` }} />
      </div>

      {/* Strategy + auto-switch */}
      <div className="flex items-center gap-2 text-xs">
        <span className="text-[10px] uppercase tracking-widest text-gray-500">Strategy</span>
        <span className="text-gray-200">{w.strategy_category}{w.auto_switch ? ' · auto' : ''}</span>
      </div>

      {/* Action row */}
      {isRunning && (
        <div className="mt-3 pt-2 border-t border-panel/60 flex items-center gap-1 flex-wrap">
          {EXTEND_OPTIONS.map(opt => (
            <button key={opt.label}
                    disabled={busy}
                    onClick={() => extend(opt.seconds)}
                    className="text-[11px] px-2 py-1 rounded bg-panel hover:bg-panel/60 disabled:opacity-50">
              {opt.label}
            </button>
          ))}
          <button disabled={busy}
                  onClick={kill}
                  className="ml-auto text-[11px] px-2 py-1 rounded bg-bad/20 text-bad hover:bg-bad/30 disabled:opacity-50">
            Kill window
          </button>
        </div>
      )}
    </div>
  );
}

function PositionRow({
  p, pairs, windowId, onChange,
}: { p: Position; pairs: Pair[]; windowId: string; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const pair = pairs.find(x => x.token.toLowerCase() === p.token.toLowerCase());
  const sym = pair ? pair.label.split('/')[0] : `${p.token.slice(0, 6)}…`;
  const pnl = p.unrealized_pnl_usd ?? 0;
  const pnlPct = p.unrealized_pnl_pct ?? 0;
  const hasStop = (p.stop_loss ?? 0) > 0;
  const hasTp   = (p.take_profit ?? 0) > 0;
  const r       = (p.initial_risk ?? 0) > 0 && p.mark_price && p.avg_entry_price
    ? (p.mark_price - p.avg_entry_price) / p.initial_risk!
    : null;

  async function exit() {
    if (!confirm(`Manually close ${sym} position? Current P&L: $${pnl.toFixed(2)}`)) return;
    setBusy(true);
    try {
      await api.closeWindowPosition(windowId, p.token);
      onChange();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-panel rounded p-2 text-xs">
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{sym}</span>
          <span className="text-[10px] text-gray-500 bg-panel2 px-1.5 py-0.5 rounded">
            {p.strategy}
          </span>
          {p.pyramid_step != null && p.pyramid_step > 0 && (
            <span className="text-[10px] text-accent bg-accent/10 px-1.5 py-0.5 rounded">
              pyramid·{p.pyramid_step}
            </span>
          )}
          {(p.scale_outs_done ?? 0) > 0 && (
            <span className="text-[10px] text-warn bg-warn/10 px-1.5 py-0.5 rounded">
              50% locked
            </span>
          )}
        </div>
        <button
          disabled={busy}
          onClick={exit}
          className="text-[11px] px-2 py-0.5 rounded bg-bad/15 text-bad hover:bg-bad/25 border border-bad/30 disabled:opacity-50">
          {busy ? '…' : 'Exit'}
        </button>
      </div>
      <div className="grid grid-cols-4 gap-2 mt-1">
        <Cell label="Deployed"  value={fmtUsd(p.cost_basis_usd)} />
        <Cell label="Entry"     value={`$${fmtPrice(p.avg_entry_price)}`} />
        <Cell label="Mark"      value={p.mark_price != null ? `$${fmtPrice(p.mark_price)}` : '—'} />
        <Cell
          label="Unreal P&L"
          value={`${fmtUsd(pnl, 2, true)} (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%)`}
          cls={pnl >= 0 ? 'text-good' : 'text-bad'}
        />
      </div>
      {(hasStop || hasTp || r != null) && (
        <div className="mt-1 flex items-center gap-3 text-[10px] text-gray-500 font-mono">
          {hasStop && <span>SL <span className="text-bad">${fmtPrice(p.stop_loss)}</span></span>}
          {hasTp   && <span>TP <span className="text-good">${fmtPrice(p.take_profit)}</span></span>}
          {r != null && <span>{r >= 0 ? '+' : ''}{r.toFixed(2)}R</span>}
        </div>
      )}
    </div>
  );
}

function Cell({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className={`font-mono text-[11px] ${cls ?? ''}`}>{value}</div>
    </div>
  );
}

function Stat({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className={`font-mono ${cls ?? ''}`}>{value}</div>
    </div>
  );
}

const PHASE_META: Record<string, { icon: string; cls: string; label: string }> = {
  warmup:     { icon: '⏳', cls: 'bg-warn/10 text-warn border-warn/30',         label: 'WARMUP' },
  analyzing:  { icon: '🔍', cls: 'bg-panel border-panel2 text-gray-300',         label: 'ANALYZING' },
  pending:    { icon: '🎯', cls: 'bg-accent/10 text-accent border-accent/30',    label: 'CONFIRMING' },
  entering:   { icon: '▶',  cls: 'bg-good/15 text-good border-good/30',          label: 'ENTERING' },
  holding:    { icon: '📊', cls: 'bg-panel border-panel2 text-gray-200',         label: 'HOLDING' },
  cooldown:   { icon: '💤', cls: 'bg-panel border-panel2 text-gray-400',         label: 'COOLDOWN' },
  waiting:    { icon: '⏸',  cls: 'bg-panel border-panel2 text-gray-400',         label: 'WAITING' },
  starting:   { icon: '⚙',  cls: 'bg-panel border-panel2 text-gray-400',         label: 'STARTING' },
};

function PhaseBanner({ phase, reasoning }: { phase?: string; reasoning?: string }) {
  const meta = PHASE_META[phase || 'starting'] || PHASE_META['starting'];
  return (
    <div className={`mb-3 px-2.5 py-1.5 rounded border text-xs flex items-start gap-2 ${meta.cls}`}>
      <span className="text-sm leading-tight">{meta.icon}</span>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] uppercase tracking-widest font-semibold leading-none">{meta.label}</div>
        {reasoning && <div className="mt-0.5 leading-snug">{reasoning}</div>}
      </div>
    </div>
  );
}
