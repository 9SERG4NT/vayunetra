import type { ReplayPreset } from "../types";

interface Props {
  timestamps: string[];
  presets: ReplayPreset[];
  index: number;
  onIndex: (i: number) => void;
  onPreset: (preset: ReplayPreset | null) => void;
}

function fmtIST(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
}

export default function TimeScrubber({ timestamps, presets, index, onIndex, onPreset }: Props) {
  const current = timestamps[index] ?? "";
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white/85 p-3.5 shadow-lg shadow-slate-900/5 backdrop-blur-md">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Time</span>
        <span className="font-mono text-sm font-medium text-slate-700">{fmtIST(current)}</span>
      </div>
      <input
        type="range"
        min={0}
        max={Math.max(0, timestamps.length - 1)}
        value={index}
        onChange={(e) => onIndex(Number(e.target.value))}
        className="w-full accent-sky-600"
      />
      <div className="mt-2.5 flex flex-wrap gap-2">
        <button
          onClick={() => onPreset(null)}
          className="rounded-full bg-sky-600 px-3.5 py-1 text-xs font-semibold text-white shadow-sm transition hover:bg-sky-500"
        >
          Latest
        </button>
        {presets.map((p) => (
          <button
            key={p.id}
            onClick={() => onPreset(p)}
            className="rounded-full border border-slate-200 bg-white px-3.5 py-1 text-xs font-medium text-slate-600 transition hover:border-sky-400 hover:text-sky-700"
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
