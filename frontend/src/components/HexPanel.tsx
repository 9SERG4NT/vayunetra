import { useEffect, useMemo, useState } from "react";
import {
  Area, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { api } from "../api";
import { CONFIDENCE_COLOR, SOURCE_COLOR } from "../theme";
import type { ActionItem, AttributionResponse, ForecastResponse } from "../types";
import AdvisoryModal from "./AdvisoryModal";

interface Props {
  city: string;
  hex: string;
  action?: ActionItem;
  onClose: () => void;
}

function istHour(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", hour: "2-digit" });
}

export default function HexPanel({ city, hex, action, onClose }: Props) {
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [attr, setAttr] = useState<AttributionResponse | null>(null);
  const [showAdvisory, setShowAdvisory] = useState(false);

  useEffect(() => {
    setForecast(null);
    setAttr(null);
    api.forecast(city, hex).then(setForecast).catch(() => setForecast(null));
    api.attribution(city, hex).then(setAttr).catch(() => setAttr(null));
  }, [city, hex]);

  const chartData = useMemo(() => {
    if (!forecast) return [];
    const hist = forecast.history_72h.map((p) => ({ t: p.t, obs: p.pm25 }));
    const fc = forecast.forecast.map((p) => ({
      t: p.t, pred: p.pm25, band: [p.pi_low, p.pi_high] as [number | null, number | null],
    }));
    return [...hist, ...fc];
  }, [forecast]);

  const pieData = useMemo(() => {
    if (!attr) return [];
    return Object.entries(attr.shares).map(([name, value]) => ({ name, value: Math.round(value * 100) }));
  }, [attr]);

  const ev = attr?.evidence ?? {};

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto border-l border-slate-800 bg-slate-950 p-4">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-semibold text-slate-100">{action?.locality || "Selected hex"}</h3>
          <p className="font-mono text-xs text-slate-500">{hex}</p>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-white">✕</button>
      </div>

      <section>
        <h4 className="mb-1 text-xs uppercase tracking-wide text-slate-400">72h history + forecast</h4>
        <ResponsiveContainer width="100%" height={190}>
          <ComposedChart data={chartData} margin={{ top: 5, right: 8, bottom: 0, left: -18 }}>
            <XAxis dataKey="t" tickFormatter={istHour} tick={{ fontSize: 9, fill: "#94a3b8" }} minTickGap={40} />
            <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} />
            <Tooltip
              labelFormatter={istHour}
              contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 12 }}
            />
            <Area dataKey="band" stroke="none" fill="#2563eb" fillOpacity={0.18} />
            <Line dataKey="obs" stroke="#e2e8f0" dot={false} strokeWidth={1.6} name="observed" />
            <Line dataKey="pred" stroke="#38bdf8" dot strokeWidth={1.8} name="forecast" />
          </ComposedChart>
        </ResponsiveContainer>
      </section>

      <section>
        <div className="mb-1 flex items-center justify-between">
          <h4 className="text-xs uppercase tracking-wide text-slate-400">Source attribution</h4>
          {attr && (
            <span
              className="rounded-full px-2 py-0.5 text-xs font-semibold text-white"
              style={{ backgroundColor: CONFIDENCE_COLOR[attr.confidence] ?? "#64748b" }}
            >
              {attr.confidence}
            </span>
          )}
        </div>
        <ResponsiveContainer width="100%" height={190}>
          <PieChart>
            <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={40} outerRadius={70} paddingAngle={2}>
              {pieData.map((d) => (
                <Cell key={d.name} fill={SOURCE_COLOR[d.name] ?? "#94a3b8"} />
              ))}
            </Pie>
            <Legend wrapperStyle={{ fontSize: 10 }} />
            <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 12 }} />
          </PieChart>
        </ResponsiveContainer>
        {attr && (
          <p className="text-xs text-slate-500">
            Dispersion effect (meteorology): {Math.round(attr.met_modifier * 100)}% — shown separately, not a source.
          </p>
        )}
      </section>

      <section className="rounded-lg border border-slate-800 bg-slate-900/50 p-2 text-xs text-slate-300">
        <div className="mb-1 font-semibold text-slate-200">Evidence</div>
        <div>Fires (7d): {String(ev.fire_n ?? "—")} · FRP Σ {String(ev.frp_sum ?? "—")}</div>
        <div>Nearest station: {String(ev.station_km ?? "—")} km · biomass lift {String(ev.biomass_lift ?? "—")}</div>
      </section>

      <div className="mt-auto flex gap-2">
        {action && (
          <a
            href={api.evidenceUrl(city, action.id)}
            target="_blank"
            rel="noreferrer"
            className="flex-1 rounded-lg bg-sky-600 px-3 py-2 text-center text-sm font-medium text-white hover:bg-sky-500"
          >
            Generate evidence pack
          </a>
        )}
        <button
          onClick={() => setShowAdvisory(true)}
          className="flex-1 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:border-sky-500"
        >
          Advisory
        </button>
      </div>

      {showAdvisory && <AdvisoryModal city={city} hex={hex} onClose={() => setShowAdvisory(false)} />}
    </div>
  );
}
