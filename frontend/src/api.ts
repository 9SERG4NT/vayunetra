import type {
  ActionsResponse, Advisory, AttributionResponse, CityInfo, FireDot,
  ForecastResponse, GrapStatus, GridResponse, Metrics, Station, Timeline,
} from "./types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  cities: () => get<CityInfo[]>("/cities"),
  timeline: (city: string) => get<Timeline>(`/timeline/${city}`),
  grid: (city: string, t?: string) =>
    get<GridResponse>(`/grid/${city}${t ? `?t=${encodeURIComponent(t)}` : ""}`),
  forecast: (city: string, hex: string) => get<ForecastResponse>(`/forecast/${city}/${hex}`),
  attribution: (city: string, hex: string, t?: string) =>
    get<AttributionResponse>(`/attribution/${city}/${hex}${t ? `?t=${encodeURIComponent(t)}` : ""}`),
  fires: (city: string, t?: string, windowH = 24) =>
    get<FireDot[]>(`/fires/${city}?window_h=${windowH}${t ? `&t=${encodeURIComponent(t)}` : ""}`),
  stations: (city: string) => get<Station[]>(`/stations/${city}`),
  actions: (city: string) => get<ActionsResponse>(`/actions/${city}`),
  advisory: (city: string, hex: string, lang: string) =>
    get<Advisory>(`/advisory/${city}/${hex}?lang=${lang}`),
  metrics: (city: string) => get<Metrics>(`/metrics/${city}`),
  grap: (city: string) => get<GrapStatus>(`/grap/${city}`),
  evidenceUrl: (city: string, id: string, format: "html" | "pdf" = "html") =>
    `${BASE}/actions/${city}/${id}/evidence?format=${format}`,
};
