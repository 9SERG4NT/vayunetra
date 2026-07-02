import { useEffect, useState } from "react";
import { api } from "../api";
import type { CityInfo, Metrics } from "../types";

interface CityMetrics {
  id: string;
  name: string;
  metrics: Metrics | null;
}

function rmse(m: Metrics, h: string, method: string): string {
  const cell = m.horizons?.[h]?.[method];
  if (cell && typeof cell === "object" && "rmse" in cell) {
    const v = (cell as { rmse: number | null }).rmse;
    return v == null ? "—" : v.toFixed(1);
  }
  return "—";
}

function skill(m: Metrics, h: string): string {
  const v = m.horizons?.[h]?.skill_vs_persistence;
  return typeof v === "number" ? (v >= 0 ? `+${v.toFixed(3)}` : v.toFixed(3)) : "—";
}

export default function MetricsPage({ city }: { city: string }) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [compare, setCompare] = useState<CityMetrics[]>([]);

  useEffect(() => {
    api.metrics(city).then(setMetrics).catch(() => setMetrics(null));
  }, [city]);

  // Multi-city comparative strip: fetch every city's metrics once.
  useEffect(() => {
    api.cities().then((cs: CityInfo[]) =>
      Promise.all(
        cs.map((c) =>
          api.metrics(c.id)
            .then((m) => ({ id: c.id, name: c.name, metrics: m }))
            .catch(() => ({ id: c.id, name: c.name, metrics: null }))
        )
      ).then(setCompare)
    );
  }, []);

  if (!metrics || !metrics.horizons) {
    return <div className="p-8 text-slate-400">No metrics yet — run <code>make evaluate</code>.</div>;
  }
  const cov = metrics.coverage ?? {};
  const horizons = ["24", "48", "72"];

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-5xl">
        <h2 className="mb-1 text-xl font-semibold tracking-tight text-slate-900">Forecast metrics</h2>
        <p className="mb-6 text-sm text-slate-500">
          Rolling-origin backtest (4 × 2-week folds). RMSE/MAE in µg/m³ (pm25). Skill = 1 − RMSE_model/RMSE_persistence.
        </p>

        {compare.length > 1 && (
          <div className="mb-6">
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Multi-city comparison
            </h3>
            <div className="grid gap-4 sm:grid-cols-2">
              {compare.map((c) => {
                const m = c.metrics;
                const covC = (m?.coverage ?? {}) as Record<string, unknown>;
                const active = c.id === city;
                return (
                  <div
                    key={c.id}
                    className={`rounded-2xl border bg-white p-4 shadow-sm transition ${
                      active ? "border-sky-300 ring-2 ring-sky-100" : "border-slate-200"
                    }`}
                  >
                    <div className="mb-2 flex items-baseline justify-between">
                      <span className="font-semibold text-slate-800">{c.name}</span>
                      {active && <span className="text-[10px] font-semibold uppercase tracking-wider text-sky-500">viewing</span>}
                    </div>
                    {m?.horizons ? (
                      <>
                        <div className="mb-2 flex gap-2">
                          {horizons.map((h) => (
                            <div key={h} className="flex-1 rounded-xl bg-slate-50 px-2 py-1.5 text-center">
                              <div className="text-[10px] font-medium uppercase text-slate-400">{h}h skill</div>
                              <div className="text-sm font-bold text-emerald-600">{skill(m, h)}</div>
                            </div>
                          ))}
                        </div>
                        <div className="text-xs text-slate-500">
                          {String(covC.stations ?? "—")} stations · {String(covC.pm25_rows ?? "—")} pm25 rows
                        </div>
                      </>
                    ) : (
                      <div className="text-xs text-slate-400">No metrics for this city yet.</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="mb-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/70 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                <th className="p-3">Horizon</th><th className="p-3">Model RMSE</th>
                <th className="p-3">Persistence</th><th className="p-3">Climatology</th>
                <th className="p-3">CAMS</th><th className="p-3">Skill vs persistence</th>
              </tr>
            </thead>
            <tbody>
              {horizons.map((h) => (
                <tr key={h} className="border-b border-slate-100 last:border-0">
                  <td className="p-3 font-semibold text-slate-800">{h}h</td>
                  <td className="p-3 font-semibold text-sky-600">{rmse(metrics, h, "model")}</td>
                  <td className="p-3 text-slate-600">{rmse(metrics, h, "persistence")}</td>
                  <td className="p-3 text-slate-600">{rmse(metrics, h, "climatology")}</td>
                  <td className="p-3 text-slate-600">{rmse(metrics, h, "cams")}</td>
                  <td className="p-3 font-bold text-emerald-600">{skill(metrics, h)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
          <div className="mb-1.5 font-semibold text-slate-800">Coverage</div>
          <div>Stations: {String(cov.stations ?? "—")} ({String(cov.reference_stations ?? "—")} reference)</div>
          <div>pm25 rows: {String(cov.pm25_rows ?? "—")}</div>
          <div>Date range: {Array.isArray(cov.date_range) ? (cov.date_range as string[]).join(" → ") : "—"}</div>
        </div>

        <p className="mt-8 max-w-3xl text-xs leading-relaxed text-slate-400">
          Data: OpenAQ/CPCB · NASA FIRMS VIIRS · Open-Meteo ERA5 + CAMS · OpenStreetMap.
          Disclosure: hourly AQI proxy on hourly concentrations (official CPCB NAQI uses 24-h averages).
          Attribution is evidence-weighted, confidence-scored — not regulatory source apportionment.
        </p>
      </div>
    </div>
  );
}
