import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

// Give up polling after this long — if the backend died mid-refresh the status
// endpoint would report running=true forever and the spinner would never stop.
const POLL_DEADLINE_MS = 15 * 60 * 1000;

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

  // Stop polling when the component unmounts (route change / HMR) so the
  // interval doesn't keep firing against an unmounted component.
  useEffect(() => () => window.clearInterval(poll.current), []);

  const refresh = async () => {
    if (running) return;
    setRunning(true);
    await api.refreshNow().catch(() => {});
    // poll until the background refresh finishes, then reload everything
    const startedAt = Date.now();
    window.clearInterval(poll.current);
    poll.current = window.setInterval(async () => {
      const s = await api.refreshStatus().catch(() => null);
      const timedOut = Date.now() - startedAt > POLL_DEADLINE_MS;
      if ((s && !s.running) || timedOut) {
        window.clearInterval(poll.current);
        setRunning(false);
        loadFreshness();
        if (!timedOut) onRefreshed?.();
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
