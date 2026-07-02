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
    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-slate-400">Time</span>
        <span className="font-mono text-sm text-slate-200">{fmtIST(current)}</span>
      </div>
      <input
        type="range"
        min={0}
        max={Math.max(0, timestamps.length - 1)}
        value={index}
        onChange={(e) => onIndex(Number(e.target.value))}
        className="w-full accent-sky-500"
      />
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          onClick={() => onPreset(null)}
          className="rounded-full bg-sky-600 px-3 py-1 text-xs font-medium text-white hover:bg-sky-500"
        >
          Latest
        </button>
        {presets.map((p) => (
          <button
            key={p.id}
            onClick={() => onPreset(p)}
            className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-200 hover:border-sky-500"
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
