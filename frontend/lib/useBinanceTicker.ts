'use client';
// Subscribes directly to Binance's public miniTicker stream for the given
// symbol. Pushes a price update roughly once per second straight from the
// exchange — no backend round-trip, no polling. Reconnects with exponential
// backoff on disconnect. Caller is responsible for unmounting when the
// symbol changes (the hook handles it via dependency array).
//
// Binance docs: https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md
import { useEffect, useRef, useState } from 'react';

type Tick = {
  symbol: string;
  price: number;
  ts: number;     // ms epoch
};

export function useBinanceTicker(symbol: string | null): Tick | null {
  const [tick, setTick] = useState<Tick | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!symbol) return;
    setTick(null);

    let cancelled = false;
    let backoff = 500;

    function connect() {
      const url = `wss://stream.binance.com:9443/ws/${symbol.toLowerCase()}@miniTicker`;
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => { backoff = 500; };
      ws.onmessage = (msg) => {
        try {
          const d = JSON.parse(msg.data);
          // miniTicker payload: { e, E, s, c (close price), o, h, l, v, q }
          setTick({
            symbol: d.s,
            price: parseFloat(d.c),
            ts: Number(d.E) || Date.now(),
          });
        } catch { /* ignore malformed */ }
      };
      ws.onclose = () => {
        if (cancelled) return;
        setTimeout(connect, Math.min(backoff *= 2, 5000));
      };
      ws.onerror = () => { ws.close(); };
    }

    connect();
    return () => { cancelled = true; wsRef.current?.close(); };
  }, [symbol]);

  return tick;
}
