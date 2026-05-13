'use client';
// Minimal WS hook with auto-reconnect. Pushes events into a callback.
import { useEffect, useRef } from 'react';
import { WS_URL } from './api';

export type BotEvent =
  | { type: 'status'; data: any }
  | { type: 'wallet'; data: any }
  | { type: 'positions'; data: any }
  | { type: 'windows'; data: any }
  | { type: 'trade'; data: any }
  | { type: 'tick'; data: any }
  | { type: 'signal_rejected'; data: any }
  | { type: 'ping' };

export function useBotStream(onEvent: (e: BotEvent) => void) {
  const ref = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    let backoff = 500;

    function connect() {
      const ws = new WebSocket(WS_URL);
      ref.current = ws;
      ws.onopen = () => { backoff = 500; };
      ws.onmessage = (msg) => {
        try { onEvent(JSON.parse(msg.data)); } catch {}
      };
      ws.onclose = () => {
        if (cancelled) return;
        setTimeout(connect, Math.min(backoff *= 2, 8000));
      };
      ws.onerror = () => { ws.close(); };
    }

    connect();
    return () => { cancelled = true; ref.current?.close(); };
  }, [onEvent]);
}
