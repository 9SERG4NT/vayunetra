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
    <div className="h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-5xl">
        <h2 className="mb-1 text-xl font-semibold tracking-tight text-slate-900">
          Enforcement action queue
        </h2>
        <p className="mb-6 text-sm text-slate-500">
          Ranked by share × severity × persistence × exposure × actionability. Click a row for its evidence pack.
        </p>
        {loading ? (
          <p className="text-slate-400">Loading…</p>
        ) : actions.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-slate-400 shadow-sm">
            No active hotspots (AQI &gt; 200) in the current snapshot.
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/70 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                  <th className="p-3">#</th><th className="p-3">Locality</th><th className="p-3">Source</th>
                  <th className="p-3">Share</th><th className="p-3">Conf.</th><th className="p-3">AQI</th>
                  <th className="p-3">Score</th><th className="p-3">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {actions.map((a) => (
                  <tr key={a.id} className="border-b border-slate-100 transition last:border-0 hover:bg-sky-50/40">
                    <td className="p-3 text-slate-400">{a.id}</td>
                    <td className="p-3 font-semibold text-slate-800">{a.locality}</td>
                    <td className="p-3">
                      <span className="rounded-md px-2 py-0.5 text-xs font-medium text-white"
                            style={{ backgroundColor: SOURCE_COLOR[a.source] ?? "#64748b" }}>
                        {a.source}
                      </span>
                    </td>
                    <td className="p-3 text-slate-600">{Math.round(a.share * 100)}%</td>
                    <td className="p-3">
                      <span className="rounded-full px-2.5 py-0.5 text-xs font-semibold text-white"
                            style={{ backgroundColor: CONFIDENCE_COLOR[a.confidence] ?? "#64748b" }}>
                        {a.confidence}
                      </span>
                    </td>
                    <td className="p-3 font-bold" style={{ color: aqiColor(a.aqi) }}>{a.aqi}</td>
                    <td className="p-3">
                      <div className="h-2 w-24 rounded-full bg-slate-100">
                        <div className="h-2 rounded-full bg-sky-500"
                             style={{ width: `${Math.min(100, a.score * 400)}%` }} />
                      </div>
                    </td>
                    <td className="p-3">
                      <a href={api.evidenceUrl(city, a.id)} target="_blank" rel="noreferrer"
                         className="font-medium text-sky-600 hover:text-sky-500 hover:underline">Open →</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
