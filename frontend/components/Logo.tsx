'use client';
// StrikePlus brand mark.
//
// Mark anatomy:
//   - Dark rounded-square shield with a soft inner gradient
//   - A bold white zigzag "breakout" line (the Strike)
//   - A cyan "+" disc capping the highest point (the Plus, premium edge)
//   - A subtle outer ring on hover suggests action / interactivity
//
// Wordmark uses a small caps + weight-contrast treatment:
//   "Strike" semibold gray-100 · "+" cyan accent · "Plus" lighter
//   Below: a 0.3em-letter-spaced tagline in muted text.

type Props = {
  size?: number;              // pixel size of the mark
  showWordmark?: boolean;     // hide wordmark when used in tight spaces (favicon-ish)
  showTagline?: boolean;
  className?: string;
};

export default function Logo({
  size = 38, showWordmark = true, showTagline = true, className = '',
}: Props) {
  return (
    <div className={`flex items-center gap-3 select-none ${className}`}>
      <LogoMark size={size} />
      {showWordmark && (
        <div className="leading-none">
          <div className="text-[19px] font-semibold tracking-tight text-gray-100">
            Strike<span className="text-accent">Plus</span>
          </div>
          {showTagline && (
            <div className="mt-1 text-[9px] uppercase tracking-[0.32em] text-gray-500 font-medium">
              Adaptive Algo Trading · BSC
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function LogoMark({ size = 38 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 48 48"
      width={size}
      height={size}
      role="img"
      aria-label="StrikePlus"
      className="shrink-0 drop-shadow-[0_2px_8px_rgba(34,211,238,0.15)]"
    >
      <defs>
        {/* Soft inner gradient on the shield */}
        <linearGradient id="sp-shield" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%"  stopColor="#1a2230" />
          <stop offset="100%" stopColor="#0c1116" />
        </linearGradient>
        {/* Subtle gradient stroke on the zigzag for depth */}
        <linearGradient id="sp-stroke" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%"  stopColor="#e7eaee" />
          <stop offset="60%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#22d3ee" />
        </linearGradient>
        {/* Glow filter on the plus cap */}
        <filter id="sp-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="1.2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Shield */}
      <rect x="2" y="2" width="44" height="44" rx="11"
            fill="url(#sp-shield)"
            stroke="#2a3340" strokeWidth="1" />

      {/* Thin diagonal accent line for depth (chart-grid feel) */}
      <line x1="6" y1="38" x2="42" y2="10" stroke="#1f2a36" strokeWidth="0.6" />

      {/* The Strike — bold zigzag breakout */}
      <path
        d="M 11 32 L 19 24 L 24 28 L 33 14"
        stroke="url(#sp-stroke)"
        strokeWidth="3.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />

      {/* The Plus cap — accent disc at the apex of the strike */}
      <g filter="url(#sp-glow)">
        <circle cx="36" cy="12" r="5.6" fill="#22d3ee" />
        <path d="M 36 9 L 36 15 M 33 12 L 39 12"
              stroke="#0b0d10" strokeWidth="1.8" strokeLinecap="round" />
      </g>
    </svg>
  );
}
