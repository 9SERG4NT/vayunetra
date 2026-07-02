import type { CityInfo } from "../types";

interface Props {
  cities: CityInfo[];
  active: string;
  onChange: (city: string) => void;
}

export default function CityToggle({ cities, active, onChange }: Props) {
  return (
    <div className="inline-flex rounded-xl border border-slate-200 bg-slate-100/70 p-1">
      {cities.map((c) => (
        <button
          key={c.id}
          onClick={() => onChange(c.id)}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
            active === c.id
              ? "bg-white text-sky-700 shadow-sm ring-1 ring-slate-200"
              : "text-slate-500 hover:text-slate-800"
          }`}
        >
          {c.name}
        </button>
      ))}
    </div>
  );
}
