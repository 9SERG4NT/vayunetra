import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import CityToggle from "./components/CityToggle";
import GrapChip from "./components/GrapChip";
import LiveStatus from "./components/LiveStatus";
import CommandPage from "./pages/CommandPage";
import ActionsPage from "./pages/ActionsPage";
import DecidePage from "./pages/DecidePage";
import MetricsPage from "./pages/MetricsPage";
import { api } from "./api";
import type { CityInfo, GrapStatus } from "./types";

export default function App() {
  const [cities, setCities] = useState<CityInfo[]>([]);
  const [city, setCity] = useState<string>("delhi");
  const [grap, setGrap] = useState<GrapStatus | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

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
    `px-3 py-1.5 text-sm font-medium rounded-lg transition ${
      isActive ? "bg-sky-50 text-sky-700" : "text-slate-500 hover:text-slate-900 hover:bg-slate-50"
    }`;

  return (
    <div className="flex h-full flex-col bg-slate-50">
      <header className="flex items-center gap-5 border-b border-slate-200 bg-white px-5 py-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
        <a href="/" className="flex items-baseline gap-2.5" title="Back to landing page">
          <span className="text-lg font-bold tracking-tight text-sky-600">VayuNetra</span>
          <span className="hidden text-xs font-medium text-slate-400 sm:inline">
            Urban Air Quality Intelligence
          </span>
        </a>
        <nav className="flex gap-1">
          <NavLink to="/app" end className={navClass}>Command</NavLink>
          <NavLink to="/app/actions" className={navClass}>Actions</NavLink>
          <NavLink to="/app/decide" className={navClass}>Decide</NavLink>
          <NavLink to="/app/metrics" className={navClass}>Metrics</NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <LiveStatus city={city} onRefreshed={() => { setRefreshKey((k) => k + 1); api.grap(city).then(setGrap).catch(() => setGrap(null)); }} />
          {cityInfo?.grap && <GrapChip grap={grap} />}
          <CityToggle cities={cities} active={city} onChange={setCity} />
        </div>
      </header>
      <main className="min-h-0 flex-1">
        <Routes>
          <Route index element={<CommandPage key={refreshKey} city={city} cityInfo={cityInfo} />} />
          <Route path="actions" element={<ActionsPage key={refreshKey} city={city} />} />
          <Route path="decide" element={<DecidePage key={refreshKey} city={city} cityInfo={cityInfo} />} />
          <Route path="metrics" element={<MetricsPage key={refreshKey} city={city} />} />
        </Routes>
      </main>
    </div>
  );
}
