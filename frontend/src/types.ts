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
  department?: string | null;
  legal_basis?: string | null;
  intervention_id?: string | null;
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

// --- Decision Layer ---
export interface Range {
  lo: number;
  mid: number;
  hi: number;
}

export interface Intervention {
  id: string;
  label: string;
  targets: string;
  efficacy: [number, number, number];
  time_to_impact_h: [number, number];
  cost_tier: string;
  department: string;
  legal_basis: string;
  basis: string;
}

export interface Scenario {
  city: string;
  hex_id: string;
  intervention_id: string;
  label: string;
  target_source: string;
  method: string;
  aqi_now: number;
  delta_aqi: Range;
  aqi_after: Range;
  confidence: string;
  confidence_downgraded: boolean;
  department: string;
  legal_basis: string;
  time_to_impact_h: [number, number];
  cost_tier: string;
  assumptions: string[];
  exposure: {
    schools_affected: number;
    hospitals_affected: number;
    person_hours_avoided: Range;
    person_hours_basis: string;
  };
}

export interface WhyResponse {
  city: string;
  hex_id: string;
  bullets: string[];
  conclusion: string;
  polished: boolean;
}

export interface DecideHex {
  city: string;
  hex_id: string;
  why: WhyResponse;
  interventions: Scenario[];
}

export interface CityScenario {
  city: string;
  intervention_id: string;
  label: string;
  hexes_affected: number;
  delta_aqi_weighted_mean: number;
  person_hours_avoided_total: number;
  top_hexes: { hex_id: string; locality: string; delta_aqi_mid: number; person_hours_mid: number }[];
}

export interface DispatchStop {
  hex: string;
  locality: string;
  intervention: string;
  eta_ist: string;
  impact: number;
  aqi: number;
  lat: number;
  lng: number;
}

export interface DispatchRoute {
  inspector_id: number;
  stops: DispatchStop[];
  route_km: number;
  utilisation: number;
}

export interface DispatchPlan {
  city: string;
  inspectors: number;
  shift_hours: number;
  depot: { lat: number; lng: number };
  plan: DispatchRoute[];
  totals: { impact_covered: number; sites_covered: number; travel_km: number };
  baseline_comparison: {
    naive_impact_covered: number;
    naive_sites: number;
    naive_travel_km: number;
    impact_gain_pct: number;
    travel_km_saved: number;
  };
}
