import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import CityToggle from "./components/CityToggle";
import GrapChip from "./components/GrapChip";
import CommandPage from "./pages/CommandPage";
import ActionsPage from "./pages/ActionsPage";
import MetricsPage from "./pages/MetricsPage";
import { api } from "./api";
import type { CityInfo, GrapStatus } from "./types";

export default function App() {
  const [cities, setCities] = useState<CityInfo[]>([]);
  const [city, setCity] = useState<string>("delhi");
  const [grap, setGrap] = useState<GrapStatus | null>(null);

  useEffect(() => {
    api.cities().then((cs) => {
      setCities(cs);
      if (cs.length && !cs.find((c) => c.id === city)) setCity(cs[0].id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    api.grap(city).then(setGrap).catch(() => setGrap(null));
  }, [city]);

  const cityInfo = cities.find((c) => c.id === city);

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-1.5 text-sm font-medium rounded-md ${isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:text-white"}`;

  return (
    <div className="flex h-full flex-col bg-slate-950">
      <header className="flex items-center gap-4 border-b border-slate-800 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-sky-400">VayuNetra</span>
          <span className="hidden text-xs text-slate-500 sm:inline">Urban Air Quality Intelligence</span>
        </div>
        <nav className="flex gap-1">
          <NavLink to="/" end className={navClass}>Command</NavLink>
          <NavLink to="/actions" className={navClass}>Actions</NavLink>
          <NavLink to="/metrics" className={navClass}>Metrics</NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {cityInfo?.grap && <GrapChip grap={grap} />}
          <CityToggle cities={cities} active={city} onChange={setCity} />
        </div>
      </header>
      <main className="min-h-0 flex-1">
        <Routes>
          <Route path="/" element={<CommandPage city={city} cityInfo={cityInfo} />} />
          <Route path="/actions" element={<ActionsPage city={city} />} />
          <Route path="/metrics" element={<MetricsPage city={city} />} />
        </Routes>
      </main>
    </div>
  );
}
