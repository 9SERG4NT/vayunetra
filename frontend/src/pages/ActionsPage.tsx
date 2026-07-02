import { useEffect, useState } from "react";
import { api } from "../api";
import { CONFIDENCE_COLOR, SOURCE_COLOR, aqiColor } from "../theme";
import type { ActionItem } from "../types";

export default function ActionsPage({ city }: { city: string }) {
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.actions(city).then((a) => setActions(a.actions)).finally(() => setLoading(false));
  }, [city]);

  return (
    <div className="h-full overflow-y-auto p-6">
      <h2 className="mb-1 text-xl font-semibold text-slate-100">Enforcement action queue</h2>
      <p className="mb-4 text-sm text-slate-400">
        Ranked by share × severity × persistence × exposure × actionability. Click a row for its evidence pack.
      </p>
      {loading ? (
        <p className="text-slate-500">Loading…</p>
      ) : actions.length === 0 ? (
        <p className="text-slate-500">No active hotspots (AQI &gt; 200) in the current snapshot.</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-800 text-left text-slate-400">
              <th className="p-2">#</th><th className="p-2">Locality</th><th className="p-2">Source</th>
              <th className="p-2">Share</th><th className="p-2">Conf.</th><th className="p-2">AQI</th>
              <th className="p-2">Score</th><th className="p-2">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {actions.map((a) => (
              <tr key={a.id} className="border-b border-slate-900 hover:bg-slate-900/50">
                <td className="p-2 text-slate-500">{a.id}</td>
                <td className="p-2 font-medium text-slate-100">{a.locality}</td>
                <td className="p-2">
                  <span className="rounded px-2 py-0.5 text-xs text-white"
                        style={{ backgroundColor: SOURCE_COLOR[a.source] ?? "#64748b" }}>
                    {a.source}
                  </span>
                </td>
                <td className="p-2 text-slate-300">{Math.round(a.share * 100)}%</td>
                <td className="p-2">
                  <span className="rounded-full px-2 py-0.5 text-xs text-white"
                        style={{ backgroundColor: CONFIDENCE_COLOR[a.confidence] ?? "#64748b" }}>
                    {a.confidence}
                  </span>
                </td>
                <td className="p-2 font-semibold" style={{ color: aqiColor(a.aqi) }}>{a.aqi}</td>
                <td className="p-2">
                  <div className="h-2 w-24 rounded bg-slate-800">
                    <div className="h-2 rounded bg-sky-500"
                         style={{ width: `${Math.min(100, a.score * 400)}%` }} />
                  </div>
                </td>
                <td className="p-2">
                  <a href={api.evidenceUrl(city, a.id)} target="_blank" rel="noreferrer"
                     className="text-sky-400 hover:underline">Open →</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
