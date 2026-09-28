import datetime
import json
import re

from pydantic import BaseModel, ValidationError


class ProductionExtraction(BaseModel):
    subsidiary: str | None = None
    period: str | None = None
    production_lt: float | None = None
    dispatch_lt: float | None = None
    offtake_lt: float | None = None
    rom_lt: float | None = None
    washery_output_lt: float | None = None
    grades: str | None = None


class GeologicalExtraction(BaseModel):
    subsidiary: str | None = None
    block: str | None = None
    seam: str | None = None
    borehole_id: str | None = None
    depth_m: float | None = None
    seam_thickness_m: float | None = None
    reserves_mt: float | None = None
    grade: str | None = None


class ParliamentaryQExtraction(BaseModel):
    question: str | None = None
    answer_summary: str | None = None
    ministry: str | None = None
    year: int | None = None
    subsidiary: str | None = None


class DailyShiftExtraction(BaseModel):
    report_date: str | None = None
    mine: str | None = None
    relay: str | None = None
    shift: str | None = None
    total_ob_m3: float | None = None
    total_lignite_mt: float | None = None
    power_generation_mw: float | None = None


class StoppageExtraction(BaseModel):
    report_date: str | None = None
    mine: str | None = None
    machines: list[dict] | None = None


DAILY_SHIFT_PROMPT = (
    "Extract daily shift production and supply figures from this mine operational report. "
    "Output tonnes are in metric tonnes (mt); overburden in cubic metres (m3). "
    "The document's TOTAL LIGNITE line is the shift total - use it, not per-machine output. "
    "A stated value of 0 (e.g. 'TOTAL OB 0') is a real value: report 0, never null. "
    "Example: 'TOTAL OB 0' gives \"total_ob_m3\": 0, and 'TOTAL LIGNITE 0 mt' gives "
    "\"total_lignite_mt\": 0. "
    "Use null only when the field does not appear in the document at all. "
    'Return ONLY JSON: {"fields": {"report_date": "DD.MM.YYYY"|null, "mine": str|null, "relay": str|null, '
    '"shift": str|null, "total_ob_m3": number|null, "total_lignite_mt": number|null, '
    '"power_generation_mw": number|null}, "confidence": {field_name: 0.0-1.0}}. '
    "Use null for fields not present."
)

STOPPAGE_PROMPT = (
    "Extract per-machine working hours and stoppages from this mine stoppage report. "
    "Machines appear as section headers exactly like: "
    "'LBS/BWE-1029 / LIGNITE / TWH: 18.45 /EWH:18.45 / Output: 9,600.000 / Rate: 512.000' "
    "followed by stoppage rows like '1000 1200 02.00 Daily maintenance'. "
    "machine_id is the token before the first ' /' (e.g. 'LBS/BWE-1029'); material is the word after it "
    "(e.g. 'LIGNITE', 'OVER BURDEN'); twh_h is after 'TWH:', ewh_h after 'EWH:', output_mt after 'Output:' "
    "(strip commas), rate after 'Rate:'. "
    "Include EVERY machine header in the document - typically 5 to 10 machines. "
    "Do NOT invent machine names from stoppage reason text. "
    'Example: header "LBS/BWE-1029 / LIGNITE / TWH: 18.45 /EWH:18.45 / Output: 9,600.000 / Rate: 512.000" '
    'with row "1000 1200 02.00 Daily maintenance" gives '
    '{"machine_id": "LBS/BWE-1029", "material": "LIGNITE", "twh_h": 18.45, "ewh_h": 18.45, '
    '"output_mt": 9600.0, "rate": 512.0, "stoppages": [{"from_hhmm": "1000", "to_hhmm": "1200", '
    '"duration_h": 2.0, "reason": "Daily maintenance"}]}. '
    "Each entry of 'machines' is one machine: {\"machine_id\": str, \"material\": str, \"twh_h\": number, "
    "\"ewh_h\": number, \"output_mt\": number, \"rate\": number, "
    "\"stoppages\": [{\"from_hhmm\": str, \"to_hhmm\": str, \"duration_h\": number, \"reason\": str}]}. "
    'Return ONLY JSON: {"fields": {"report_date": "DD.MM.YYYY"|null, "mine": str|null, '
    '"machines": [as above]}, "confidence": {"report_date": 0.0-1.0, "mine": 0.0-1.0, "machines": 0.0-1.0}}. '
    "Times are 24h clock; durations in hours; output in metric tonnes."
)

