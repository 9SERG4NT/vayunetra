import { useState } from "react";
import type { GrapStatus } from "../types";

const STAGE_COLOR = ["#64748b", "#f97316", "#dc2626", "#b91c1c", "#7f1d1d"];

export default function GrapChip({ grap }: { grap: GrapStatus | null }) {
  const [open, setOpen] = useState(false);
  if (!grap || grap.grap === false || grap.headline_stage == null) return null;
  const stage = grap.headline_stage;
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="rounded-xl px-3.5 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:opacity-90"
        style={{ backgroundColor: STAGE_COLOR[stage] ?? "#64748b" }}
      >
        GRAP Stage {stage || "0"} · pred 48h {grap.predicted_stage_48h}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 rounded-2xl border border-slate-200 bg-white p-4 text-sm shadow-xl shadow-slate-900/10">
          <div className="mb-2 font-semibold text-slate-800">{grap.label}</div>
          <ul className="list-disc space-y-1.5 pl-4 text-slate-600">
            {(grap.actions ?? []).map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
