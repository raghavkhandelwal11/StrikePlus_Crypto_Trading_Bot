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

// ---- Time / date — always formatted in IST (Asia/Kolkata) ----
//
// All UI timestamps are forced to India Standard Time per project owner.
// The chart's own time-axis is left alone (lightweight-charts manages it).

const IST_TIME = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
  hour12: false,
});

const IST_HHMM = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata',
  hour: '2-digit', minute: '2-digit',
  hour12: false,
});

const IST_DATETIME = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata',
  day: '2-digit', month: 'short',
  hour: '2-digit', minute: '2-digit',
  hour12: false,
});

function _parse(input: string | Date | number | null | undefined): Date | null {
  if (input == null) return null;
  const d = input instanceof Date ? input : new Date(input);
  return isNaN(d.getTime()) ? null : d;
}

/** HH:MM:SS in IST. Returns "—" if input is invalid. */
export function fmtTime(input: string | Date | number | null | undefined): string {
  const d = _parse(input); if (!d) return '—';
  return IST_TIME.format(d);
}

/** HH:MM in IST — compact, for column views. */
export function fmtTimeShort(input: string | Date | number | null | undefined): string {
  const d = _parse(input); if (!d) return '—';
  return IST_HHMM.format(d);
}

/** "12 May, 14:32" in IST. */
export function fmtDateTime(input: string | Date | number | null | undefined): string {
  const d = _parse(input); if (!d) return '—';
  return IST_DATETIME.format(d);
}

/** Current wall-clock HH:MM:SS in IST — for log row timestamps. */
export function nowIST(): string {
  return IST_TIME.format(new Date());
}
