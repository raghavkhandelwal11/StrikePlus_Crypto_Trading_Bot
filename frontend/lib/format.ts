// Centralized number formatting so the whole UI agrees on precision.
//
// Rule of thumb:
//   - Asset PRICES use 4 decimal places (per user spec)
//   - USD AMOUNTS / PnL use 2 decimal places
//   - Token UNITS use 4 decimal places
//   - PERCENTAGES use 2 decimal places

export function fmtPrice(p: number | undefined | null): string {
  if (p == null || !isFinite(p)) return '—';
  // For sub-cent tokens (e.g. $0.000123), 4dp would round to zero. Keep
  // 4 significant figures in that case so the chart line is meaningful.
  if (Math.abs(p) > 0 && Math.abs(p) < 0.01) return p.toPrecision(4);
  return p.toFixed(4);
}

export function fmtUsd(amount: number | undefined | null, dp = 2, withSign = false): string {
  if (amount == null || !isFinite(amount)) return '—';
  const abs = Math.abs(amount).toFixed(dp);
  if (withSign) {
    if (amount > 0) return `+$${abs}`;
    if (amount < 0) return `-$${abs}`;
    return `$${abs}`;
  }
  if (amount < 0) return `-$${abs}`;
  return `$${abs}`;
}

export function fmtUnits(u: number | undefined | null): string {
  if (u == null || !isFinite(u)) return '—';
  return u.toFixed(4);
}

export function fmtPct(p: number | undefined | null, withSign = true): string {
  if (p == null || !isFinite(p)) return '—';
  const v = p.toFixed(2);
  if (withSign && p > 0) return `+${v}%`;
  return `${v}%`;
}
