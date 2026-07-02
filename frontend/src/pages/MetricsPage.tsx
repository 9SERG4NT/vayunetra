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
    return <div className="p-6 text-slate-400">No metrics yet — run <code>make evaluate</code>.</div>;
  }
  const cov = metrics.coverage ?? {};
  const horizons = ["24", "48", "72"];

  return (
    <div className="h-full overflow-y-auto p-6">
      <h2 className="mb-1 text-xl font-semibold text-slate-100">Forecast metrics</h2>
      <p className="mb-4 text-sm text-slate-400">
        Rolling-origin backtest (4 × 2-week folds). RMSE/MAE in µg/m³ (pm25). Skill = 1 − RMSE_model/RMSE_persistence.
      </p>
      <table className="mb-6 w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-800 text-left text-slate-400">
            <th className="p-2">Horizon</th><th className="p-2">Model RMSE</th>
            <th className="p-2">Persistence</th><th className="p-2">Climatology</th>
            <th className="p-2">CAMS</th><th className="p-2">Skill vs persistence</th>
          </tr>
        </thead>
        <tbody>
          {horizons.map((h) => (
            <tr key={h} className="border-b border-slate-900">
              <td className="p-2 font-medium text-slate-100">{h}h</td>
              <td className="p-2 text-sky-300">{rmse(metrics, h, "model")}</td>
              <td className="p-2 text-slate-300">{rmse(metrics, h, "persistence")}</td>
              <td className="p-2 text-slate-300">{rmse(metrics, h, "climatology")}</td>
              <td className="p-2 text-slate-300">{rmse(metrics, h, "cams")}</td>
              <td className="p-2 font-semibold text-emerald-300">{skill(metrics, h)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-300">
        <div className="mb-1 font-semibold text-slate-200">Coverage</div>
        <div>Stations: {String(cov.stations ?? "—")} ({String(cov.reference_stations ?? "—")} reference)</div>
        <div>pm25 rows: {String(cov.pm25_rows ?? "—")}</div>
        <div>Date range: {Array.isArray(cov.date_range) ? (cov.date_range as string[]).join(" → ") : "—"}</div>
      </div>

      <p className="mt-6 text-xs text-slate-500">
        Data: OpenAQ/CPCB · NASA FIRMS VIIRS · Open-Meteo ERA5 + CAMS · OpenStreetMap.
        Disclosure: hourly AQI proxy on hourly concentrations (official CPCB NAQI uses 24-h averages).
        Attribution is evidence-weighted, confidence-scored — not regulatory source apportionment.
      </p>
    </div>
  );
}