SCHEMAS: dict[str, dict] = {
    "production_report": {
        "model": ProductionExtraction,
        "items_key": None,
        "prompt": (
            "Extract coal production figures from this Coal India subsidiary document. "
            "All tonnage values MUST be in lakh tonnes. If a document (such as national CCO statistics or Ministry "
            "reports) states figures in Million Tonnes (MT), convert MT to lakh tonnes by multiplying by 10 "
            "(e.g. 893.19 MT = 8931.9 lakh tonnes). When a figure appears in both lakh tonnes and million tonnes, "
            "e.g. '7810.56 lakh tonnes (781.056 million tonnes)', use the LAKH-TONNES number. "
            "rom_lt is run-of-mine production (raw coal before washing), often written as "
            "'ROM production was X lakh tonnes' or 'ROM coal production'. "
            "period: specify the exact quarter and year (e.g. 'Q1 2022', 'Q2 2024') or fiscal year (e.g. '2022-23') as written. "
            "grades: coal quality grades mentioned (distinguish non-coking thermal G-grades from metallurgical coking washery grades). "
            'Return ONLY JSON: {"fields": {"subsidiary": str|null, "period": str|null, '
            '"production_lt": number|null, "dispatch_lt": number|null, "offtake_lt": number|null, '
            '"rom_lt": number|null, "washery_output_lt": number|null, "grades": str|null}, '
            '"confidence": {field_name: 0.0-1.0}}. Use null for fields not present.'
        ),
    },
    "geological": {
        "model": GeologicalExtraction,
        "items_key": None,
        "prompt": (
            "Extract geological details from this Coal India document. "
            "subsidiary: the coal company abbreviation named in the text "
            "(one of ECL, BCCL, CCL, NCL, WCL, SECL, MCL, NEC, CMPDIL, NLC) - "
            "NEVER 'Coal India Limited' and never the full company name. "
            "grade: the single coal grade code (e.g. 'G3'), or null if absent. "
            "borehole_id: copy the full identifier exactly as written, including the block "
            "prefix (e.g. 'Suliyari-BH02', 'Kurasia-BH77'), never shorten it to just the BH number. "
            'Return ONLY JSON: {"fields": {"subsidiary": str|null, "block": str|null, "seam": str|null, '
            '"borehole_id": str|null, "depth_m": number|null, "seam_thickness_m": number|null, '
            '"reserves_mt": number|null, "grade": str|null}, '
            '"confidence": {field_name: 0.0-1.0}}. Use null for fields not present.'
        ),
    },
    "parliamentary_q": {
        "model": ParliamentaryQExtraction,
        "items_key": None,
        "prompt": (
            "Extract details from this parliamentary question/answer document about coal. "
            "ministry: always the plain lowercase word 'coal' - even if the text says "
            "'Ministry of Coal' or 'Minister of Coal'. "
            "subsidiary: the specific coal company named in the document, written as in the text "
            "(e.g. 'coal india limited', 'MCL', 'NCL', 'SECL'); null if only generic ministry "
            "statements appear. "
            "year: the calendar year the question was ANSWERED, as a plain number. "
            "Example: 'Lok Sabha Question 4471: the Minister of Coal was asked about coal "
            "production trends in Jharkhand during 2023' gives "
            '{"ministry": "coal", "year": 2023, "subsidiary": null}. '
            'Return ONLY JSON: {"fields": {"question": str|null, "answer_summary": str|null, '
            '"ministry": str|null, "year": number|null, "subsidiary": str|null}, '
            '"confidence": {field_name: 0.0-1.0}}. Use null for fields not present.'
        ),
    },
    "daily_shift_report": {
        "model": DailyShiftExtraction,
        "prompt": DAILY_SHIFT_PROMPT,
        "period_type": "daily",
        "items_key": None,
    },
    "stoppage_report": {
        "model": StoppageExtraction,
        "prompt": STOPPAGE_PROMPT,
        "period_type": "daily",
        "items_key": "machines",
    },
}

# field -> (unit, period_type). Fields absent from UNIT_REGISTRY get "" / "quarterly".
UNIT_REGISTRY: dict[str, tuple[str, str]] = {
    "production_lt": ("lakh_tonnes", "quarterly"),
    "dispatch_lt": ("lakh_tonnes", "quarterly"),
    "offtake_lt": ("lakh_tonnes", "quarterly"),
    "rom_lt": ("lakh_tonnes", "quarterly"),
    "washery_output_lt": ("lakh_tonnes", "quarterly"),
    "reserves_mt": ("mt", "point_in_time"),
    "total_lignite_mt": ("tonnes", "daily"),
    "total_ob_m3": ("m3", "daily"),
    "power_generation_mw": ("mw", "daily"),
    "twh_h": ("hours", "daily"),
    "ewh_h": ("hours", "daily"),
    "output_mt": ("tonnes", "daily"),
    "rate": ("tonnes_per_hour", "daily"),
    "stoppage_duration_h": ("hours", "daily"),
}

