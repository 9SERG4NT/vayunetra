import { useEffect, useRef, useState } from "react";
import DispatchMap, { INSPECTOR_COLORS } from "../components/DispatchMap";
import { api } from "../api";
import type { CityInfo, CityScenario, DispatchPlan, GridCell } from "../types";

export default function DecidePage({ city, cityInfo }: { city: string; cityInfo?: CityInfo }) {
  const [scenarios, setScenarios] = useState<CityScenario[]>([]);
  const [cells, setCells] = useState<GridCell[]>([]);
  const [inspectors, setInspectors] = useState(10);
  const [shift, setShift] = useState(8);
  const [plan, setPlan] = useState<DispatchPlan | null>(null);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const debounce = useRef<number | undefined>(undefined);

  useEffect(() => {
    setScenarios([]);
    setPlan(null);
    api.decideCity(city).then((d) => setScenarios(d.scenarios)).catch(() => setScenarios([]));
    api.grid(city).then((g) => setCells(g.cells)).catch(() => setCells([]));
  }, [city]);

  useEffect(() => {
    window.clearTimeout(debounce.current);
    setLoadingPlan(true);
    debounce.current = window.setTimeout(() => {
      api.dispatch(city, inspectors, shift)
        .then(setPlan)
        .catch(() => setPlan(null))
        .finally(() => setLoadingPlan(false));
    }, 250);
    return () => window.clearTimeout(debounce.current);
  }, [city, inspectors, shift]);

  const bc = plan?.baseline_comparison;

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-6xl">
        <h2 className="mb-1 text-xl font-semibold tracking-tight text-slate-900">Decision support</h2>
        <p className="mb-6 text-sm text-slate-500">
          City-level scenario outcomes (planning estimates, ranges) and an inspector dispatch plan optimised for impact.
        </p>

        {/* Scenario comparison */}
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Intervention scenarios — city aggregate
        </h3>
        <div className="mb-8 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/70 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                <th className="p-3">Intervention</th><th className="p-3">Hexes</th>
                <th className="p-3">Mean ΔAQI (exposure-wtd)</th><th className="p-3">Person-hours avoided (proxy)</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.length === 0 && (
                <tr><td colSpan={4} className="p-4 text-slate-400">Loading scenarios…</td></tr>
              )}
              {scenarios.map((s) => (
                <tr key={s.intervention_id} className="border-b border-slate-100 last:border-0">
                  <td className="p-3 font-medium text-slate-800">{s.label}</td>
                  <td className="p-3 text-slate-600">{s.hexes_affected}</td>
                  <td className="p-3 font-semibold text-sky-600">{s.delta_aqi_weighted_mean}</td>
                  <td className="p-3 text-slate-600">{s.person_hours_avoided_total.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Dispatch */}
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Inspector dispatch optimiser
        </h3>
        <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
          <div className="h-[460px] overflow-hidden rounded-2xl border border-slate-200 shadow-sm">
            {cityInfo && <DispatchMap bbox={cityInfo.bbox} cells={cells} plan={plan?.plan ?? []} depot={plan?.depot ?? null} />}
          </div>

          <div className="flex flex-col gap-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <label className="mb-1 flex items-center justify-between text-sm font-medium text-slate-700">
                Inspectors <span className="font-bold text-sky-600">{inspectors}</span>
              </label>
              <input type="range" min={1} max={50} value={inspectors}
                     onChange={(e) => setInspectors(Number(e.target.value))} className="w-full accent-sky-600" />
              <label className="mb-1 mt-3 flex items-center justify-between text-sm font-medium text-slate-700">
                Shift hours <span className="font-bold text-sky-600">{shift}</span>
              </label>
              <input type="range" min={4} max={12} value={shift}
                     onChange={(e) => setShift(Number(e.target.value))} className="w-full accent-sky-600" />
            </div>

            {bc && (
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-wider text-emerald-600">vs geography-blind naive plan</div>
                <div className="mt-1 text-2xl font-bold text-emerald-700">
                  +{bc.impact_gain_pct}% impact
                </div>
                <div className="text-sm text-emerald-700">
                  −{bc.travel_km_saved} km travel · {plan?.totals.sites_covered} sites covered
                </div>
                {loadingPlan && <div className="mt-1 text-xs text-emerald-600">recomputing…</div>}
              </div>
            )}

            <div className="max-h-[220px] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
              {(plan?.plan ?? []).filter((r) => r.stops.length > 0).map((r) => (
                <div key={r.inspector_id} className="mb-2 border-b border-slate-100 pb-2 last:border-0">
                  <div className="mb-0.5 flex items-center gap-2 text-sm font-semibold text-slate-800">
                    <span className="inline-block h-3 w-3 rounded-full"
                          style={{ backgroundColor: `rgb(${INSPECTOR_COLORS[(r.inspector_id - 1) % INSPECTOR_COLORS.length].join(",")})` }} />
                    Inspector {r.inspector_id} · {r.stops.length} stops · {r.route_km} km · {Math.round(r.utilisation * 100)}% util
                  </div>
                  <div className="pl-5 text-xs text-slate-500">
                    {r.stops.map((s, i) => (
                      <span key={s.hex}>{i > 0 ? " → " : ""}{s.locality} ({s.eta_ist})</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <p className="mt-6 text-[11px] leading-relaxed text-slate-400">
          Planning estimates from attribution × editable priors (config/interventions.yaml). Dispatch is a deterministic
          greedy insertion optimiser under a shift-hours budget — a prioritisation aid, not a causal guarantee. See docs/DECISION_LAYER.md.
        </p>
      </div>
    </div>
  );
}
