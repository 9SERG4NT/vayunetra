import { useEffect, useState } from "react";
import { api } from "../api";
import type { Metrics } from "../types";

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

  useEffect(() => {
    api.metrics(city).then(setMetrics).catch(() => setMetrics(null));
  }, [city]);

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
