'use client';

import { fmtPrice, fmtTime } from '../lib/format';

type Trade = {
  ts: string;
  side: string;
  strategy: string;
  amount_in: number;
  amount_out: number;
  price: number;
  pnl_usd: number;
  status: string;
  notional_usd?: number;
  gas_cost_usd?: number;
  lp_fee_usd?: number;
  reason?: string;
};

type Props = { trades: Trade[] };

function fmt(n: number, dp = 2) { return (n ?? 0).toFixed(dp); }

export default function TradesTable({ trades }: Props) {
  // Aggregate footer numbers
  const totalInvested = trades
    .filter(t => t.side === 'buy')
    .reduce((s, t) => s + (t.notional_usd ?? 0), 0);
  const netProfit = trades.reduce((s, t) => s + (t.pnl_usd ?? 0), 0);
  const totalFees = trades.reduce(
    (s, t) => s + (t.gas_cost_usd ?? 0) + (t.lp_fee_usd ?? 0), 0
  );
  const winners = trades.filter(t => (t.pnl_usd ?? 0) > 0).length;
  const closed  = trades.filter(t => t.side === 'sell').length;

  return (
    <div className="bg-panel rounded-xl p-4">
      <h3 className="text-sm uppercase tracking-wider text-gray-400 mb-2">Trades</h3>
      {trades.length === 0 ? (
        <p className="text-gray-500 text-sm">No trades yet.</p>
      ) : (
        <div className="overflow-auto max-h-80">
          <table className="w-full text-xs">
            <thead className="text-left text-gray-400 sticky top-0 bg-panel">
              <tr>
                <th className="py-1 pr-2">Time (IST)</th>
                <th className="pr-2">Strat</th>
                <th className="pr-2">Side</th>
                <th className="pr-2">Notional</th>
                <th className="pr-2">Price</th>
                <th className="pr-2">Net P&L</th>
                <th className="pr-2">Fees</th>
                <th className="pr-2">Reason</th>
              </tr>
            </thead>
            <tbody>
              {trades.slice().reverse().map((t, i) => {
                const fees = (t.gas_cost_usd ?? 0) + (t.lp_fee_usd ?? 0);
                return (
                  <tr key={i} className="border-t border-panel2">
                    <td className="py-1 pr-2 text-gray-400">{fmtTime(t.ts)}</td>
                    <td className="pr-2">{t.strategy}</td>
                    <td className={`pr-2 ${t.side === 'buy' ? 'text-good' : 'text-bad'}`}>{t.side}</td>
                    <td className="pr-2">${fmt(t.notional_usd ?? 0)}</td>
                    <td className="pr-2">${fmtPrice(t.price)}</td>
                    <td className={`pr-2 ${(t.pnl_usd ?? 0) >= 0 ? 'text-good' : 'text-bad'}`}>
                      {t.side === 'buy' ? '—' : `$${fmt(t.pnl_usd)}`}
                    </td>
                    <td className="pr-2 text-gray-400">${fmt(fees, 3)}</td>
                    <td className="pr-2 text-gray-400 truncate max-w-[180px]" title={t.reason}>{t.reason || ''}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Footer summary */}
      <div className="mt-3 pt-3 border-t border-panel2 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <SummaryStat label="Total invested" value={`$${fmt(totalInvested)}`} />
        <SummaryStat
          label="Net profit (after fees)"
          value={`$${netProfit >= 0 ? '+' : ''}${fmt(netProfit)}`}
          positive={netProfit >= 0}
        />
        <SummaryStat label="Total fees" value={`$${fmt(totalFees, 3)}`} muted />
        <SummaryStat
          label="Win rate"
          value={closed === 0 ? '—' : `${((winners / closed) * 100).toFixed(0)}% (${winners}/${closed})`}
        />
      </div>
    </div>
  );
}

function SummaryStat({
  label, value, positive, muted,
}: { label: string; value: string; positive?: boolean; muted?: boolean }) {
  const cls = muted
    ? 'text-gray-400'
    : positive === undefined ? ''
    : positive ? 'text-good' : 'text-bad';
  return (
    <div>
      <div className="text-gray-500 uppercase tracking-wider text-[10px]">{label}</div>
      <div className={`font-semibold text-base ${cls}`}>{value}</div>
    </div>
  );
}
