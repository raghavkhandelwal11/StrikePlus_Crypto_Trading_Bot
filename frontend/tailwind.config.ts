import type { Config } from 'tailwindcss';

export default {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0b0d10',
        panel: '#13161b',
        panel2: '#1a1f26',
        accent: '#22d3ee',
        good: '#4ade80',
        bad: '#f87171',
        warn: '#facc15',
      },
    },
  },
  plugins: [],
} satisfies Config;
