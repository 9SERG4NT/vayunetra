import type {
  ActionsResponse, Advisory, AttributionResponse, CityInfo, CityScenario, DecideHex,
  DispatchPlan, FireDot, ForecastResponse, GrapStatus, GridResponse, Intervention,
  Metrics, Station, Timeline, Vulnerability,
} from "./types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
  vulnerability: (city: string) => get<Vulnerability>(`/vulnerability/${city}`),
  actions: (city: string) => get<ActionsResponse>(`/actions/${city}`),
  advisory: (city: string, hex: string, lang: string) =>
    get<Advisory>(`/advisory/${city}/${hex}?lang=${lang}`),
  metrics: (city: string) => get<Metrics>(`/metrics/${city}`),
  grap: (city: string) => get<GrapStatus>(`/grap/${city}`),
  evidenceUrl: (city: string, id: string, format: "html" | "pdf" = "html") =>
    `${BASE}/actions/${city}/${id}/evidence?format=${format}`,

  // --- Decision Layer ---
  interventions: (city: string) => get<Intervention[]>(`/interventions/${city}`),
  decideHex: (city: string, hex: string) => get<DecideHex>(`/decide/${city}/${hex}`),
  decideCity: (city: string) => get<{ city: string; scenarios: CityScenario[] }>(`/decide/${city}`),
  dispatch: (city: string, inspectors: number, shiftHours: number) =>
    post<DispatchPlan>(`/dispatch/${city}?inspectors=${inspectors}&shift_hours=${shiftHours}`, {}),
  createOrder: (city: string, hexId: string, interventionId: string) =>
    post<{ url: string; generation_ms: number }>(`/actions/${city}/order`, {
      hex_id: hexId,
      intervention_id: interventionId,
    }),
  orderUrl: (city: string, hex: string, intervention: string) =>
    `${BASE}/order/${city}?hex=${hex}&intervention=${intervention}`,
};
