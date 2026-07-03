# Decision Layer — method note

The Decision Layer turns VayuNetra's intelligence + evidence into **decision support**:
for any hotspot it answers *what to do, who does it, how much it helps, at what
confidence and cost*. This note states exactly how those numbers are produced and,
just as importantly, what they are **not**.

## The one thing to remember
> These are **planning estimates** — a correlational forecasting model combined with
> **editable literature priors**. They are designed for **prioritisation**, not as a
> causal guarantee. Every predicted improvement is a **range**, every confidence is a
> **tier inherited from attribution**, and every efficacy/cost/time value is visible
> and editable in `config/interventions.yaml`.

## Two estimation methods (triangulated where possible)
For a hex `h`, intervention `i` targeting source `k` with efficacy prior `e = [lo, mid, hi]`:

- **Method A — attribution arithmetic** (always available):
  `ΔPM = PM_now × source_share_k × e`. The source share and its confidence tier come
  from the attribution engine; the efficacy comes from the priors file, never the model.
- **Method M — model counterfactual** (only where the mechanism is a real model feature,
  i.e. biomass via `fire_load_upwind_24` / `fire_count_radius_24`): re-run the trained
  24 h forecaster with those features scaled by `(1 − e_mid)`, IDW the per-station
  prediction delta to the hex.

Where both exist, the reported range spans them: `ΔPM_range = [min(A_lo, M), max(A_hi, M)]`,
`mid = mean(A_mid, M)`. If the two methods disagree by more than 50 % of `A_mid`, the
confidence tier is **downgraded one step** and the reason is listed in the scenario's
`assumptions[]`.

## Confidence is inherited, not invented
Scenario confidence = the hex's attribution confidence (`high` / `medium` / `low`),
possibly downgraded by the disagreement rule above. There is **no invented percentage**
anywhere (grep the UI: confidence is always a tier word).

## AQI, exposure, and the forward view
- `ΔAQI = AQI_now − AQI_after`, floored at 0, where AQI is the max CPCB sub-index of the
  reduced PM2.5 and the unchanged PM10 (so a PM10-dominated hex honestly shows little
  benefit from a PM2.5-source intervention).
- **Exposure**: schools/hospitals within the hex ∪ its 6 neighbours; `person_hours_avoided`
  is a **labelled proxy** (`schools_n × 500` persons × hours the forecast crosses back
  below AQI 200). If `data/geo/{city}/population.tif` is added, it is used instead.
- Forward reduction applies the same fractional cut to the 24 h / 48 h forecast, under
  the stated assumption that source shares are stable over the horizon.

## Dispatch optimiser
A deterministic greedy nearest-neighbour insertion assigns inspectors to the highest
`impact / insertion-time` hotspot+intervention candidates under a shift-hours budget
(travel via haversine × 1.3 circuity at 25 km/h + per-intervention inspection time).
It is compared against a geography-blind naive plan (top candidates by AQI, round-robin).
The headline stat — "+X % impact, −Y km" — is that comparison. It is a prioritisation
aid, not a routing guarantee, and uses no external solver.

## The priors file is the argument, not a liability
`config/interventions.yaml` holds every efficacy/cost/time/department/legal-basis value
with a `basis:` note. The values are conservative seed priors meant to be reviewed and
annotated by domain experts before deployment. Editing one line changes every downstream
estimate — that transparency is the design, and the deck should present it as such.

## Language policy (enforced)
UI and generated documents say "planning estimate" / "model-implied estimate", never
"will reduce", "guaranteed", or "causal effect". The order document carries the same
disclaimer inline.
