"""Citizen advisory generation (BUILD_SPEC §10).

Deterministic Jinja2 templates with injected fields only; numbers are never
LLM-generated. Localized category/source/action phrases live here (not the LLM).
Optional polish via advisory/llm.polish when a provider is configured.
"""
from __future__ import annotations

import logging

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend.advisory.llm import is_enabled, polish
from backend.config import IST_OFFSET_MINUTES, geo_city_dir, snap_dir
from backend.models.attribution import SOURCES

log = logging.getLogger("vayunetra.advisory.generate")
_TEMPLATES = Environment(
    loader=FileSystemLoader(str(__import__("pathlib").Path(__file__).parent / "templates")),
    autoescape=select_autoescape(enabled_extensions=()),
)
IST = pd.Timedelta(minutes=IST_OFFSET_MINUTES)

CATEGORY = {
    "en": {"Good": "Good", "Satisfactory": "Satisfactory", "Moderate": "Moderate",
           "Poor": "Poor", "Very Poor": "Very Poor", "Severe": "Severe", "Unknown": "Unknown"},
    "hi": {"Good": "अच्छा", "Satisfactory": "संतोषजनक", "Moderate": "मध्यम",
           "Poor": "खराब", "Very Poor": "बहुत खराब", "Severe": "गंभीर", "Unknown": "अज्ञात"},
    "mr": {"Good": "चांगला", "Satisfactory": "समाधानकारक", "Moderate": "मध्यम",
           "Poor": "वाईट", "Very Poor": "अतिशय वाईट", "Severe": "गंभीर", "Unknown": "अज्ञात"},
}
SOURCE_LABEL = {
    "en": {"biomass": "biomass/stubble burning", "traffic": "vehicular traffic",
           "industry": "industrial emissions", "construction_dust": "construction dust",
           "background": "accumulated background pollution"},
    "hi": {"biomass": "बायोमास/पराली जलाना", "traffic": "वाहनों का यातायात",
           "industry": "औद्योगिक उत्सर्जन", "construction_dust": "निर्माण धूल",
           "background": "संचित पृष्ठभूमि प्रदूषण"},
    "mr": {"biomass": "बायोमास/पराली जाळणे", "traffic": "वाहतूक",
           "industry": "औद्योगिक उत्सर्जन", "construction_dust": "बांधकाम धूळ",
           "background": "साचलेले पार्श्वभूमी प्रदूषण"},
}
# severity buckets: low (<=100), mid (101-300), high (>300)
DO = {
    "en": {"low": ["Enjoy normal outdoor activity.", "Keep windows open for ventilation.",
                   "Stay hydrated."],
           "mid": ["Limit prolonged outdoor exertion.", "Prefer an N95 mask outdoors.",
                   "Keep windows closed during peak hours."],
           "high": ["Avoid all outdoor exercise.", "Wear an N95 mask if you must go out.",
                    "Run an air purifier indoors and seal gaps."]},
    "hi": {"low": ["सामान्य बाहरी गतिविधि करें।", "हवादार रखने के लिए खिड़कियाँ खुली रखें।",
                   "पर्याप्त पानी पिएँ।"],
           "mid": ["लंबे समय तक बाहरी परिश्रम सीमित करें।", "बाहर N95 मास्क पहनें।",
                   "व्यस्त घंटों में खिड़कियाँ बंद रखें।"],
           "high": ["बाहरी व्यायाम पूरी तरह टालें।", "बाहर जाना ज़रूरी हो तो N95 मास्क पहनें।",
                    "घर के अंदर एयर प्यूरीफायर चलाएँ और दरारें बंद करें।"]},
    "mr": {"low": ["नेहमीप्रमाणे बाहेरील हालचाली करा.", "हवेशीरतेसाठी खिडक्या उघड्या ठेवा.",
                   "पुरेसे पाणी प्या."],
           "mid": ["दीर्घ बाहेरील श्रम टाळा.", "बाहेर N95 मास्क वापरा.",
                   "गर्दीच्या वेळेत खिडक्या बंद ठेवा."],
           "high": ["बाहेरील व्यायाम पूर्णपणे टाळा.", "बाहेर जाणे आवश्यक असल्यास N95 मास्क वापरा.",
                    "घरात एअर प्युरिफायर चालवा आणि फटी बंद करा."]},
}
VULN = {
    "en": {"low": "Children and the elderly can go about their day normally.",
           "mid": "Children, the elderly, pregnant women and people with heart or lung conditions should take extra care.",
           "high": "Vulnerable groups — children, the elderly, pregnant women, outdoor workers and heart/lung patients — must stay indoors."},
    "hi": {"low": "बच्चे और बुज़ुर्ग सामान्य रूप से दिनचर्या रख सकते हैं।",
           "mid": "बच्चे, बुज़ुर्ग, गर्भवती महिलाएँ और हृदय या फेफड़े के रोगी विशेष सावधानी बरतें।",
           "high": "संवेदनशील समूह — बच्चे, बुज़ुर्ग, गर्भवती महिलाएँ, बाहरी श्रमिक और हृदय/फेफड़े के रोगी — घर के अंदर रहें।"},
    "mr": {"low": "मुले आणि ज्येष्ठ नागरिक नेहमीप्रमाणे दिनक्रम ठेवू शकतात.",
           "mid": "मुले, ज्येष्ठ, गर्भवती महिला आणि हृदय किंवा फुफ्फुसाचे रुग्ण यांनी विशेष काळजी घ्यावी.",
           "high": "संवेदनशील गट — मुले, ज्येष्ठ, गर्भवती महिला, बाहेरील कामगार आणि हृदय/फुफ्फुस रुग्ण — यांनी घरातच राहावे."},
}


