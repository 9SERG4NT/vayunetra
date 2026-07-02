import { useEffect, useMemo, useRef, useState } from "react";
import MapView from "../components/MapView";
import TimeScrubber from "../components/TimeScrubber";
import HexPanel from "../components/HexPanel";
import { api } from "../api";
import type {
  ActionItem, CityInfo, FireDot, GridCell, ReplayPreset, Station,
} from "../types";

export default function CommandPage({ city, cityInfo }: { city: string; cityInfo?: CityInfo }) {
  const [timestamps, setTimestamps] = useState<string[]>([]);
  const [presets, setPresets] = useState<ReplayPreset[]>([]);
  const [index, setIndex] = useState(0);
  const [cells, setCells] = useState<GridCell[]>([]);
  const [fires, setFires] = useState<FireDot[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [showFires, setShowFires] = useState(true);
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
          showFires={showFires}
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
        <button
          onClick={() => setShowFires((s) => !s)}
          className="absolute bottom-3 left-3 z-10 rounded-lg border border-slate-700 bg-slate-900/80 px-3 py-1.5 text-xs text-slate-200"
        >
          {showFires ? "Hide fires" : "Show fires"}
        </button>
        <Legend />
      </div>
      {selected ? (
        <HexPanel city={city} hex={selected} action={selectedAction} onClose={() => setSelected(null)} />
      ) : (
        <div className="flex h-full items-center justify-center border-l border-slate-800 bg-slate-950 p-6 text-center text-sm text-slate-500">
          Click a hex on the map to see its forecast, source attribution and advisory.
        </div>
      )}
    </div>
  );
}

function Legend() {
  const bands = [
    ["Good", "#16a34a"], ["Satisfactory", "#84cc16"], ["Moderate", "#eab308"],
    ["Poor", "#f97316"], ["Very Poor", "#dc2626"], ["Severe", "#7f1d1d"],
  ];
  return (
    <div className="absolute bottom-3 right-3 z-10 rounded-lg border border-slate-700 bg-slate-900/80 p-2 text-xs">
      {bands.map(([label, color]) => (
        <div key={label} className="flex items-center gap-2 text-slate-200">
          <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: color }} />
          {label}
        </div>
      ))}
    </div>
  );
}
