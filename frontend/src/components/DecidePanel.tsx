import { useEffect, useState } from "react";
import { api } from "../api";
import { CONFIDENCE_COLOR } from "../theme";
import type { DecideHex, Scenario } from "../types";

function RangeBar({ s, scale }: { s: Scenario; scale: number }) {
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / scale) * 100))}%`;
  return (
    <div className="relative h-5 w-full rounded-full bg-slate-100">
      <div
        className="absolute top-0 h-5 rounded-full bg-sky-200"
        style={{ left: pct(s.delta_aqi.lo), width: pct(s.delta_aqi.hi - s.delta_aqi.lo) }}
      />
      <div
        className="absolute top-[-2px] h-[24px] w-[3px] rounded bg-sky-600"
        style={{ left: pct(s.delta_aqi.mid) }}
        title={`mid ΔAQI ${s.delta_aqi.mid}`}
      />
      <span className="absolute right-1.5 top-0.5 text-[10px] font-semibold text-slate-500">
        {s.delta_aqi.lo}–{s.delta_aqi.hi}
      </span>
    </div>
  );
}

export default function DecidePanel({ city, hex }: { city: string; hex: string }) {
  const [data, setData] = useState<DecideHex | null>(null);
  const [ordering, setOrdering] = useState<string | null>(null);
  const [orderMs, setOrderMs] = useState<Record<string, number>>({});

  useEffect(() => {
    setData(null);
    api.decideHex(city, hex).then(setData).catch(() => setData(null));
  }, [city, hex]);

  const generateOrder = async (interventionId: string) => {
    setOrdering(interventionId);
    try {
      const { url, generation_ms } = await api.createOrder(city, hex, interventionId);
      setOrderMs((m) => ({ ...m, [interventionId]: generation_ms }));
      window.open(url, "_blank");
    } finally {
      setOrdering(null);
    }
  };

  if (!data) return <div className="p-2 text-sm text-slate-400">Loading decision options…</div>;
  const scale = Math.max(10, ...data.interventions.map((s) => s.delta_aqi.hi));

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-xl border border-slate-200 bg-slate-50 p-3">
        <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Why this hotspot
        </h4>
        <ul className="space-y-1 text-xs text-slate-600">
          {data.why.bullets.map((b, i) => (
            <li key={i} className="flex gap-1.5">
              <span className="text-sky-500">•</span>
              <span>{b}</span>
            </li>
          ))}
        </ul>
        <p className="mt-2 border-t border-slate-200 pt-2 text-xs font-semibold text-slate-700">
          {data.why.conclusion}
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Intervention options — model-implied ΔAQI (range)
        </h4>
        {data.interventions.length === 0 && (
          <p className="text-xs text-slate-400">No applicable interventions (no attributable source share).</p>
        )}
        {data.interventions.map((s) => (
          <div key={s.intervention_id} className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="mb-1.5 flex items-start justify-between gap-2">
              <div className="text-sm font-semibold text-slate-800">{s.label}</div>
              <span
                className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold text-white"
                style={{ backgroundColor: CONFIDENCE_COLOR[s.confidence] ?? "#64748b" }}
              >
                {s.confidence}
                {s.confidence_downgraded ? " ↓" : ""}
              </span>
            </div>
            <RangeBar s={s} scale={scale} />
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
              <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-600">{s.department}</span>
              <span>⏱ {s.time_to_impact_h[0]}–{s.time_to_impact_h[1]}h</span>
              <span>💠 {s.cost_tier}</span>
              <span>method: {s.method}</span>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <button
                onClick={() => generateOrder(s.intervention_id)}
                disabled={ordering === s.intervention_id}
                className="rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
              >
                {ordering === s.intervention_id ? "Generating…" : "Generate order"}
              </button>
              {orderMs[s.intervention_id] != null && (
                <span className="text-[11px] text-emerald-600">
                  order in {(orderMs[s.intervention_id] / 1000).toFixed(1)}s
                </span>
              )}
            </div>
          </div>
        ))}
      </section>

      <p className="text-[11px] leading-relaxed text-slate-400">
        Planning estimates from attribution × editable priors (config/interventions.yaml); model-implied, not a
        causal guarantee. See Methods (docs/DECISION_LAYER.md).
      </p>
    </div>
  );
}
