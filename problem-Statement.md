# problem-Statement.md
## PS 5 — AI-Powered Urban Air Quality Intelligence for Smart City Intervention
### ET AI Hackathon 2.0 · Detailed decode of the official problem statement

Place this file in the repo root next to `BUILD_SPEC.md`. It exists so that anyone (teammate, judge, or Claude Code) can understand *exactly* what the organisers are asking for, what each sentence of the PDF implies technically, and how VayuNetra answers it. Structure mirrors the PDF section by section: first a faithful paraphrase of what the PDF says, then what it actually means, then the implication for our build.

**Theme (as given):** Smart Cities · Environmental Intelligence · Geospatial Analytics · Public Health

---

## 1. PROBLEM CONTEXT — what the PDF establishes, line by line

The PDF's problem context makes six factual claims and one diagnosis. Each one is there for a reason — judges wrote them as hints about what they want to see addressed.

**Claim 1 — "This is a national urban crisis, not a Delhi problem."**
The PDF cites Delhi averaging AQI 218 in 2024–25 (over 200 days classified Poor or worse), but immediately widens the frame: Mumbai had dangerous AQI on 60+ days in 2024, Kolkata averaged above 150 through much of winter, and even Bengaluru and Chennai — historically "clean" — are measurably deteriorating under vehicle density and construction growth. CPCB's 2024 national data puts 24 of India's 50 most polluted cities in the Tier-1/Tier-2 bracket.
*Why it's there:* the organisers are signalling that a Delhi-only solution is incomplete. They want **portability across cities** demonstrated, not assumed.
*Our answer:* two live cities (Delhi + Pune/PCMC) with city onboarding reduced to a YAML config block — the scalability claim is shown, not slided.

**Claim 2 — the health stake.**
The PDF cites the Lancet Planetary Health estimate of 1.67 million premature deaths annually in India from air pollution, falling disproportionately on urban populations.
*Why it's there:* impact framing. Business Impact is 25% of the score; the human cost is the opening of every winning pitch.
*Our answer:* vulnerability-aware exposure weighting (schools/hospitals per hex) and the citizen advisory layer.

**Claim 3 — the infrastructure already exists.**
India has deployed 900+ Continuous Ambient Air Quality Monitoring Stations (CAAQMS) under the National Clean Air Programme (NCAP).
*Why it's there:* they are telling you **not to propose new sensors**. The measurement layer is solved. Any team pitching hardware has misread the PS.
*Our answer:* we build purely on existing public data (CPCB stations via OpenAQ, NASA FIRMS satellites, ERA5/CAMS weather) — zero new hardware.

**Claim 4 — the damning audit.**
A 2024 CAG audit found only 31% of cities with monitoring data had any actionable multi-agency response protocol linked to those readings.
*Why it's there:* this is the thesis of the whole PS, stated as evidence: **"The data exists. The intelligence layer to act on it does not."** That sentence is the problem statement.
*Our answer:* VayuNetra *is* that intelligence layer — the entire product is the signal→attribution→forecast→enforcement-action loop.

**Claim 5–7 — the three missing capabilities.**
The PDF then names exactly what "more than dashboards" means. City administrations need:
1. **Geospatial attribution** — *which sources are responsible at this location, right now*;
2. **Predictive forecasting** — *what will AQI be in 24 hours at ward level*;
3. **Enforcement intelligence** — *where to deploy inspectors for maximum impact*.
And it states flatly that this combination does not exist today.
*Why it's there:* this is the grading key hiding in the context section. These three capabilities reappear verbatim as the first three bullets of the Evaluation Focus. A solution that nails these three is aligned with the judges' rubric by construction.
*Our answer:* they map 1:1 to VayuNetra's attribution engine (§8.3 of BUILD_SPEC), forecast models (§8.2), and enforcement ranker + evidence packs (§9).

---

## 2. CHALLENGE STATEMENT — decoded

**Paraphrase of the ask:** build an AI platform that *fuses* five data families — monitoring stations, satellite imagery, mobility feeds, meteorological forecasts, and geospatial land-use layers — to move cities from *reactive monitoring* to *proactive, evidence-based intervention*, so administrators can reduce pollution **at source** rather than just measure it.

