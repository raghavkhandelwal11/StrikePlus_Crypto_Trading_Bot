'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Chart from '../components/Chart';
import ChartHeader from '../components/ChartHeader';
import HistoryTab from '../components/HistoryTab';
import LogsPanel from '../components/LogsPanel';
import NewWindowForm from '../components/NewWindowForm';
import StatusPanel from '../components/StatusPanel';
import TerminateButton from '../components/TerminateButton';
import TopTicker from '../components/TopTicker';
import WindowsPanel from '../components/WindowsPanel';
import { api, Pair, Position, TradingWindow } from '../lib/api';
import { fmtPrice, fmtUsd } from '../lib/format';
import { useBotStream, BotEvent } from '../lib/useBotStream';

const INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d'] as const;
type Tab = 'current' | 'history';

export default function Dashboard() {
  const [status, setStatus] = useState<any | null>(null);
  const [wallet, setWallet] = useState<any | null>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [windows, setWindows] = useState<TradingWindow[]>([]);
  const [pairs, setPairs] = useState<Pair[]>([]);
  const [logs, setLogs] = useState<{ ts: string; level: 'info'|'warn'|'error'; msg: string }[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState('BNBUSDT');
  const [selectedToken, setSelectedToken] = useState<string>('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c');
  const [interval, setInterval_] = useState<typeof INTERVALS[number]>('15m');
  const [tab, setTab] = useState<Tab>('current');
  const prevRunningCount = useRef(0);

  const refresh = useCallback(async () => {
    try {
      const [s, w, t, p, ws, pa] = await Promise.all([
        api.status(), api.wallet(), api.trades(200),
        api.positions(), api.listWindows(), api.pairs(),
      ]);
      setStatus(s); setWallet(w);
      setTrades(t.items || []);
      setPositions(p.positions || []);
      setWindows(ws.windows || []);
      setPairs(pa.pairs || []);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, 5000);
    return () => window.clearInterval(t);
  }, [refresh]);

  useBotStream(useCallback((e: BotEvent) => {
    const ts = new Date().toISOString().slice(11, 19);
    if (e.type === 'status')    setStatus(e.data);
    if (e.type === 'wallet')    setWallet(e.data);
    if (e.type === 'positions') setPositions(e.data || []);
    if (e.type === 'windows')   setWindows(e.data || []);
    if (e.type === 'trade') {
      const r: any = e.data?.result || {};
      const sig: any = e.data?.signal || {};
      const reason = e.data?.exit_reason || sig.reason || '';
      setLogs(prev => [...prev, {
        ts,
        level: (r.pnl_usd ?? 0) < 0 ? 'warn' : 'info',
        msg: `[${e.data?.window_id ?? '—'}] ${sig.strategy} ${String(r.side).toUpperCase()} `
           + `${r.amount_in?.toFixed?.(4) ?? ''} @ ${r.price?.toFixed?.(4) ?? ''}`
           + (r.pnl_usd != null ? ` pnl=$${r.pnl_usd.toFixed(2)}` : '')
           + ` (${reason})`,
      }]);
      api.trades(200).then(t => setTrades(t.items || []));
      api.positions().then(p => setPositions(p.positions || []));
      api.listWindows().then(ws => setWindows(ws.windows || []));
    }
    if (e.type === 'signal_rejected') {
      setLogs(p => [...p, { ts, level: 'warn',
        msg: `[${e.data?.window_id ?? '—'}] rejected: ${e.data.strategy} (${e.data.reason})` }]);
    }
  }, []));

  // Partition windows by status
  const runningWindows = useMemo(
    () => windows.filter(w => w.status === 'running'),
    [windows],
  );
  const pastWindows = useMemo(
    () => windows.filter(w => w.status !== 'running'),
    [windows],
  );

  // Auto-switch to history tab when the last running window ends (i.e.
  // duration expired or user terminated). Avoid stealing focus while at
  // least one window is still alive — multi-window users hate that.
  useEffect(() => {
    const running = runningWindows.length;
    if (prevRunningCount.current > 0 && running === 0) {
      setTab('history');
    }
    prevRunningCount.current = running;
  }, [runningWindows.length]);

  // Position matched to displayed chart symbol — drives entry/SL/TP overlays.
  const displayedPosition = useMemo<Position | null>(() => {
    return positions.find(p => p.token.toLowerCase() === selectedToken.toLowerCase()) || null;
  }, [positions, selectedToken]);

  const availableCash = wallet?.available_capital_usd ?? 1000;

  return (
    <main className="min-h-screen bg-bg text-gray-100">
      <div className="max-w-screen-2xl mx-auto p-4 space-y-4">

        <TopTicker />

        <header className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold">Crypto Trading Bot</h1>
            <span className="text-gray-500 text-sm">BSC / PancakeSwap</span>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          <section className="lg:col-span-3 space-y-4">
            {/* Chart with overlays */}
            <div className="bg-panel rounded-xl p-2 relative">
              {/* Top-left overlay: clickable pair dropdown + interval picker.
                  Positioned absolutely so it floats over the candles. */}
              <div className="absolute top-3 left-3 z-20">
                <ChartHeader
                  selectedSymbol={selectedSymbol}
                  selectedInterval={interval}
                  onPairChange={(sym, token) => { setSelectedSymbol(sym); setSelectedToken(token); }}
                  onIntervalChange={(i) => setInterval_(i)}
                />
              </div>

              <Chart
                symbol={selectedSymbol}
                interval={interval}
                avgEntryPrice={displayedPosition?.avg_entry_price ?? null}
                stopLoss={displayedPosition?.stop_loss && displayedPosition.stop_loss > 0 ? displayedPosition.stop_loss : null}
                takeProfit={displayedPosition?.take_profit && displayedPosition.take_profit > 0 ? displayedPosition.take_profit : null}
                unrealizedPnlPct={displayedPosition?.unrealized_pnl_pct ?? null}
              />
              {displayedPosition && (
                <div className="px-2 pb-2 pt-1 text-xs text-gray-400 flex gap-3 flex-wrap">
                  <span>open: <span className="text-gray-200 font-mono">{displayedPosition.units.toFixed(4)}</span></span>
                  <span>entry: <span className="text-gray-200 font-mono">${fmtPrice(displayedPosition.avg_entry_price)}</span></span>
                  {displayedPosition.stop_loss! > 0 && (
                    <span>SL: <span className="text-bad font-mono">${fmtPrice(displayedPosition.stop_loss)}</span></span>
                  )}
                  {displayedPosition.take_profit! > 0 && (
                    <span>TP: <span className="text-good font-mono">${fmtPrice(displayedPosition.take_profit)}</span></span>
                  )}
                  <span>cost basis: <span className="text-gray-200">{fmtUsd(displayedPosition.cost_basis_usd)}</span></span>
                  {displayedPosition.unrealized_pnl_usd != null && (
                    <span>
                      unrealized:{' '}
                      <span className={displayedPosition.unrealized_pnl_usd >= 0 ? 'text-good' : 'text-bad'}>
                        {fmtUsd(displayedPosition.unrealized_pnl_usd, 2, true)}
                        {displayedPosition.unrealized_pnl_pct != null &&
                          ` (${displayedPosition.unrealized_pnl_pct >= 0 ? '+' : ''}${displayedPosition.unrealized_pnl_pct.toFixed(2)}%)`}
                      </span>
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Tabs: Current Positions / Trade History */}
            <div className="bg-panel rounded-xl overflow-hidden">
              <div className="flex border-b border-panel2">
                <TabButton
                  active={tab === 'current'}
                  onClick={() => setTab('current')}
                  label="Current Positions"
                  count={runningWindows.length}
                />
                <TabButton
                  active={tab === 'history'}
                  onClick={() => setTab('history')}
                  label="Trade History"
                  count={pastWindows.length}
                />
              </div>

              <div className="p-3">
                {tab === 'current' ? (
                  <WindowsPanel
                    windows={runningWindows}
                    pairs={pairs}
                    positions={positions}
                    onChange={refresh}
                  />
                ) : (
                  <HistoryTab windows={pastWindows} pairs={pairs} trades={trades} />
                )}
              </div>
            </div>
          </section>

          <aside className="space-y-4">
            <StatusPanel status={status} wallet={wallet} trades={trades} />
            <NewWindowForm
              availableCash={availableCash}
              selectedPair={{ symbol: selectedSymbol, token: selectedToken }}
              pairs={pairs}
              onCreated={() => { setTab('current'); refresh(); }}
            />
            <TerminateButton onDone={() => { setTab('history'); refresh(); }} />
            <LogsPanel logs={logs} />
          </aside>
        </div>

        <footer className="text-xs text-gray-500 leading-relaxed pt-2">
          Paper mode by default. Strategies learn from outcomes — losing strategies auto-disable for 1h after a 10-trade cold streak.
          Live price overlay streams direct from Binance WebSocket; candle data refreshes every 2s.
        </footer>
      </div>
    </main>
  );
}

function TabButton({
  active, onClick, label, count,
}: { active: boolean; onClick: () => void; label: string; count: number }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px
        ${active
          ? 'text-gray-100 border-accent bg-panel2/40'
          : 'text-gray-500 hover:text-gray-300 border-transparent'}`}
    >
      {label}
      <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded
        ${active ? 'bg-accent/20 text-accent' : 'bg-panel2 text-gray-500'}`}>
        {count}
      </span>
    </button>
  );
}
