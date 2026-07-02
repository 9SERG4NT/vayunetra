// AQI color scale (color-blind safe; always pair color with the category text).
export interface AqiBand {
  lo: number;
  hi: number;
  label: string;
  color: string;
  rgb: [number, number, number];
}

export const AQI_BANDS: AqiBand[] = [
  { lo: 0, hi: 50, label: "Good", color: "#16a34a", rgb: [22, 163, 74] },
  { lo: 51, hi: 100, label: "Satisfactory", color: "#84cc16", rgb: [132, 204, 22] },
  { lo: 101, hi: 200, label: "Moderate", color: "#eab308", rgb: [234, 179, 8] },
  { lo: 201, hi: 300, label: "Poor", color: "#f97316", rgb: [249, 115, 22] },
  { lo: 301, hi: 400, label: "Very Poor", color: "#dc2626", rgb: [220, 38, 38] },
  { lo: 401, hi: 500, label: "Severe", color: "#7f1d1d", rgb: [127, 29, 29] },
];

export function aqiBand(aqi: number | null | undefined): AqiBand {
  if (aqi == null || Number.isNaN(aqi)) return AQI_BANDS[0];
  for (const b of AQI_BANDS) if (aqi <= b.hi) return b;
  return AQI_BANDS[AQI_BANDS.length - 1];
}

export function aqiColor(aqi: number | null | undefined): string {
  return aqiBand(aqi).color;
}

export function aqiRgba(aqi: number | null | undefined, alpha = 140): [number, number, number, number] {
  const b = aqiBand(aqi);
  return [b.rgb[0], b.rgb[1], b.rgb[2], alpha];
}

export const CONFIDENCE_COLOR: Record<string, string> = {
  high: "#16a34a",
  medium: "#eab308",
  low: "#f97316",
};

export const SOURCE_COLOR: Record<string, string> = {
  biomass: "#f97316",
  traffic: "#64748b",
  industry: "#7c3aed",
  construction_dust: "#a16207",
  background: "#94a3b8",
};

export const CARTO_DARK = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
