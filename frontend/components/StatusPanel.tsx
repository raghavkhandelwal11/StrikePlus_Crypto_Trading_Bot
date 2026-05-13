'use client';
// Aggregated bot status + wallet summary with BNB + USDT split.
// Period analytics (Today / All time) computed from the loaded trade history.

type Trade = {
  ts: string;
  side: 'buy' | 'sell' | string;
  pnl_usd?: number;
  notional_usd?: number;
  gas_cost_usd?: number;
  lp_fee_usd?: number;
};

type Props = {
  status: any | null;
  wallet: any | null;
  trades: Trade[];
};

function aggregate(trades: Trade[], since: Date) {
  let realized = 0, fees = 0, wins = 0, closed = 0;
  for (const t of trades) {
    if (!t.ts) continue;
    const ts = new Date(t.ts);
    if (ts < since) continue;
    fees += (t.gas_cost_usd ?? 0) + (t.lp_fee_usd ?? 0);
    if (t.side === 'sell') {
      closed += 1;
      if ((t.pnl_usd ?? 0) > 0) wins += 1;
      realized += t.pnl_usd ?? 0;
    }
  }
  return { realized, fees, winRate: closed > 0 ? wins / closed : 0, closed };
}

export default function StatusPanel({ status, wallet, trades }: Props) {
  const live = status?.status === 'running';

  // Today (midnight local) and all-time aggregates
  const midnight = new Date(); midnight.setHours(0, 0, 0, 0);
  const today = aggregate(trades, midnight);
  const all = aggregate(trades, new Date(0));

  // BNB & USDT balances
  const bnbBalance = wallet?.bnb_balance ?? 0;
  // Heuristic: USDT lives in the available_capital_usd minus the BNB-USD portion.
  const usdtBalance = Math.max(0, (wallet?.available_capital_usd ?? 0));

  return (
    <div className="bg-panel rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <div className={`h-2.5 w-2.5 rounded-full ${live ? 'bg-good animate-pulse' : 'bg-gray-500'}`} />
        <span className="font-medium capitalize text-sm">{status?.status || 'idle'}</span>
        {status?.kill_switch && <span className="ml-2 text-bad text-[10px] uppercase tracking-widest">kill engaged</span>}
        {status?.active_strategy && status.active_strategy !== 'none' && (
          <span className="ml-auto text-[10px] uppercase tracking-widest text-gray-500">
            {status.active_strategy}
          </span>
        )}
      </div>

      {/* Wallet — BNB + USDT */}
      <div className="bg-panel2 rounded-lg p-3 grid grid-cols-2 gap-2 text-sm">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-gray-500">USDT</div>
          <div className="font-mono">${usdtBalance.toFixed(2)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-widest text-gray-500">BNB</div>
          <div className="font-mono">{bnbBalance.toFixed(4)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-widest text-gray-500">Deployed</div>
          <div className="font-mono">${(wallet?.deployed_capital_usd ?? 0).toFixed(2)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-widest text-gray-500">Unrealized</div>
          <div className={`font-mono ${(wallet?.unrealized_pnl_usd ?? 0) >= 0 ? 'text-good' : 'text-bad'}`}>
            ${(wallet?.unrealized_pnl_usd ?? 0).toFixed(2)}
          </div>
        </div>
      </div>

      {/* Analytics — Today + All time */}
      <div>
        <div className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Performance</div>
        <PeriodRow label="Today" data={today} />
        <PeriodRow label="All time" data={all} />
        <p className="text-[10px] text-gray-600 mt-1 italic">
          Week / month / 6m / year analytics need persistent DB — scheduled for next phase.
        </p>
      </div>

      {wallet?.address && (
        <div className="text-[10px] text-gray-500 font-mono break-all" title={wallet.address}>
          {wallet.address.length > 16 ? `${wallet.address.slice(0,6)}…${wallet.address.slice(-4)}` : wallet.address}
        </div>
      )}

      {status?.last_error && <p className="text-bad text-xs">{status.last_error}</p>}
    </div>
  );
}

function PeriodRow({ label, data }: { label: string; data: ReturnType<typeof aggregate> }) {
  return (
    <div className="flex items-center justify-between text-xs py-0.5 border-t border-panel2 first-of-type:border-0">
      <span className="text-gray-400 w-20">{label}</span>
      <span className={`font-mono w-24 text-right ${data.realized >= 0 ? 'text-good' : 'text-bad'}`}>
        ${data.realized >= 0 ? '+' : ''}{data.realized.toFixed(2)}
      </span>
      <span className="font-mono text-gray-500 w-20 text-right">${data.fees.toFixed(2)} fees</span>
      <span className="font-mono text-gray-400 w-16 text-right">
        {data.closed > 0 ? `${(data.winRate * 100).toFixed(0)}%` : '—'}
      </span>
    </div>
  );
}
