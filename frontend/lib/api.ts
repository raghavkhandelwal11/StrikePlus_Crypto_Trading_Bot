// Thin client for the FastAPI backend.

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  // Status & legacy
  status: () => jsonFetch<any>('/bot/status'),
  releaseKill: () => jsonFetch<any>('/bot/release-kill', { method: 'POST', body: '{}' }),

  // Multi-window
  listWindows: () => jsonFetch<{ windows: any[]; count: number }>('/bot/windows'),
  createWindow: (body: any) =>
    jsonFetch<any>('/bot/windows', { method: 'POST', body: JSON.stringify(body) }),
  stopWindow: (id: string) =>
    jsonFetch<any>(`/bot/windows/${id}/stop`, { method: 'POST', body: '{}' }),
  killWindow: (id: string) =>
    jsonFetch<any>(`/bot/windows/${id}/kill`, { method: 'POST', body: '{}' }),
  extendWindow: (id: string, additional_seconds: number) =>
    jsonFetch<any>(`/bot/windows/${id}/extend`, {
      method: 'POST', body: JSON.stringify({ additional_seconds }),
    }),
  closeWindowPosition: (id: string, token: string) =>
    jsonFetch<any>(`/bot/windows/${id}/positions/${token}/close`, {
      method: 'POST', body: '{}',
    }),
  terminateAll: () =>
    jsonFetch<any>('/bot/terminate-all', { method: 'POST', body: '{}' }),

  // Data
  trades: (limit = 100) => jsonFetch<any>(`/bot/trades?limit=${limit}`),
  strategies: () => jsonFetch<any>('/bot/strategies'),
  performance: () => jsonFetch<any>('/bot/performance'),
  wallet: () => jsonFetch<any>('/wallet'),
  positions: () => jsonFetch<any>('/positions'),
  ohlcv: (symbol: string, interval: string, limit = 200) =>
    jsonFetch<any[]>(`/market/ohlcv?symbol=${symbol}&interval=${interval}&limit=${limit}`),
  pairs: () => jsonFetch<{ pairs: any[]; count: number }>('/market/pairs'),
  headlineTickers: () => jsonFetch<{ tickers: any[] }>('/market/headline'),
  backtest: (body: any) =>
    jsonFetch<any>('/backtest', { method: 'POST', body: JSON.stringify(body) }),
};

export const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';

// ---- Types ----

export type TradingWindow = {
  id: string;
  status: 'running' | 'stopped' | 'killed' | 'completed' | 'error';
  started_at: string;
  deadline_at: string;
  duration_seconds: number;
  tokens: string[];
  strategy_category: string;
  auto_switch: boolean;
  paper_mode: boolean;
  max_deploy_usd: number;
  deployed_usd: number;
  realized_pnl_usd: number;
  trade_count: number;
  open_positions: number;
  kill_switch: boolean;
  extended_by_seconds: number;
  phase?: string;        // warmup | analyzing | pending | entering | holding | cooldown | waiting
  reasoning?: string;    // human-readable explanation shown in the window card
};

export type Pair = {
  symbol: string;
  token: string;
  label: string;
  last_price?: number;
  price_change_pct?: number;
  high_24h?: number;
  low_24h?: number;
  volume_24h?: number;
  quote_volume_24h?: number;
};

export type Position = {
  token: string;
  units: number;
  avg_entry_price: number;
  cost_basis_usd: number;
  mark_price?: number;
  unrealized_pnl_usd?: number;
  unrealized_pnl_pct?: number;
  strategy: string;
  stop_loss?: number;
  take_profit?: number;
  initial_risk?: number;
  window_id?: string;
};
