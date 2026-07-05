import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

export default function LiveStatus({ city, onRefreshed }: { city: string; onRefreshed?: () => void }) {
  const [age, setAge] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const poll = useRef<number | undefined>(undefined);

  const loadFreshness = useCallback(() => {
    api.freshness(city).then((f) => setAge(f.age_hours)).catch(() => setAge(null));
  }, [city]);

  useEffect(() => {
    loadFreshness();
  }, [loadFreshness]);

  const refresh = async () => {
    if (running) return;
    setRunning(true);
    await api.refreshNow().catch(() => {});
    // poll until the background refresh finishes, then reload everything
    window.clearInterval(poll.current);
    poll.current = window.setInterval(async () => {
      const s = await api.refreshStatus().catch(() => null);
      if (s && !s.running) {
        window.clearInterval(poll.current);
        setRunning(false);
        loadFreshness();
        onRefreshed?.();
      }
    }, 3000);
  };

  const label =
    age == null ? "—" : age < 1 ? `${Math.round(age * 60)} min ago` : `${age.toFixed(1)} h ago`;
  const fresh = age != null && age <= 3;

  return (
    <div className="flex items-center gap-2">
      <span className="hidden items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-500 sm:inline-flex">
        <span className={`h-2 w-2 rounded-full ${fresh ? "bg-emerald-500" : "bg-amber-500"} ${running ? "animate-pulse" : ""}`} />
        data {label}
      </span>
      <button
        onClick={refresh}
        disabled={running}
        title="Pull the latest station readings, fires and forecast"
        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:border-sky-400 hover:text-sky-700 disabled:opacity-60"
      >
        <span className={`text-[14px] leading-none ${running ? "inline-block animate-spin" : ""}`}>↻</span>
        {running ? "Refreshing…" : "Refresh"}
      </button>
    </div>
  );
}
