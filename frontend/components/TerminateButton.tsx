'use client';
// Big red button — stops every window and closes every position.
import { useState } from 'react';
import { api } from '../lib/api';

export default function TerminateButton({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function terminate() {
    if (!confirm('Terminate ALL trading windows and close every open position. Continue?')) return;
    setBusy(true); setErr(null);
    try {
      await api.terminateAll();
      onDone();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-panel rounded-xl p-3 space-y-2">
      <button
        onClick={terminate}
        disabled={busy}
        className="w-full bg-bad/15 hover:bg-bad/25 text-bad px-3 py-2 rounded font-medium text-sm border border-bad/30 disabled:opacity-50">
        {busy ? 'Terminating…' : 'Terminate all positions'}
      </button>
      <p className="text-[10px] text-gray-500 leading-tight">
        Stops every running window and force-closes every open position.
        Use the per-window Kill switch in the windows list to target one.
      </p>
      {err && <p className="text-bad text-xs">{err}</p>}
    </div>
  );
}
