export interface CityInfo {
  id: string;
  name: string;
  bbox: [number, number, number, number];
  grap: boolean;
  replay_presets: ReplayPreset[];
}

export interface ReplayPreset {
  id: string;
  label: string;
  start: string;
  end: string;
}

export interface Timeline {
  city: string;
  timestamps: string[];
  presets: ReplayPreset[];
}

export interface GridCell {
  hex_id: string;
  pm25: number | null;
  aqi: number | null;
  category: string | null;
  low_coverage: boolean;
}

export interface GridResponse {
  city: string;
  t: string;
  cells: GridCell[];
}

export interface HistoryPoint {
  t: string;
  pm25: number | null;
  aqi: number | null;
}

export interface ForecastPoint {
  h: number;
  t: string;
  pm25: number | null;
  pi_low: number | null;
  pi_high: number | null;
  aqi: number | null;
}

export interface ForecastResponse {
  city: string;
  hex_id: string;
  history_72h: HistoryPoint[];
  forecast: ForecastPoint[];
}

export interface AttributionResponse {
  city: string;
  hex_id: string;
  t: string;
  shares: Record<string, number>;
  met_modifier: number;
  confidence: string;
  evidence: Record<string, unknown>;
}

export interface FireDot {
  lat: number;
  lng: number;
  frp: number;
  age_h: number;
}

export interface ActionItem {
  id: string;
  hex: string;
  locality: string;
  source: string;
  share: number;
  confidence: string;
  aqi: number;
  score: number;
  recommended_action: string;
  grap_context?: string | null;
  created_ts: string;
}

export interface ActionsResponse {
  city: string;
  created_ts?: string | null;
  actions: ActionItem[];
}

export interface Advisory {
  lang: string;
  text: string;
  generated_by: string;
}

export interface GrapStatus {
  city: string;
  grap?: boolean;
  current_stage?: number;
  predicted_stage_48h?: number;
  headline_stage?: number;
  label?: string;
  actions?: string[];
}

export interface Metrics {
  city?: string;
  generated_utc?: string;
  horizons?: Record<string, Record<string, { rmse: number | null; mae: number | null; n: number } | number | null>>;
  coverage?: Record<string, unknown>;
}

export interface Station {
  station_id: number;
  lat: number;
  lng: number;
}

export interface VulnPoint {
  lat: number;
  lng: number;
}

export interface Vulnerability {
  schools: VulnPoint[];
  hospitals: VulnPoint[];
}
