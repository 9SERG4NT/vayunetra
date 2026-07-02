import { useState } from "react";
import type { GrapStatus } from "../types";

const STAGE_COLOR = ["#334155", "#f97316", "#dc2626", "#b91c1c", "#7f1d1d"];

export default function GrapChip({ grap }: { grap: GrapStatus | null }) {
  const [open, setOpen] = useState(false);
  if (!grap || grap.grap === false || grap.headline_stage == null) return null;
  const stage = grap.headline_stage;
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="rounded-lg px-3 py-1.5 text-sm font-semibold text-white"
        style={{ backgroundColor: STAGE_COLOR[stage] ?? "#334155" }}
      >
        GRAP Stage {stage || "0"} · pred 48h {grap.predicted_stage_48h}
      </button>
      {open && (
        <div className="absolute z-20 mt-2 w-80 rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm shadow-xl">
          <div className="mb-2 font-semibold text-slate-100">{grap.label}</div>
          <ul className="list-disc space-y-1 pl-4 text-slate-300">
            {(grap.actions ?? []).map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