Four words in that sentence carry the entire technical burden:

| Word | What it demands | How VayuNetra satisfies it |
|---|---|---|
| **fuses** | Multi-source integration is mandatory, not optional. A single-API app fails the brief. | 5 source families: CAAQMS obs (OpenAQ/CPCB), satellite fire detections (FIRMS/VIIRS), meteorology (ERA5 + Open-Meteo forecast + CAMS), land use (OSM industrial/construction/roads), mobility proxy (road-class density × diurnal profile; TomTom optional) |
| **proactive** | Prediction with lead time, not display of the present. | 24/48/72-h forecasts with prediction intervals; GRAP stage predicted 48 h ahead |
| **evidence-based** | Every recommendation must carry defensible supporting material. | One-click evidence pack: map, trend, fire table, wind-sector lifts, confidence score, method appendix |
| **at source** | The system must say *who/what* is polluting, not just *how much*. | Hourly, per-hex source attribution across 5 source classes with a confidence rating |

The phrase "giving city administrators the tools" also fixes the **primary user**: the SPCB officer and municipal commissioner, not the citizen. The citizen layer is one module of five, not the product. Teams that build a consumer AQI app have answered a different question.

---

## 3. "WHAT YOU MAY BUILD" — the five modules, explained

The PDF closes this section with "These examples are illustrative only." Translation: **you are not expected to build all five; you are expected to build a coherent, deep subset.** Here is what each module actually requires and our scope decision:

**3.1 Geospatial Pollution Source Attribution Engine** — analyse spatial-temporal AQI patterns against land-use maps, traffic density, construction permits, industrial stacks, and satellite-detected thermal anomalies, attributing pollution by source category at ward/zone level **with statistical confidence scores**.
*Hard part:* true source apportionment needs chemical speciation data (receptor models like PMF/CMB) that doesn't exist in real time. *The PDF's own wording gives the out:* it asks for attribution "with statistical confidence scores" — an evidence-weighted statistical method, honestly confidence-labelled, meets the brief.
*Our scope:* **CORE.** Triangulated recipe — SHAP group decomposition of the forecast model (temporal drivers) + spatial ridge regression on land-use covariates (spatial drivers) + wind-sector lift statistics (directional cross-check) → 5 source shares + confidence badge. We explicitly label it "evidence-weighted attribution, not regulatory source apportionment."

**3.2 Hyperlocal Predictive AQI Forecasting Agent** — 24–72 h AQI forecasts at ~1 km grid resolution, integrating met forecasts, traffic prediction, seasonal emission calendars, and dispersion modelling.
*Hard part:* full atmospheric dispersion modelling (CTMs) is a PhD, not a hackathon. *The out:* the Evaluation Focus grades forecasts as **"RMSE versus persistence baseline"** — a statistical-learning forecast that beats persistence satisfies the rubric as written.
*Our scope:* **CORE.** Station-level LightGBM per horizon with met, calendar (festival windows = the "seasonal emission calendar"), and upwind-fire features; CAMS as both benchmark and optional blend; IDW to a ~1 km H3 res-8 grid; honest rolling-origin backtests.

**3.3 Enforcement Intelligence & Prioritisation Agent** — correlate hotspots with registered emission sources (industries, construction, waste burning, diesel fleets) and generate **prioritised, evidence-backed enforcement recommendations with supporting geospatial documentation**.
*Our scope:* **CORE — and our differentiator.** Ranked action queue (share × severity × persistence × exposure × actionability) and the auto-generated evidence pack with a draft notice and a PRANA-reporting stub. "Supporting geospatial documentation" is the phrase the evidence-pack PDF/HTML answers literally.

**3.4 Multi-City Comparative Intelligence Dashboard** — track trends, intervention effectiveness, and compliance across cities so administrators learn from each other.
*Our scope:* **LIGHT.** The Delhi⇄Pune toggle + per-city metrics page demonstrates the architecture; full intervention-effectiveness comparison is roadmap (we show one worked before/after example if time allows).