def _bucket(aqi: float) -> str:
    if aqi <= 100:
        return "low"
    return "mid" if aqi <= 300 else "high"


def _hex_now(city: str, hex_id: str):
    nc = pd.read_parquet(snap_dir(city) / "hex_nowcast.parquet")
    nc["ts_utc"] = pd.to_datetime(nc["ts_utc"], utc=True)
    row = nc[(nc["hex_id"] == hex_id) & (nc["ts_utc"] == nc["ts_utc"].max())]
    return row.iloc[0] if not row.empty else None


def _locality(city: str, hex_id: str) -> str:
    grid = pd.read_parquet(geo_city_dir(city) / "grid.parquet")
    match = grid[grid["hex_id"] == hex_id]
    return str(match.iloc[0]["locality"]) if not match.empty else hex_id


def _peak_24h(city: str, hex_id: str):
    path = snap_dir(city) / "forecasts.parquet"
    if not path.exists():
        return None, None
    fc = pd.read_parquet(path)
    fc = fc[(fc["hex_id"] == hex_id) & (fc["horizon_h"] <= 24)]
    if fc.empty:
        return None, None
    top = fc.loc[fc["aqi_pred"].idxmax()]
    ist = (pd.to_datetime(top["target_ts"], utc=True) + IST).strftime("%d %b %H:%M IST")
    return int(round(top["aqi_pred"])), ist


def _primary_source(city: str, hex_id: str, lang: str) -> str:
    path = snap_dir(city) / "attribution.parquet"
    if not path.exists():
        return SOURCE_LABEL[lang]["background"]
    attr = pd.read_parquet(path)
    attr["ts_utc"] = pd.to_datetime(attr["ts_utc"], utc=True)
    latest = attr[attr["ts_utc"] == attr["ts_utc"].max()]
    row = latest[latest["hex_id"] == hex_id]
    if row.empty:
        return SOURCE_LABEL[lang]["background"]
    shares = {s: float(row.iloc[0][s]) for s in SOURCES}
    return SOURCE_LABEL[lang][max(shares, key=shares.get)]


def generate_advisory(city: str, hex_id: str, lang: str = "en") -> dict:
    lang = lang if lang in ("en", "hi", "mr") else "en"
    now = _hex_now(city, hex_id)
    if now is None:
        return {"lang": lang, "text": "No nowcast available for this location yet.",
                "generated_by": "template"}
    aqi_now = int(round(float(now["aqi"])))
    peak_aqi, peak_win = _peak_24h(city, hex_id)
    bucket = _bucket(max(aqi_now, peak_aqi or aqi_now))
    do = DO[lang][bucket]
    fields = {
        "locality": _locality(city, hex_id),
        "aqi_now": aqi_now, "category": CATEGORY[lang].get(str(now["category"]), str(now["category"])),
        "peak_24h_aqi": peak_aqi if peak_aqi is not None else aqi_now,
        "peak_window_ist": peak_win or "the next few hours",
        "primary_source_label": _primary_source(city, hex_id, lang),
        "do_1": do[0], "do_2": do[1], "do_3": do[2], "vulnerable_note": VULN[lang][bucket],
    }
    text = _TEMPLATES.get_template(f"{lang}.md.j2").render(**fields).strip()
    generated_by = "template"
    if is_enabled():
        polished = polish(text, lang)
        if polished and polished != text:
            text, generated_by = polished, "template+llm"
    return {"lang": lang, "text": text, "generated_by": generated_by}


if __name__ == "__main__":
    import sys
    city, hexid = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("delhi", "")
    for lg in ("en", "hi", "mr"):
        print(generate_advisory(city, hexid, lg))
