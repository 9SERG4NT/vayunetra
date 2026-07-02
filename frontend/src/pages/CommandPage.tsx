import { useEffect, useMemo, useRef, useState } from "react";
import MapView from "../components/MapView";
import TimeScrubber from "../components/TimeScrubber";
import HexPanel from "../components/HexPanel";
import { api } from "../api";
import type {
  ActionItem, CityInfo, FireDot, GridCell, ReplayPreset, Station, Vulnerability,
} from "../types";

export default function CommandPage({ city, cityInfo }: { city: string; cityInfo?: CityInfo }) {
  const [timestamps, setTimestamps] = useState<string[]>([]);
  const [presets, setPresets] = useState<ReplayPreset[]>([]);
  const [index, setIndex] = useState(0);
  const [cells, setCells] = useState<GridCell[]>([]);
  const [fires, setFires] = useState<FireDot[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [vulnerability, setVulnerability] = useState<Vulnerability | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [showFires, setShowFires] = useState(true);
  const [showVuln, setShowVuln] = useState(false);
  const debounce = useRef<number | undefined>(undefined);

  // Load per-city static data.
  useEffect(() => {
    setSelected(null);
    api.timeline(city).then((t) => {
      setTimestamps(t.timestamps);
      setPresets(t.presets);
      setIndex(Math.max(0, t.timestamps.length - 1));
    });
    api.stations(city).then(setStations).catch(() => setStations([]));
    api.actions(city).then((a) => setActions(a.actions)).catch(() => setActions([]));
    api.vulnerability(city).then(setVulnerability).catch(() => setVulnerability(null));
  }, [city]);

  // Debounced grid + fires refetch when the scrubber moves.
  useEffect(() => {
    const t = timestamps[index];
    if (!t) return;
    window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => {
      api.grid(city, t).then((g) => setCells(g.cells)).catch(() => setCells([]));
      api.fires(city, t, 24).then(setFires).catch(() => setFires([]));
    }, 120);
    return () => window.clearTimeout(debounce.current);
  }, [city, index, timestamps]);

  const onPreset = (preset: ReplayPreset | null) => {
    if (!preset) return setIndex(Math.max(0, timestamps.length - 1));
    const target = timestamps.findIndex((t) => t >= new Date(preset.start).toISOString());
    if (target >= 0) setIndex(target);
  };

  const selectedAction = useMemo(
    () => actions.find((a) => a.hex === selected),
    [actions, selected]
  );

  if (!cityInfo) return <div className="p-6 text-slate-400">Loading city…</div>;

  return (
    <div className="grid h-full grid-cols-[1fr_380px]">
      <div className="relative">
        <MapView
          city={cityInfo}
          cells={cells}
          fires={fires}
          stations={stations}
          vulnerability={vulnerability}
          showFires={showFires}
          showVulnerability={showVuln}
          onSelectHex={setSelected}
        />
        <div className="absolute left-3 top-3 z-10 w-[420px] max-w-[70vw]">
          <TimeScrubber
            timestamps={timestamps}
            presets={presets}
            index={index}
            onIndex={setIndex}
            onPreset={onPreset}
          />
        </div>
        <div className="absolute bottom-3 left-3 z-10 flex gap-2">
          <button
            onClick={() => setShowFires((s) => !s)}
            className={`rounded-xl border px-3.5 py-1.5 text-xs font-medium shadow-lg shadow-slate-900/5 backdrop-blur-md transition ${
              showFires
                ? "border-orange-200 bg-orange-50/90 text-orange-700"
                : "border-slate-200/80 bg-white/85 text-slate-500 hover:text-slate-800"
            }`}
          >
            🔥 Fires
          </button>
          <button
            onClick={() => setShowVuln((s) => !s)}
            className={`rounded-xl border px-3.5 py-1.5 text-xs font-medium shadow-lg shadow-slate-900/5 backdrop-blur-md transition ${
              showVuln
                ? "border-violet-200 bg-violet-50/90 text-violet-700"
                : "border-slate-200/80 bg-white/85 text-slate-500 hover:text-slate-800"
            }`}
          >
            🏥 Vulnerability
          </button>
        </div>
        <Legend showVuln={showVuln} />
      </div>
      {selected ? (
        <HexPanel city={city} hex={selected} action={selectedAction} onClose={() => setSelected(null)} />
      ) : (
        <div className="flex h-full items-center justify-center border-l border-slate-200 bg-white p-8 text-center text-sm leading-relaxed text-slate-400">
          Click a hex on the map to see its forecast, source attribution and advisory.
        </div>
      )}
    </div>
  );
}

function Legend({ showVuln }: { showVuln: boolean }) {
  const bands = [
    ["Good", "#16a34a"], ["Satisfactory", "#84cc16"], ["Moderate", "#eab308"],
    ["Poor", "#f97316"], ["Very Poor", "#dc2626"], ["Severe", "#7f1d1d"],
  ];
  return (
    <div className="absolute bottom-3 right-3 z-10 rounded-xl border border-slate-200/80 bg-white/85 p-2.5 text-xs shadow-lg shadow-slate-900/5 backdrop-blur-md">
      {bands.map(([label, color]) => (
        <div key={label} className="flex items-center gap-2 py-px font-medium text-slate-600">
          <span className="inline-block h-3 w-3 rounded" style={{ backgroundColor: color }} />
          {label}
        </div>
      ))}
      {showVuln && (
        <div className="mt-1.5 border-t border-slate-200 pt-1.5">
          <div className="flex items-center gap-2 py-px font-medium text-slate-600">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: "#8b5cf6" }} />
            Schools
          </div>
          <div className="flex items-center gap-2 py-px font-medium text-slate-600">
            <span className="inline-block h-3 w-3 rounded-full ring-1 ring-white" style={{ backgroundColor: "#e11d48" }} />
            Hospitals
          </div>
        </div>
      )}
    </div>
  );
}
