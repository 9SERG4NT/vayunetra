import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { BASEMAP_STYLE, aqiRgba } from "../theme";
import type { DispatchRoute, GridCell } from "../types";

export const INSPECTOR_COLORS: [number, number, number][] = [
  [37, 99, 235], [220, 38, 38], [22, 163, 74], [217, 119, 6], [124, 58, 237],
  [8, 145, 178], [190, 24, 93], [101, 163, 13], [2, 132, 199], [180, 83, 9],
];

interface Props {
  bbox: [number, number, number, number];
  cells: GridCell[];
  plan: DispatchRoute[];
  depot: { lat: number; lng: number } | null;
}

export default function DispatchMap({ bbox, cells, plan, depot }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);

  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: BASEMAP_STYLE,
      center: [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2],
      zoom: 9.2,
      attributionControl: { compact: true },
    });
    const overlay = new MapboxOverlay({ interleaved: true, layers: [] });
    map.addControl(overlay);
    mapRef.current = map;
    overlayRef.current = overlay;
    return () => {
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!overlayRef.current) return;
    const stops = plan.flatMap((r) =>
      r.stops.map((s) => ({ ...s, color: INSPECTOR_COLORS[(r.inspector_id - 1) % INSPECTOR_COLORS.length] }))
    );
    const layers = [
      new H3HexagonLayer<GridCell>({
        id: "ctx-hexes",
        data: cells,
        getHexagon: (d) => d.hex_id,
        getFillColor: (d) => aqiRgba(d.aqi, 55),
        stroked: false,
        filled: true,
        pickable: false,
      }),
      new PathLayer<DispatchRoute>({
        id: "routes",
        data: plan.filter((r) => r.stops.length > 0),
        getPath: (r) => [
          ...(depot ? [[depot.lng, depot.lat] as [number, number]] : []),
          ...r.stops.map((s) => [s.lng, s.lat] as [number, number]),
        ],
        getColor: (r) => INSPECTOR_COLORS[(r.inspector_id - 1) % INSPECTOR_COLORS.length],
        getWidth: 3,
        widthUnits: "pixels",
        capRounded: true,
        jointRounded: true,
      }),
      new ScatterplotLayer<(typeof stops)[number]>({
        id: "stops",
        data: stops,
        getPosition: (d) => [d.lng, d.lat],
        getFillColor: (d) => d.color,
        getLineColor: [255, 255, 255],
        lineWidthMinPixels: 1.5,
        stroked: true,
        getRadius: 6,
        radiusUnits: "pixels",
        pickable: true,
      }),
      new ScatterplotLayer({
        id: "depot",
        data: depot ? [depot] : [],
        getPosition: (d: { lat: number; lng: number }) => [d.lng, d.lat],
        getFillColor: [15, 23, 42, 255],
        getLineColor: [255, 255, 255],
        lineWidthMinPixels: 2,
        stroked: true,
        getRadius: 8,
        radiusUnits: "pixels",
      }),
    ];
    overlayRef.current.setProps({ layers });
  }, [cells, plan, depot]);

  return <div ref={container} className="h-full w-full" />;
}
