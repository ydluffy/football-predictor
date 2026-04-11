"use client";

export function ProbBar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="flex items-center gap-3">
      <div className="w-8 text-xs text-zinc-500">{label}</div>
      <div className="flex-1 rounded-full bg-zinc-100">
        <div className="h-2 rounded-full bg-zinc-900" style={{ width: `${pct}%` }} />
      </div>
      <div className="w-12 text-right text-xs tabular-nums text-zinc-700">{pct.toFixed(1)}%</div>
    </div>
  );
}

