'use client';

type LogEntry = { ts: string; level: 'info' | 'warn' | 'error'; msg: string };

export default function LogsPanel({ logs }: { logs: LogEntry[] }) {
  return (
    <div className="bg-panel rounded-xl p-4">
      <h3 className="text-sm uppercase tracking-wider text-gray-400 mb-2">Logs</h3>
      <div className="font-mono text-xs max-h-72 overflow-auto space-y-1">
        {logs.length === 0 && <p className="text-gray-500">Waiting for events…</p>}
        {logs.slice().reverse().map((l, i) => (
          <div key={i} className={
            l.level === 'error' ? 'text-bad' :
            l.level === 'warn' ? 'text-warn' : 'text-gray-300'
          }>
            <span className="text-gray-500">{l.ts}</span> {l.msg}
          </div>
        ))}
      </div>
    </div>
  );
}
