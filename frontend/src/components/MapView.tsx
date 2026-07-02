import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import { ScatterplotLayer } from "@deck.gl/layers";
import { BASEMAP_STYLE, aqiRgba } from "../theme";
import type { CityInfo, FireDot, GridCell, Station, Vulnerability, VulnPoint } from "../types";

interface Props {
  city: CityInfo;
  cells: GridCell[];
  fires: FireDot[];
  stations: Station[];
  vulnerability: Vulnerability | null;
  showFires: boolean;
  showVulnerability: boolean;
  onSelectHex: (hex: string) => void;
}

function bboxCenter(bbox: [number, number, number, number]): [number, number] {
  return [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2];
}

export default function MapView({
  city, cells, fires, stations, vulnerability, showFires, showVulnerability, onSelectHex,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);

  // Initialize the map once.
  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: BASEMAP_STYLE,
      center: bboxCenter(city.bbox),
      zoom: 9.4,
      attributionControl: { compact: true },
    });
    const overlay = new MapboxOverlay({ interleaved: true, layers: [] });
    map.addControl(overlay);
    map.addControl(new maplibregl.NavigationControl(), "top-left");
    mapRef.current = map;
    overlayRef.current = overlay;
    return () => {
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Recenter when the city changes.
  useEffect(() => {
    mapRef.current?.easeTo({ center: bboxCenter(city.bbox), zoom: 9.4, duration: 600 });
  }, [city.id, city.bbox]);

  // Update deck.gl layers when data changes.
  useEffect(() => {
    if (!overlayRef.current) return;
    const layers = [
      new H3HexagonLayer<GridCell>({
        id: "aqi-hexes",
        data: cells,
        getHexagon: (d) => d.hex_id,
        getFillColor: (d) => aqiRgba(d.aqi, d.low_coverage ? 70 : 150),
        getLineColor: [15, 23, 42, 40],
        lineWidthMinPixels: 0.5,
        extruded: false,
        stroked: true,
        filled: true,
        pickable: true,
        onClick: (info) => info.object && onSelectHex((info.object as GridCell).hex_id),
        updateTriggers: { getFillColor: cells },
      }),
      new ScatterplotLayer<Station>({
        id: "stations",
        data: stations,
        getPosition: (d) => [d.lng, d.lat],
        getFillColor: [14, 165, 233, 220],
        getRadius: 4,
        radiusUnits: "pixels",
        pickable: false,
      }),
      new ScatterplotLayer<FireDot>({
        id: "fires",
        data: showFires ? fires : [],
        getPosition: (d) => [d.lng, d.lat],
        getFillColor: [249, 115, 22, 180],
        getRadius: (d) => Math.max(2, Math.min(14, d.frp)),
        radiusUnits: "pixels",
        pickable: false,
      }),
      new ScatterplotLayer<VulnPoint>({
        id: "vuln-schools",
        data: showVulnerability ? vulnerability?.schools ?? [] : [],
        getPosition: (d) => [d.lng, d.lat],
        getFillColor: [139, 92, 246, 190], // violet — schools
        getRadius: 2.5,
        radiusUnits: "pixels",
        pickable: false,
      }),
      new ScatterplotLayer<VulnPoint>({
        id: "vuln-hospitals",
        data: showVulnerability ? vulnerability?.hospitals ?? [] : [],
        getPosition: (d) => [d.lng, d.lat],
        getFillColor: [225, 29, 72, 210], // rose — hospitals
        getLineColor: [255, 255, 255, 220],
        lineWidthMinPixels: 1,
        stroked: true,
        getRadius: 4,
        radiusUnits: "pixels",
        pickable: false,
      }),
    ];
    overlayRef.current.setProps({ layers });
  }, [cells, fires, stations, vulnerability, showFires, showVulnerability, onSelectHex]);

  return <div ref={container} className="h-full w-full" />;
}
