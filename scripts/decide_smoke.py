"""decide-smoke (DECISION_LAYER_SPEC §A4.4): 3 canned simulate calls + 1 dispatch."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(city: str = "delhi") -> int:
    from backend.actions.dispatch import dispatch
    from backend.actions.simulate import simulate, simulate_city

    actions = json.loads((Path("data/snapshots") / city / "actions.json").read_text(encoding="utf-8"))
    hexes = [a["hex"] for a in actions["actions"][:1]] or []
    print(f"=== decide-smoke: {city} ===")

    if hexes:
        for iid in ("construction_halt", "biomass_enforcement", "dust_suppression"):
            s = simulate(city, hexes[0], iid)
            print(f"  simulate {iid:22} method={s['method']:16} "
                  f"dAQI={s['delta_aqi']['lo']}–{s['delta_aqi']['hi']} (mid {s['delta_aqi']['mid']}) "
                  f"conf={s['confidence']}")
    c = simulate_city(city, "biomass_enforcement")
    print(f"  city biomass: {c['hexes_affected']} hexes, mean dAQI {c['delta_aqi_weighted_mean']}, "
          f"{c['person_hours_avoided_total']:,} person-hours (proxy)")
    d = dispatch(city, 4, 8)
    b = d["baseline_comparison"]
    print(f"  dispatch N=4: {d['totals']['sites_covered']} sites, "
          f"+{b['impact_gain_pct']}% impact vs naive, -{b['travel_km_saved']} km travel")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "delhi"))