NUMERIC_FIELDS = {
    "production_lt", "dispatch_lt", "offtake_lt", "rom_lt", "washery_output_lt",
    "depth_m", "seam_thickness_m", "reserves_mt", "year",
    "total_ob_m3", "total_lignite_mt", "power_generation_mw",
    "twh_h", "ewh_h", "output_mt", "rate", "stoppage_duration_h",
}

DATE_RE = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4}|\d{2})\b")


def field_unit(field_name: str) -> str:
    if field_name in UNIT_REGISTRY:
        return UNIT_REGISTRY[field_name][0]
    return "lakh_tonnes" if field_name.endswith("_lt") else ("mt" if field_name.endswith("_mt") else "")


def field_period_type(field_name: str) -> str:
    if field_name in UNIT_REGISTRY:
        return UNIT_REGISTRY[field_name][1]
    return "quarterly"


def parse_report_date(text: str) -> str:
    """Find the first DD.MM.YYYY / DD-MM-YYYY / DD/MM/YYYY date in text -> 'YYYY-MM-DD' or ''.
    Supports 2-digit years (e.g. 9.10.22 -> 2022-10-09).
    Uses datetime.date so impossible dates (99.99.2026) are rejected."""
    m = DATE_RE.search(text or "")
    if not m:
        return ""
    try:
        yr = int(m.group(3))
        if yr < 100:
            yr += 2000
        return datetime.date(yr, int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return ""


def expand_items(fields: dict, confidence: dict, doc_type: str) -> list[dict]:
    """Split list-of-dict fields (e.g. stoppage machines) into one flat record per item.
    Scalar fields stay as a single record. Returns [{field_name, item, value, confidence}]."""
    schema = SCHEMAS[doc_type]
    items_key = schema.get("items_key")
    out: list[dict] = []
    if items_key and isinstance(fields.get(items_key), list):
        items = fields[items_key]
        scalar = {k: v for k, v in fields.items() if k != items_key}
        base_conf = float(confidence.get(items_key, 0.5) or 0.5)
        for idx, entry in enumerate(items):
            if not isinstance(entry, dict):
                continue
            item_name = str(entry.get("machine_id") or entry.get("item") or f"{items_key}#{idx + 1}")
            stoppages = entry.pop("stoppages", None) or []
            for k, v in entry.items():
                if k in ("machine_id", "item", "material"):
                    continue
                if v is None:
                    continue
                out.append({
                    "field_name": k,
                    "item": item_name,
                    "value": v,
                    "confidence": float(confidence.get(f"{items_key}.{k}", base_conf) or base_conf),
                })
            for s_idx, s in enumerate(stoppages):
                if not isinstance(s, dict):
                    continue
                dur = s.get("duration_h")
                reason = str(s.get("reason") or "").strip()
                from_h = str(s.get("from_hhmm") or "")
                to_h = str(s.get("to_hhmm") or "")
                label = f"{item_name}|stop#{s_idx + 1}|{from_h}-{to_h}|{reason[:140]}".rstrip("|")
                if dur is not None:
                    out.append({
                        "field_name": "stoppage_duration_h",
                        "item": label,
                        "value": dur,
                        "confidence": float(confidence.get(f"{items_key}.stoppages", base_conf) or base_conf),
                    })
                elif reason:
                    out.append({
                        "field_name": "stoppage_reason",
                        "item": label,
                        "value": reason,
                        "confidence": float(confidence.get(f"{items_key}.stoppages", base_conf) or base_conf),
                    })
        # scalar fields of the document itself (report_date, mine, ...)
        for k, v in scalar.items():
            if v is None:
                continue
            out.append({
                "field_name": k,
                "item": "",
                "value": v,
                "confidence": float(confidence.get(k, 0.5) or 0.5),
            })
        return out
    # plain schema: one record per field
    for k, v in fields.items():
        if v is None:
            continue
        out.append({
            "field_name": k,
            "item": "",
            "value": v,
            "confidence": float(confidence.get(k, 0.5) or 0.5),
        })
    return out


def get_schema(doc_type: str) -> dict:
    if doc_type not in SCHEMAS:
        raise ValueError(f"unknown doc_type '{doc_type}'. Known: {', '.join(sorted(SCHEMAS))}")
    return SCHEMAS[doc_type]


def parse_extraction(raw: str, doc_type: str) -> dict:
    """Parse LLM output -> {"fields": {...}, "confidence": {...}} validated against the schema."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in LLM output")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON from LLM: {e}")
    fields = data.get("fields", {})
    confidence = data.get("confidence", {})
    model = get_schema(doc_type)["model"]
    try:
        validated = model(**{k: v for k, v in fields.items() if k in model.model_fields}).model_dump()
    except ValidationError as e:
        raise ValueError(f"extraction failed schema validation: {e.error_count()} error(s) in {list(fields)}")
    return {"fields": validated, "confidence": confidence}
