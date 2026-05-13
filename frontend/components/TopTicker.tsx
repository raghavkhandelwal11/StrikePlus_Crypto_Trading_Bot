'use client';
// Headline price bar — BTC/ETH/BNB live with 24h % change. Updates every 5s
// against the backend, which now caches Binance tickers for 2s.
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { fmtPrice, fmtPct } from '../lib/format';

type Ticker = {
  symbol: string;
  last_price: number;
  price_change_pct: number;
};

export default function TopTicker() {
  const [tickers, setTickers] = useState<Ticker[]>([]);
  const [updatedAt, setUpdatedAt] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await api.headlineTickers();
        if (cancelled) return;
        setTickers(res.tickers || []);
        setUpdatedAt(new Date().toLocaleTimeString());
      } catch (e) {
        // Silent — banner is non-essential
      }
    }
    load();
    const t = setInterval(load, 5_000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  return (
    <div className="bg-panel rounded-xl px-4 py-2 flex items-center gap-6 overflow-x-auto">
      <span className="text-[10px] uppercase tracking-widest text-gray-500 shrink-0">Markets</span>
      {tickers.length === 0 ? (
        <span className="text-gray-500 text-sm">loading…</span>
      ) : tickers.map(t => (
        <div key={t.symbol} className="flex items-baseline gap-2 shrink-0">
          <span className="font-medium text-sm">{t.symbol.replace('USDT', '')}</span>
          <span className="text-base font-mono">${fmtPrice(t.last_price)}</span>
          <span className={`text-xs font-medium ${t.price_change_pct >= 0 ? 'text-good' : 'text-bad'}`}>
            {t.price_change_pct >= 0 ? '▲' : '▼'} {Math.abs(t.price_change_pct).toFixed(2)}%
          </span>
        </div>
      ))}
      <span className="ml-auto text-[10px] text-gray-500 shrink-0">{updatedAt}</span>
    </div>
  );
}