**3.5 Citizen Health Risk Advisory System** — ward-level health alerts, vulnerability mapping (hospitals, schools, outdoor workers, elderly) against forecast AQI, pushed via apps/displays/IVR **in regional languages** (the PDF names Kannada for Bengaluru, Tamil for Chennai — i.e., language must match the city).
*Our scope:* **LIGHT.** Advisory generator with EN/HI/MR live (Marathi matches our Pune demo city, per the PDF's own logic), 12-language template framework, WhatsApp-card + IVR-script preview. Deterministic templates with injected numbers; optional LLM polish.

**Scope summary:** deep on 3.1 + 3.2 + 3.3 (the three capabilities from the problem context), demonstrative on 3.4 + 3.5. That is a defensible reading of "illustrative only," and it should be said out loud in the pitch: *"We built the loop end-to-end for two modules-deep cities rather than five modules an inch deep."*

---

## 4. SUGGESTED TECHNOLOGIES — mapped to actual choices

| PDF suggestion | What it means | Our implementation |
|---|---|---|
| Geospatial Intelligence & Remote Sensing (Sentinel, MODIS) | Satellite evidence layers | NASA FIRMS (VIIRS + MODIS thermal anomalies) in v1; Sentinel-5P NO₂ via Earth Engine as stretch |
| Multi-Agent AI Systems | Modular autonomous components | Pipeline of specialised components (ingest → forecast → attribution → ranker → advisory); framed as an agentic pipeline in the deck — do not over-engineer an agent framework for its own sake |
| Real-time IoT sensor integration (CAAQMS) | Live station feeds | OpenAQ v3 (CPCB mirror) + optional data.gov.in live endpoint; `LIVE_MODE=1` hourly refresh |
| Atmospheric Dispersion Modelling | Physics of transport | Met-driven features (wind vectors, BLH, upwind sector geometry) — "dispersion-informed ML" honestly framed; full CTM is out of scope and we say so |
| Predictive Analytics | Forecasting | LightGBM + baselines + prediction intervals |
| LLMs for multi-language citizen communication | Regional-language advisories | Template-first generation (numbers never hallucinated) with optional Anthropic/NIM polish |

---

## 5. EXPECTED DELIVERABLES

The PDF requires exactly four artefacts — all four must exist at submission:
1. **Working Prototype** → the repo, runnable via `make setup && make pipeline && make demo`, offline-capable.
2. **Architecture Diagram** → `docs/architecture.md` (mermaid) exported to an image for the deck.
3. **Presentation Deck** → 10-slide outline in the planning doc (human task).
4. **Demo Video** → ≤3 min, scripted around the demo beats (human task).

---

## 6. EVALUATION FOCUS — the five bullets judges will actually probe

This is the most important section of the PDF. Each bullet, decoded into "what to show":

| # | PDF's evaluation bullet | What judges will ask | Our proof artefact |
|---|---|---|---|
| 1 | Source attribution accuracy **versus ground-truth emission inventories** | "How do you know your attribution is right?" | Event-study replays (festival window → biomass/activity share spikes, `docs/event_*.png`); cross-method agreement rate; comparison table of our average Delhi shares vs published source-apportionment studies (TERI/ARAI 2018, SAFAR inventory) as literature reference; the confidence badge itself is the honesty mechanism |
| 2 | AQI forecast accuracy at hyperlocal resolution (**RMSE versus persistence baseline**) | "Show me the number." | `docs/metrics.md`: RMSE/MAE + skill score at 24/48/72 h vs persistence, climatology, and raw CAMS — rendered inside the app on the Metrics page |
| 3 | Enforcement recommendation quality **rated by domain experts** | "Would an SPCB officer act on this?" | 5 sample evidence packs scored on a disclosed rubric (external reviewer if we can get one; structured self-rubric otherwise, stated transparently) |
| 4 | Citizen advisory **relevance and language coverage** | "Does it work in the city's language?" | Live EN/HI/MR advisories with correct injected numbers; 12-language template framework; Marathi demo on a Pune ward |
| 5 | Demonstrated **reduction in response time from signal to intervention** | "How much faster than today?" | Instrumented `generation_ms` on the evidence pack — "signal to court-ready evidence in under X seconds, versus the days-to-weeks manual status quo"; the demo's stopwatch moment |

Note the trap in bullet 1: "ground-truth emission inventories" for Indian cities are static, years-old studies. Nobody can validate hourly attribution against them directly. The winning move is to acknowledge that on stage and show the three-way triangulation instead — judges reward epistemic honesty over inflated claims.

---

## 7. JUDGING CRITERIA — how each weight is won

| Criterion | Weight | How VayuNetra scores it |
|---|---|---|
| Innovation | 25% | Hourly, confidence-scored source attribution + one-click court-ready evidence packs + GRAP-ahead prediction — no existing product (SAFAR, CPCB dashboards, Ambee, IQAir, Google AQ) closes the signal→enforcement loop |
| Business Impact | 25% | Directly tied to performance-linked NCAP/XV-FC funding (≈₹19,700 crore programme; non-performing cities receive zero) and to CPCB PRANA reporting obligations — the buyer, budget line, and wedge are all named |
| Technical Excellence | 20% | Honest backtests vs three baselines, prediction intervals, triangulated attribution with unit-tested math, reproducible one-command pipeline, no fabricated data anywhere |
| Scalability | 15% | New city = one YAML block; H3 grid needs no shapefiles; keyless/free-tier data stack; live Delhi⇄Pune toggle as on-stage proof |
| User Experience | 15% | Officer-first command view, one-click evidence, replay scrubber, colour-blind-safe AQI palette with text labels, regional-language advisories |

---

## 8. GLOSSARY (terms the PDF assumes you know)

- **AQI / NAQI** — India's National Air Quality Index (CPCB): worst pollutant sub-index wins; bands Good(0–50) → Severe(401–500). Official AQI uses 24-h averages; our hourly figure is a disclosed proxy.
- **CAAQMS** — Continuous Ambient Air Quality Monitoring Stations; the 900+ reference-grade government monitors.
- **CPCB / SPCB** — Central / State Pollution Control Boards (regulator = our enforcement user).
- **NCAP** — National Clean Air Programme (2019–): PM-reduction targets for 131 non-attainment/million-plus cities, with performance-linked funding.
- **CAG audit** — Comptroller & Auditor General; its 2024 finding (31% protocol coverage) is the PS's core evidence.
- **Ward / zone** — municipal sub-units; we approximate with ~1 km H3 hexes labelled by locality, avoiding fragile shapefile dependencies.
- **Source attribution vs apportionment** — apportionment = chemical receptor modelling (PMF/CMB) on speciated samples; attribution (our claim) = statistical, evidence-weighted estimation with confidence labels.
- **Persistence baseline** — the naive forecast "tomorrow = today"; the PDF's named benchmark.
- **Dispersion modelling** — physics simulation of pollutant transport (wind, boundary layer); we use its drivers as ML features rather than running a CTM.
- **GRAP** — Graded Response Action Plan (Delhi-NCR, CAQM): staged mandatory actions by AQI band (I: 201–300 … IV: >450).
- **PRANA** — CPCB's official NCAP reporting portal (why our project is *not* named that; we generate its paperwork instead).
- **FIRMS / VIIRS** — NASA's satellite fire-detection service / sensor; our stubble- and waste-burning evidence layer.
- **CAMS / ERA5** — Copernicus global air-quality forecast model / ECMWF weather reanalysis; our benchmark and met-history sources.

---

## 9. TRAPS THIS PS SETS (and how we avoid them)

1. **Building all five modules an inch deep** → we go deep on the three capabilities the problem context itself names, light on the rest, and say so.
2. **Shipping another dashboard** → the PDF explicitly says administrations "need more than dashboards"; our unit of output is an *action with evidence*, not a chart.
3. **Over-claiming attribution** → confidence badges + "evidence-weighted, not regulatory apportionment" disclaimer everywhere the number appears.
4. **Synthetic/demo data** → hard rule in BUILD_SPEC §1.2: every number traceable to real public data; gaps shown as gaps.
5. **Proposing sensors** → the PS already told us the monitors exist; we add intelligence, not hardware.
6. **Ignoring the named baseline** → RMSE vs persistence is printed inside the product, not buried in an appendix.
7. **Wrong language for the demo city** → the PDF's own examples pair language to city; hence Marathi for Pune.
