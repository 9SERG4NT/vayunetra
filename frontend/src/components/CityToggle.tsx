import type { CityInfo } from "../types";

interface Props {
  cities: CityInfo[];
  active: string;
  onChange: (city: string) => void;
}

export default function CityToggle({ cities, active, onChange }: Props) {
  return (
    <div className="inline-flex rounded-lg border border-slate-800 bg-slate-900 p-1">
      {cities.map((c) => (
        <button
          key={c.id}
          onClick={() => onChange(c.id)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
            active === c.id ? "bg-sky-600 text-white" : "text-slate-300 hover:text-white"
          }`}
        >
          {c.name}
        </button>
      ))}
    </div>
  );
}
