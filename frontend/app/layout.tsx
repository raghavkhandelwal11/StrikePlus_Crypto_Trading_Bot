import type { Metadata } from 'next';
import '../styles/globals.css';

// Inline SVG favicon — matches the brand mark used in the dashboard header.
// Encoded as a data URI so it ships with the page; no external asset needed.
const faviconSvg = `
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'>
  <defs>
    <linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='%231a2230'/>
      <stop offset='100%' stop-color='%230c1116'/>
    </linearGradient>
  </defs>
  <rect x='2' y='2' width='44' height='44' rx='11' fill='url(%23g)'/>
  <path d='M 11 32 L 19 24 L 24 28 L 33 14' stroke='%23ffffff' stroke-width='3.6' stroke-linecap='round' stroke-linejoin='round' fill='none'/>
  <circle cx='36' cy='12' r='5.6' fill='%2322d3ee'/>
  <path d='M 36 9 L 36 15 M 33 12 L 39 12' stroke='%230b0d10' stroke-width='1.8' stroke-linecap='round'/>
</svg>
`.replace(/\n\s*/g, '');

export const metadata: Metadata = {
  title: 'StrikePlus — Adaptive Algo Trading',
  description: 'Decentralized trading on Binance Smart Chain via PancakeSwap V2. Multi-strategy, ATR-based risk, online learning.',
  icons: {
    icon: [{ url: `data:image/svg+xml,${faviconSvg}` }],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
