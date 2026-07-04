
import json
import re
import sqlite3
from datetime import datetime

# ─────────────────────────────────────────────
#  ORGANIZATION CLASSIFICATION
# ─────────────────────────────────────────────

# Each org type maps to keyword signals with associated weights.
# Scoring is purely additive — no hardcoded domain assumptions.
ORG_TYPE_SIGNALS: dict[str, list[tuple[str, int]]] = {
    "Hospital": [
        ("hospital", 10), ("inpatient", 8), ("outpatient", 6),
        ("emergency department", 8), ("casualty", 6), ("ward", 5),
        ("admission", 5), ("discharge", 5), ("icu", 6), ("ot ", 5),
        ("operation theater", 7), ("surgery", 6), ("surgeon", 6),
        ("bed capacity", 8), ("nursing", 5), ("maternity", 6),
        ("nicu", 7), ("dialysis", 6), ("blood bank", 6),
    ],
    "Diagnostic Laboratory": [
        ("diagnostic laboratory", 12), ("diagnostic lab", 10),
        ("pathology lab", 10), ("clinical laboratory", 10),
        ("specimen", 8), ("sample collection", 8), ("test report", 7),
        ("blood test", 6), ("urine test", 6), ("pcr", 6),
        ("culture sensitivity", 8), ("hematology", 6),
        ("biochemistry", 6), ("serology", 6), ("histopathology", 7),
        ("cytology", 6), ("biopsy", 6),
    ],
    "Medical Equipment Distributor": [
        ("medical equipment", 10), ("distributor", 8), ("supplier", 7),
        ("importer", 7), ("authorized dealer", 8), ("dealer", 6),
        ("product catalog", 7), ("biomedical", 6), ("spare parts", 7),
        ("installation", 5), ("after sales", 6), ("warranty", 5),
        ("amc", 6), ("cmc", 6), ("tender", 6), ("procurement", 7),
    ],
    "Pharmaceutical Company": [
        ("pharmaceutical", 10), ("pharma", 8), ("drug", 7),
        ("medicine", 6), ("tablet", 6), ("capsule", 6), ("syrup", 6),
        ("formulation", 7), ("api", 6), ("gmp", 7), ("fda approved", 8),
        ("manufacturing plant", 8), ("molecule", 6), ("generic", 6),
        ("branded", 5), ("drug store", 6),
    ],
    "Medical College": [
        ("medical college", 12), ("mbbs", 10), ("bds", 8),
        ("medical university", 10), ("faculty of medicine", 9),
        ("medical school", 9), ("clinical training", 8),
        ("residency", 7), ("fellowship", 6), ("anatomy", 6),
        ("physiology", 6), ("pharmacology", 6), ("pathology department", 7),
        ("professor", 5), ("dean", 5), ("pmdc", 8), ("usmle", 6),
    ],
    "Clinic": [
        ("clinic", 9), ("polyclinic", 9), ("outpatient clinic", 9),
        ("gp ", 6), ("general practitioner", 7), ("consultation", 6),
        ("appointment", 6), ("walk-in", 7), ("specialist clinic", 8),
        ("dental clinic", 8), ("eye clinic", 7), ("skin clinic", 7),
        ("physiotherapy", 6), ("rehab", 5),
    ],
    "NGO": [
        ("ngo", 10), ("non-governmental", 10), ("non profit", 9),
        ("nonprofit", 9), ("charity", 8), ("foundation", 7),
        ("humanitarian", 8), ("community health", 7), ("donor", 6),
        ("grant", 6), ("volunteer", 6), ("aid", 5), ("welfare", 6),
        ("health camp", 7), ("free medical", 8), ("underprivileged", 7),
    ],
}


def classify_organization(full_text: str) -> dict:
    """
    Score each org type against the full site text using weighted keyword signals.
    Returns the best matching type plus the score breakdown for explainability.
    """
    text = full_text.lower()
    scores: dict[str, int] = {}

    for org_type, signals in ORG_TYPE_SIGNALS.items():
        total = 0
        for keyword, weight in signals:
            if keyword in text:
                total += weight
        scores[org_type] = total

    best_type = max(scores, key=lambda k: scores[k])
    best_score = scores[best_type]

    if best_score < 6:
        best_type = "Unknown"

    return {
        "organization_type": best_type,
        "classification_scores": scores,
    }


# ─────────────────────────────────────────────
#  DEPARTMENT DETECTION
# ─────────────────────────────────────────────

# Canonical department names mapped to their keyword aliases.
DEPARTMENT_KEYWORDS: dict[str, list[str]] = {
    "Cardiology":        ["cardiology", "cardiac", "heart", "echocardiography", "ecg", "cathlab"],
    "Radiology":         ["radiology", "radiologist", "x-ray", "xray", "mri", "ct scan", "ultrasound", "imaging"],
    "Pathology":         ["pathology", "pathologist", "histopathology", "cytology", "biopsy"],
    "Emergency":         ["emergency", "accident & emergency", "a&e", "casualty", "er "],
    "ICU":               ["icu", "intensive care", "critical care", "ccu"],
    "CSSD":              ["cssd", "central sterile", "sterilization"],
    "Operation Theater": ["operation theater", "operation theatre", "ot ", "surgical suite", "surgery"],
    "Blood Bank":        ["blood bank", "transfusion", "blood group"],
    "Laboratory":        ["laboratory", "clinical lab", "diagnostic lab", "specimen"],
    "Pharmacy":          ["pharmacy", "pharmacist", "dispensary", "drug store"],
    "Microbiology":      ["microbiology", "microbiologist", "culture sensitivity", "bacteriology"],
    "Nephrology":        ["nephrology", "nephrologist", "kidney", "dialysis", "renal"],
    "Oncology":          ["oncology", "oncologist", "cancer", "chemotherapy", "radiation therapy"],
    "Gynecology":        ["gynecology", "gynaecology", "obstetrics", "maternity", "labour", "antenatal"],
    "Orthopedics":       ["orthopedics", "orthopaedics", "bone", "fracture", "joint replacement", "spine"],
    "Pediatrics":        ["pediatrics", "paediatrics", "neonatology", "nicu", "child health"],
    "Neurology":         ["neurology", "neurologist", "brain", "stroke", "epilepsy", "eeg"],
    "Dermatology":       ["dermatology", "dermatologist", "skin", "aesthetics"],
    "Ophthalmology":     ["ophthalmology", "ophthalmologist", "eye", "cataract", "retina"],
    "ENT":               ["ent", "ear nose throat", "otolaryngology", "audiology"],
    "Psychiatry":        ["psychiatry", "psychiatrist", "mental health", "psychology"],
    "Physiotherapy":     ["physiotherapy", "physiotherapist", "rehabilitation", "rehab"],
    "Dental":            ["dental", "dentist", "orthodontics", "oral surgery"],
    "Gastroenterology":  ["gastroenterology", "gastroenterologist", "endoscopy", "colonoscopy", "liver"],
    "Urology":           ["urology", "urologist", "bladder", "prostate", "kidney stone"],
}


def detect_departments(full_text: str) -> list[str]:
    """Return a sorted list of detected department names based on keyword presence."""
    text = full_text.lower()
    found = []
    for department, keywords in DEPARTMENT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            found.append(department)
    return sorted(found)


# ─────────────────────────────────────────────
#  PRODUCT RECOMMENDATIONS
# ─────────────────────────────────────────────

DEPARTMENT_PRODUCTS: dict[str, list[str]] = {
    "Cardiology":        ["ECG Machine", "Echocardiography System", "Holter Monitor",
                          "Stress Test System", "Defibrillator", "Cardiac Catheterization Equipment"],
    "Radiology":         ["Digital X-Ray System", "MRI Scanner", "CT Scanner",
                          "Ultrasound Machine", "PACS System", "Fluoroscopy Unit"],
    "Pathology":         ["CBC Analyzer (Hematology)", "Chemistry Analyzer", "Microscope",
                          "IVD Consumables", "Slide Staining System", "Centrifuge"],
    "Emergency":         ["Defibrillator", "Patient Monitor", "Portable Ventilator",
                          "Infusion Pump", "Crash Cart", "Pulse Oximeter"],
    "ICU":               ["Patient Monitor", "Mechanical Ventilator", "Infusion Pump",
                          "Syringe Pump", "ECG Machine", "Suction Machine", "Feeding Pump"],
    "CSSD":              ["Autoclave (Steam Sterilizer)", "Plasma Sterilizer",
                          "Washer Disinfector", "Ultrasonic Cleaner", "Sterility Indicators"],
    "Operation Theater": ["Surgical Lights", "Operating Table", "Anesthesia Machine",
                          "Surgical Instruments Set", "Electrosurgical Unit", "Laparoscopic Tower"],
    "Blood Bank":        ["Blood Bank Refrigerator", "Blood Bag Centrifuge",
                          "Blood Grouping Reagents", "Platelet Agitator", "Plasma Extractor"],
    "Laboratory":        ["CBC Analyzer", "Chemistry Analyzer", "Urinalysis Analyzer",
                          "Coagulation Analyzer", "Biosafety Cabinet", "PCR Machine"],
    "Pharmacy":          ["Laminar Flow Cabinet", "Refrigerator (Vaccine/Drug)",
                          "Pharmacy Management Software", "Pill Counter", "Label Printer"],
    "Microbiology":      ["Incubator", "Autoclave", "Biosafety Cabinet Level 2",
                          "Colony Counter", "Culture Media", "Sensitivity Discs"],
    "Nephrology":        ["Hemodialysis Machine", "Dialysis Water Purification System",
                          "Peritoneal Dialysis Equipment", "Patient Monitor"],
    "Oncology":          ["Linear Accelerator (LINAC)", "Chemotherapy Infusion Pump",
                          "Brachytherapy System", "Patient Monitor", "Oncology Information System"],
    "Gynecology":        ["Fetal Monitor (CTG)", "Ultrasound Machine", "Colposcope",
                          "Delivery Table", "Infant Warmer", "Neonatal Incubator"],
    "Orthopedics":       ["C-Arm Fluoroscopy", "Orthopedic Power Tools", "Bone Cement System",
                          "Arthroscopy Tower", "Spinal Implants"],
    "Pediatrics":        ["Neonatal Incubator", "Infant Warmer", "Pediatric Ventilator",
                          "Pulse Oximeter (Pediatric)", "Phototherapy Unit"],
    "Neurology":         ["EEG Machine", "EMG Machine", "Nerve Conduction Study System",
                          "Transcranial Doppler", "Patient Monitor"],
    "Dermatology":       ["Dermatoscope", "Phototherapy Unit (PUVA/UVB)",
                          "Laser Treatment System", "Cryotherapy Unit"],
    "Ophthalmology":     ["Slit Lamp", "Fundus Camera", "Auto Refractometer",
                          "Tonometer", "Phacoemulsification System", "OCT Scanner"],
    "ENT":               ["Audiometer", "ENT Examination Unit", "Rigid/Flexible Endoscope",
                          "Otoscope", "Tympanometer"],
    "Psychiatry":        ["ECT Machine", "Biofeedback System", "Patient Management Software"],
    "Physiotherapy":     ["Ultrasound Therapy Unit", "TENS Machine", "Shortwave Diathermy",
                          "Laser Therapy Unit", "Traction Unit", "Exercise Equipment"],
    "Dental":            ["Dental Chair", "Intraoral X-Ray", "Autoclave (Dental)",
                          "Dental Handpiece", "Dental CBCT Scanner", "Teeth Whitening System"],
    "Gastroenterology":  ["Video Endoscope", "Video Colonoscope", "Endoscopy Processor",
                          "Capsule Endoscopy System", "Electrosurgical Unit"],
    "Urology":           ["Urodynamics System", "Cystoscope", "Holmium Laser",
                          "Lithotripsy System (ESWL)", "Ultrasound Machine"],
}


def recommend_products(departments: list[str]) -> list[str]:
    """Aggregate unique product recommendations across all detected departments."""
    products = set()
    for dept in departments:
        for product in DEPARTMENT_PRODUCTS.get(dept, []):
            products.add(product)
    return sorted(products)


# ─────────────────────────────────────────────
#  OPPORTUNITY SCORING
# ─────────────────────────────────────────────

ORG_TYPE_BASE_SCORES: dict[str, int] = {
    "Hospital":                      30,
    "Medical College":               20,
    "Diagnostic Laboratory":         20,
    "Clinic":                        15,
    "Pharmaceutical Company":        10,
    "Medical Equipment Distributor":  5,
    "NGO":                           10,
    "Unknown":                        0,
}

DEPARTMENT_BONUS_SCORES: dict[str, int] = {
    "ICU":               20,
    "Operation Theater": 18,
    "Laboratory":        15,
    "Blood Bank":        12,
    "Radiology":         12,
    "Pathology":         12,
    "Cardiology":        10,
    "Oncology":          10,
    "Nephrology":        10,
    "CSSD":               8,
    "Emergency":          8,
    "Neurology":          8,
    "Gastroenterology":   8,
    "Gynecology":         7,
    "Orthopedics":        7,
    "Microbiology":       7,
    "Pediatrics":         6,
    "Pharmacy":           5,
    "Physiotherapy":      5,
    "Urology":            5,
    "Ophthalmology":      5,
    "ENT":                5,
    "Dermatology":        4,
    "Psychiatry":         4,
    "Dental":             4,
}

_MAX_RAW_SCORE = 150


def calculate_opportunity_score(
    org_type: str,
    departments: list[str],
    contacts: dict,
    all_page_urls: list[str],
) -> dict:
    """
    Produce a transparent, explainable opportunity score normalized to 100.

    Breakdown:
      - Organization type base score   (up to 30)
      - Department bonuses             (capped at 40)
      - Contact email presence         (+10)
      - Procurement / tender page      (+20)
    """
    breakdown: dict[str, int] = {}
    raw = 0

    base = ORG_TYPE_BASE_SCORES.get(org_type, 0)
    breakdown["organization_type"] = base
    raw += base

    dept_total = 0
    dept_detail: dict[str, int] = {}
    for dept in departments:
        bonus = DEPARTMENT_BONUS_SCORES.get(dept, 3)
        dept_detail[dept] = bonus
        dept_total += bonus
    dept_contribution = min(dept_total, 40)
    breakdown["departments"] = dept_contribution
    breakdown["department_detail"] = dept_detail
    raw += dept_contribution

    has_email = bool(contacts.get("emails"))
    email_bonus = 10 if has_email else 0
    breakdown["has_contact_email"] = email_bonus
    raw += email_bonus

    procurement_keywords = ["procurement", "tender", "rfq", "quotation", "bid", "purchase"]
    has_procurement = any(
        any(kw in url.lower() for kw in procurement_keywords)
        for url in all_page_urls
    )
    procurement_bonus = 20 if has_procurement else 0
    breakdown["has_procurement_page"] = procurement_bonus
    raw += procurement_bonus

    final_score = min(round((raw / _MAX_RAW_SCORE) * 100), 100)

    return {
        "score": final_score,
        "breakdown": breakdown,
    }


# ─────────────────────────────────────────────
#  LEAD QUALIFICATION ENGINE
# ─────────────────────────────────────────────

PRIVATE_HOSPITAL_KEYWORDS = [
    "private hospital", "pvt ltd", "pvt. ltd", "(private) limited",
    "private limited", "trust hospital", "private healthcare",
    "a private institution", "privately owned",
]

DECISION_MAKER_TITLES = [
    "chief executive officer", "ceo", "medical director", "managing director",
    "medical superintendent", "chairman", "chief medical officer", "cmo",
    "hospital director", "director", "founder", "president",
]

# Matches: Capitalized Name (2-4 words), optionally prefixed with a courtesy title
DECISION_MAKER_NAME_RE = re.compile(
    r"(?:(?:Dr\.?|Prof\.?|Mr\.?|Mrs\.?|Ms\.?)\s+)?"
    r"[A-Z][a-zA-Z.\-]+(?:\s+[A-Z][a-zA-Z.\-]+){1,3}"
)


def detect_private_hospital(text: str) -> bool:
    """Return True if the site text signals a private (as opposed to public/govt) hospital."""
    lower = text.lower()
    return any(kw in lower for kw in PRIVATE_HOSPITAL_KEYWORDS)


def detect_decision_maker(text: str) -> dict:
    """
    Look for a named individual near a leadership title.
    Returns found=True with matched snippets for sales-team transparency.
    Search window is clipped to the current sentence to avoid bleeding
    in names/words from unrelated, preceding sentences.
    """
    matches = []
    lower = text.lower()

    for title in DECISION_MAKER_TITLES:
        idx = lower.find(title)
        if idx == -1:
            continue

        # Clip window to the current sentence: nearest sentence boundary
        # before the title, and a fixed lookahead after it.
        sentence_start = max(
            lower.rfind(".", 0, idx),
            lower.rfind("!", 0, idx),
            lower.rfind("?", 0, idx),
            lower.rfind("\n", 0, idx),
        )
        window_start = sentence_start + 1 if sentence_start != -1 else max(0, idx - 60)
        window_end = min(len(text), idx + len(title) + 60)
        window = text[window_start:window_end]

        name_match = DECISION_MAKER_NAME_RE.search(window)
        if name_match:
            snippet = name_match.group(0).strip()
            if len(snippet.split()) >= 2:
                matches.append(f"{snippet} ({title.title()})")

    seen = set()
    unique_matches = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            unique_matches.append(m)

    return {"found": bool(unique_matches), "matches": unique_matches[:5]}


# Lead score parameters per business rules
LEAD_SCORE_RULES = {
    "private_hospital": 20,
    "large_hospital": 20,      # 20+ departments
    "has_pathology": 15,
    "has_icu": 10,
    "has_cath_lab": 10,
    "has_radiology": 10,
    "has_contact_email": 5,
    "has_procurement_page": 10,
    "has_decision_maker": 5,   # bonus signal, not in original table
}

LARGE_HOSPITAL_DEPARTMENT_THRESHOLD = 20

LEAD_GRADE_BANDS = [
    (90, "A+", "Visit within 7 days"),
    (75, "A", "Visit within 14 days"),
    (55, "B", "Follow up by phone/email within 30 days"),
    (35, "C", "Add to nurture campaign"),
    (0, "D", "Low priority — monitor only"),
]


def grade_lead(score: int) -> dict:
    """Map a numeric lead score to a grade band and recommended sales action."""
    for threshold, grade, action in LEAD_GRADE_BANDS:
        if score >= threshold:
            return {"grade": grade, "recommended_action": action}
    return {"grade": "D", "recommended_action": "Low priority — monitor only"}


def calculate_lead_score(
    full_text: str,
    org_type: str,
    departments: list[str],
    contacts: dict,
    all_page_urls: list[str],
) -> dict:
    """
    Business-rule lead scoring, separate from the generic opportunity score.
    Returns score, grade, recommended action, and a transparent breakdown.
    """
    breakdown: dict[str, int] = {}
    raw = 0

    is_private = detect_private_hospital(full_text)
    breakdown["private_hospital"] = LEAD_SCORE_RULES["private_hospital"] if is_private else 0
    raw += breakdown["private_hospital"]

    is_large = len(departments) >= LARGE_HOSPITAL_DEPARTMENT_THRESHOLD
    breakdown["large_hospital"] = LEAD_SCORE_RULES["large_hospital"] if is_large else 0
    raw += breakdown["large_hospital"]

    has_pathology = "Pathology" in departments
    breakdown["has_pathology"] = LEAD_SCORE_RULES["has_pathology"] if has_pathology else 0
    raw += breakdown["has_pathology"]

    has_icu = "ICU" in departments
    breakdown["has_icu"] = LEAD_SCORE_RULES["has_icu"] if has_icu else 0
    raw += breakdown["has_icu"]

    has_cath_lab = (
        "cath lab" in full_text.lower()
        or "cathlab" in full_text.lower()
        or "catheterization" in full_text.lower()
    )
    breakdown["has_cath_lab"] = LEAD_SCORE_RULES["has_cath_lab"] if has_cath_lab else 0
    raw += breakdown["has_cath_lab"]

    has_radiology = "Radiology" in departments
    breakdown["has_radiology"] = LEAD_SCORE_RULES["has_radiology"] if has_radiology else 0
    raw += breakdown["has_radiology"]

    has_email = bool(contacts.get("emails"))
    breakdown["has_contact_email"] = LEAD_SCORE_RULES["has_contact_email"] if has_email else 0
    raw += breakdown["has_contact_email"]

    procurement_keywords = ["procurement", "tender", "rfq", "quotation", "bid", "purchase"]
    has_procurement = any(
        any(kw in url.lower() for kw in procurement_keywords) for url in all_page_urls
    )
    breakdown["has_procurement_page"] = LEAD_SCORE_RULES["has_procurement_page"] if has_procurement else 0
    raw += breakdown["has_procurement_page"]

    decision_maker = detect_decision_maker(full_text)
    breakdown["has_decision_maker"] = (
        LEAD_SCORE_RULES["has_decision_maker"] if decision_maker["found"] else 0
    )
    raw += breakdown["has_decision_maker"]

    final_score = min(raw, 100)
    grading = grade_lead(final_score)

    return {
        "score": final_score,
        "grade": grading["grade"],
        "recommended_action": grading["recommended_action"],
        "breakdown": breakdown,
        "decision_makers": decision_maker["matches"],
        "is_private_hospital": is_private,
        "is_large_hospital": is_large,
    }


# ─────────────────────────────────────────────
#  PRODUCT OPPORTUNITY MATRIX
# ─────────────────────────────────────────────

# Priority tier per department — reflects typical deal size / urgency.
# Defaults to "Medium" for any department not explicitly listed.
DEPARTMENT_PRIORITY: dict[str, str] = {
    "ICU": "High",
    "Operation Theater": "High",
    "Pathology": "High",
    "Laboratory": "High",
    "Radiology": "Medium",
    "Cardiology": "Medium",
    "Blood Bank": "Medium",
    "Oncology": "Medium",
    "Nephrology": "Medium",
    "Emergency": "Medium",
    "CSSD": "Medium",
    "Gynecology": "Low",
    "Orthopedics": "Low",
    "Pediatrics": "Low",
    "Microbiology": "Low",
    "Pharmacy": "Low",
    "Neurology": "Low",
    "Gastroenterology": "Low",
    "Urology": "Low",
    "Ophthalmology": "Low",
    "ENT": "Low",
    "Dermatology": "Low",
    "Psychiatry": "Low",
    "Physiotherapy": "Low",
    "Dental": "Low",
}


def build_opportunity_matrix(departments: list[str]) -> list[dict]:
    """
    Generate a Department → Opportunity (Product) → Priority matrix.
    This is the structured, sales-ready version of the flat product list,
    and is designed to later be re-mapped onto a specific vendor's catalog.
    """
    matrix = []
    for dept in departments:
        priority = DEPARTMENT_PRIORITY.get(dept, "Medium")
        for product in DEPARTMENT_PRODUCTS.get(dept, []):
            matrix.append({
                "department": dept,
                "opportunity": product,
                "priority": priority,
            })
    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    matrix.sort(key=lambda row: (priority_order.get(row["priority"], 1), row["department"], row["opportunity"]))
    return matrix


# ─────────────────────────────────────────────
#  SALES READINESS CHECKLIST
# ─────────────────────────────────────────────

def build_sales_checklist(
    org_type: str,
    departments: list[str],
    contacts: dict,
    all_page_urls: list[str],
    lead_qualification: dict,
) -> list[dict]:
    """
    Produce a quick-glance checklist a salesperson can scan in seconds.
    Each item is a dict with a label and a boolean 'passed' flag.
    """
    procurement_keywords = ["procurement", "tender", "rfq", "quotation", "bid", "purchase"]
    has_procurement = any(
        any(kw in url.lower() for kw in procurement_keywords) for url in all_page_urls
    )

    checklist = [
        {"label": "Website Available", "passed": len(all_page_urls) > 0},
        {"label": "Contact Email Found", "passed": bool(contacts.get("emails"))},
        {"label": "Phone Found", "passed": bool(contacts.get("phones"))},
        {"label": "Decision Maker Found", "passed": bool(lead_qualification.get("decision_makers"))},
        {"label": "Procurement Page Present", "passed": has_procurement},
        {"label": "Multiple Clinical Departments", "passed": len(departments) >= 3},
        {"label": "Pathology Lab Present", "passed": "Pathology" in departments},
    ]
    return checklist


# ─────────────────────────────────────────────
#  AI EMAIL GENERATOR (OpenRouter)
# ─────────────────────────────────────────────

# Token budget is tight (4,000/day on OpenRouter free tier), so this prompt
# is deliberately compact and only fires for qualified leads by default.
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
EMAIL_MAX_OUTPUT_TOKENS = 280  # keeps response short; ~200-word email + small margin


def generate_outreach_email(
    org_name: str,
    org_type: str,
    departments: list[str],
    recommended_products: list[str],
    contacts: dict,
    api_key: str | None,
) -> dict:
    """
    Generate a short, professional outreach email using ONLY extracted facts.
    Calls OpenRouter directly via requests (no extra SDK dependency).
    Returns {"email": str, "error": str|None} so failures don't break the pipeline.
    """
    if not api_key:
        return {"email": None, "error": "No OpenRouter API key provided (set OPENROUTER_API_KEY)."}

    if not departments:
        return {"email": None, "error": "No departments detected — skipping email generation to avoid fabrication."}

    primary_department = departments[0]
    primary_product = None
    for product in recommended_products:
        if product in DEPARTMENT_PRODUCTS.get(primary_department, []):
            primary_product = product
            break
    if not primary_product and recommended_products:
        primary_product = recommended_products[0]

    contact_line = contacts.get("emails", ["the team"])[0] if contacts.get("emails") else "the team"

    system_prompt = (
        "You write short, professional B2B medical-sales introductory emails. "
        "Use ONLY the facts given. Do not invent products, names, or claims. "
        "Mention exactly one department and one service/product. "
        "Keep the email under 200 words. End with a request for a brief meeting."
    )
    user_prompt = (
        f"Organization name: {org_name or 'the organization'}\n"
        f"Organization type: {org_type}\n"
        f"Department to mention: {primary_department}\n"
        f"Product/service to mention: {primary_product or 'relevant equipment'}\n"
        f"Contact reference: {contact_line}\n\n"
        "Write the introductory email now."
    )

    try:
        import requests
        response = requests.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_MODEL,
                "max_tokens": EMAIL_MAX_OUTPUT_TOKENS,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        email_text = data["choices"][0]["message"]["content"].strip()
        return {"email": email_text, "error": None}
    except Exception as exc:
        return {"email": None, "error": f"Email generation failed: {exc}"}


# ─────────────────────────────────────────────
#  EXECUTIVE REPORT FORMATTER
# ─────────────────────────────────────────────

def format_executive_report(org_name: str, intelligence: dict, contacts: dict, checklist: list[dict]) -> str:
    """
    Render the intelligence profile as a sectioned, plain-text executive report
    a sales manager can scan in under two minutes.
    """
    lines = []

    def section(title: str):
        lines.append("=" * 40)
        lines.append(title)
        lines.append("=" * 40)

    lead = intelligence.get("lead_qualification", {})
    matrix = intelligence.get("opportunity_matrix", [])

    confidence = intelligence.get("classification_confidence", {})

    section("EXECUTIVE SUMMARY")
    lines.append(f"Organization     : {org_name or 'Unknown'}")
    lines.append(f"Type             : {intelligence.get('organization_type', 'Unknown')}")
    conf_pct   = confidence.get("confidence_pct", 0)
    conf_label = confidence.get("confidence_label", "N/A")
    lines.append(f"Type Confidence  : {conf_pct}% ({conf_label})")
    lines.append(f"Confidence Reason: {confidence.get('reason', 'N/A')}")
    lines.append(f"Departments      : {len(intelligence.get('departments', []))} detected")
    lines.append(f"Lead Grade       : {lead.get('grade', 'D')} (Score: {lead.get('score', 0)}/100)")
    lines.append(f"Next Action      : {lead.get('recommended_action', 'N/A')}")
    lines.append("")

    section("KEY CONTACTS & RECOMMENDATIONS")
    contact_recs = intelligence.get("contact_recommendations", [])
    if contact_recs:
        lines.append(f"  {'Contact':<35} {'Type':<6} {'Reason':<30} Confidence")
        lines.append(f"  {'-'*35} {'-'*6} {'-'*30} ----------")
        for rec in contact_recs:
            lines.append(
                f"  {rec['contact']:<35} {rec['type']:<6} "
                f"{rec['reason']:<30} {rec['confidence']}"
            )
    else:
        emails = contacts.get("emails") or ["None found"]
        phones = contacts.get("phones") or ["None found"]
        lines.append(f"Emails : {', '.join(emails)}")
        lines.append(f"Phones : {', '.join(phones)}")
    lines.append("")

    section("DECISION MAKERS & STAKEHOLDERS")
    stakeholders = intelligence.get("stakeholders", [])
    if stakeholders:
        for s in stakeholders:
            lines.append(f"  {s['stars']}  {s['name']}  —  {s['title']}  (Priority: {s['priority']})")
    else:
        lines.append("  No decision makers identified.")
    lines.append("")

    section("DEPARTMENT HEADS")
    dept_heads = intelligence.get("department_heads", [])
    if dept_heads:
        for dh in dept_heads:
            lines.append(f"  {dh['department']}")
            lines.append(f"    ↓  {dh['person']}")
            lines.append(f"    ↓  Potential buyer for {dh['product_hint']}")
    else:
        lines.append("  No department head links identified.")
    lines.append("")

    section("DEPARTMENTS")
    departments = intelligence.get("departments", [])
    lines.append(", ".join(departments) if departments else "None detected")
    lines.append("")

    section("SALES OPPORTUNITIES")
    if matrix:
        lines.append(f"  {'Priority':<8} {'Department':<20} Opportunity")
        lines.append(f"  {'-'*8} {'-'*20} -----------")
        for row in matrix[:10]:
            lines.append(f"  [{row['priority']:<6}] {row['department']:<20} {row['opportunity']}")
        if len(matrix) > 10:
            lines.append(f"  ... and {len(matrix) - 10} more (see full report JSON)")
    else:
        lines.append("  No opportunities identified.")
    lines.append("")

    section("AI SALES STRATEGY")
    strategy = intelligence.get("sales_strategy")
    strategy_err = intelligence.get("sales_strategy_error")
    if strategy:
        lines.append(strategy)
    elif strategy_err:
        lines.append(f"  Not generated: {strategy_err}")
    else:
        lines.append("  Not generated.")
    lines.append("")

    section("LEAD SCORE")
    lines.append(f"  Score : {lead.get('score', 0)}/100")
    lines.append(f"  Grade : {lead.get('grade', 'D')}")
    breakdown = lead.get("breakdown", {})
    for key, val in breakdown.items():
        if isinstance(val, int) and val > 0:
            lines.append(f"  + {key.replace('_', ' ').title():<28} {val:+d}")
    lines.append("")

    section("SALES READINESS CHECKLIST")
    for item in checklist:
        mark = "✔" if item["passed"] else "✖"
        lines.append(f"  {mark} {item['label']}")
    lines.append("")

    section("RECOMMENDED NEXT ACTION")
    lines.append(f"  {lead.get('recommended_action', 'Monitor only.')}")
    lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────
#  STAKEHOLDER CLASSIFICATION
# ─────────────────────────────────────────────

# Priority score per role title. Higher = more relevant to a medical sales cycle.
# 100 = direct budget/procurement authority; lower = influencer or end-user.
ROLE_PRIORITY: dict[str, int] = {
    "Procurement Manager":        100,
    "Purchase Manager":           100,
    "Purchase Officer":            90,
    "Chief Executive Officer":    100,
    "Ceo":                        100,
    "Chief Operating Officer":     95,
    "Coo":                         95,
    "Medical Director":            90,
    "Medical Superintendent":      90,
    "Biomedical Engineer":         95,
    "Biomedical Manager":          90,
    "Lab Manager":                 90,
    "Laboratory Manager":          90,
    "Pathologist":                 85,
    "Radiologist":                 80,
    "Head Of Department":          80,
    "Hod":                         80,
    "Department Head":             80,
    "Chairman":                    85,
    "Managing Director":           85,
    "Chief Medical Officer":       90,
    "Cmo":                         90,
    "Hospital Director":           85,
    "Finance Manager":             75,
    "Administrator":               70,
    "Consultant":                  50,
    "Senior Consultant":           55,
    "Specialist":                  45,
    "Registrar":                   35,
    "Director":                    80,
    "Founder":                     80,
    "President":                   80,
}

# Star rating bands for display
def _stars(priority: int) -> str:
    if priority >= 95:  return "★★★★★"
    if priority >= 85:  return "★★★★"
    if priority >= 70:  return "★★★"
    if priority >= 50:  return "★★"
    return "★"


def classify_stakeholders(decision_makers: list[str]) -> list[dict]:
    """
    Takes the raw decision_maker strings from detect_decision_maker()
    (format: "Dr. John Smith (Medical Director)") and returns a priority-sorted
    list with role classification, priority score, and star rating.
    """
    results = []
    for entry in decision_makers:
        # Extract name and title from "Name (Title)" format
        match = re.match(r"^(.*?)\s*\((.+)\)$", entry.strip())
        if not match:
            continue
        name  = match.group(1).strip()
        title = match.group(2).strip()

        # Score: exact match first, then partial substring match
        priority = 0
        for role, score in ROLE_PRIORITY.items():
            if role.lower() == title.lower():
                priority = score
                break
        if priority == 0:
            for role, score in ROLE_PRIORITY.items():
                if role.lower() in title.lower() or title.lower() in role.lower():
                    priority = score
                    break
        if priority == 0:
            priority = 30  # unknown role — still record but low priority

        results.append({
            "name":     name,
            "title":    title,
            "priority": priority,
            "stars":    _stars(priority),
        })

    # Sort highest priority first, then deduplicate by name (keep highest-priority entry)
    results.sort(key=lambda x: x["priority"], reverse=True)
    seen_names: set[str] = set()
    deduped = []
    for r in results:
        if r["name"] not in seen_names:
            seen_names.add(r["name"])
            deduped.append(r)
    return deduped


# ─────────────────────────────────────────────
#  DEPARTMENT HEAD LINKING
# ─────────────────────────────────────────────

# Maps department name → keywords that should appear near a person's name
# to suggest they lead that department.
DEPT_HEAD_SIGNALS: dict[str, list[str]] = {
    "Pathology":         ["pathology", "pathologist", "lab director", "laboratory head"],
    "Radiology":         ["radiology", "radiologist", "imaging head", "radiology head"],
    "Cardiology":        ["cardiology", "cardiologist", "cardiac head"],
    "ICU":               ["icu", "intensive care", "critical care head", "icu head"],
    "Oncology":          ["oncology", "oncologist", "cancer head"],
    "Nephrology":        ["nephrology", "nephrologist", "dialysis head"],
    "Gynecology":        ["gynecology", "gynaecology", "obs head", "obstetrics head"],
    "Orthopedics":       ["orthopedics", "orthopaedics", "orthopedic head"],
    "Neurology":         ["neurology", "neurologist", "neurology head"],
    "Pediatrics":        ["pediatrics", "paediatrics", "pediatric head"],
    "Gastroenterology":  ["gastroenterology", "gastro head"],
    "Emergency":         ["emergency", "casualty head", "a&e head"],
    "Operation Theater": ["operation theater", "ot head", "surgical head"],
    "Laboratory":        ["laboratory", "lab head", "lab manager"],
    "Pharmacy":          ["pharmacy", "pharmacist head", "pharmacy head"],
}

# Product hint per department for the "potential buyer for X" line
DEPT_PRODUCT_HINT: dict[str, str] = {
    "Pathology":         "IVD / CBC Analyzer",
    "Radiology":         "Digital X-Ray / Ultrasound",
    "Cardiology":        "ECG / Echocardiography System",
    "ICU":               "Patient Monitor / Ventilator",
    "Oncology":          "Chemotherapy Infusion Pump",
    "Nephrology":        "Hemodialysis Machine",
    "Gynecology":        "Fetal Monitor / Ultrasound",
    "Orthopedics":       "C-Arm Fluoroscopy",
    "Neurology":         "EEG Machine",
    "Pediatrics":        "Neonatal Incubator / Infant Warmer",
    "Gastroenterology":  "Video Endoscope",
    "Emergency":         "Defibrillator / Crash Cart",
    "Operation Theater": "Surgical Lights / Anesthesia Machine",
    "Laboratory":        "Chemistry Analyzer / PCR Machine",
    "Pharmacy":          "Laminar Flow Cabinet",
}


def link_department_heads(full_text: str, departments: list[str]) -> list[dict]:
    """
    Scan the site text for person-name patterns appearing within ~120 characters
    of a department keyword signal. Returns a list of department→person→product_hint
    associations. Intended as a best-effort heuristic — not 100% accurate.
    """
    text_lower = full_text.lower()
    # Requires a courtesy title prefix (Dr./Prof./Mr./Mrs./Ms.) OR matches
    # exactly 2-3 capitalized words where each word has lowercase chars
    # (rules out pure-uppercase acronyms and long org names).
    name_re = re.compile(
        r"(?:Dr\.?|Prof\.?|Mr\.?|Mrs\.?|Ms\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}"
        r"|[A-Z][a-z]{1,14}(?:\s+[A-Z][a-z]{1,14}){1,2}"
    )
    links = []
    seen_pairs: set[tuple[str, str]] = set()

    for dept in departments:
        signals = DEPT_HEAD_SIGNALS.get(dept, [])
        for signal in signals:
            idx = text_lower.find(signal)
            if idx == -1:
                continue
            # Search window: 120 chars before and after the signal
            window_start = max(0, idx - 120)
            window_end   = min(len(full_text), idx + len(signal) + 120)
            window = full_text[window_start:window_end]

            name_match = name_re.search(window)
            if not name_match:
                continue
            name = name_match.group(0).strip()
            if len(name.split()) < 2:
                continue

            pair = (dept, name)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            links.append({
                "department":    dept,
                "person":        name,
                "product_hint":  DEPT_PRODUCT_HINT.get(dept, "Relevant equipment"),
            })
            break  # one head per department is enough

    return links


# ─────────────────────────────────────────────
#  CONTACT RECOMMENDATION
# ─────────────────────────────────────────────

# Maps email prefix patterns to (reason, confidence) tuples.
# Evaluated in order — first match wins.
EMAIL_PREFIX_RULES: list[tuple[str, str, str]] = [
    ("procurement",  "Direct Sales Opportunity",  "High"),
    ("purchase",     "Direct Sales Opportunity",  "High"),
    ("tender",       "Direct Sales Opportunity",  "High"),
    ("biomedical",   "Technical Decision Maker",  "High"),
    ("lab",          "Laboratory Inquiry",        "High"),
    ("pathology",    "Pathology Department",      "High"),
    ("radiology",    "Radiology Department",      "High"),
    ("ceo",          "Executive Outreach",        "High"),
    ("director",     "Executive Outreach",        "High"),
    ("admin",        "Administrative Contact",    "Medium"),
    ("reception",    "Front Desk — Low Priority", "Low"),
    ("reception",    "Front Desk — Low Priority", "Low"),
    ("info",         "General Inquiry",           "Medium"),
    ("contact",      "General Inquiry",           "Medium"),
    ("hello",        "General Inquiry",           "Low"),
    ("support",      "Support Channel",           "Low"),
]

PHONE_CONTACT_REASON = "Direct Call — Verify Department First"


def recommend_contacts(emails: list[str], phones: list[str]) -> list[dict]:
    """
    Classify each email by its prefix and return a prioritised contact list
    with reason and confidence. Phones are included with a generic reason.
    """
    recommendations = []
    confidence_order = {"High": 0, "Medium": 1, "Low": 2}

    for email in emails:
        prefix = email.split("@")[0].lower()
        reason     = "General Inquiry"
        confidence = "Low"
        for pattern, r, c in EMAIL_PREFIX_RULES:
            if pattern in prefix:
                reason, confidence = r, c
                break
        recommendations.append({
            "contact":    email,
            "type":       "email",
            "reason":     reason,
            "confidence": confidence,
        })

    for phone in phones:
        recommendations.append({
            "contact":    phone,
            "type":       "phone",
            "reason":     PHONE_CONTACT_REASON,
            "confidence": "Medium",
        })

    # Sort High → Medium → Low
    recommendations.sort(key=lambda x: confidence_order.get(x["confidence"], 2))
    return recommendations


# ─────────────────────────────────────────────
#  AI SALES STRATEGY
# ─────────────────────────────────────────────

STRATEGY_MAX_TOKENS = 350  # ~250-word strategy + small buffer


def generate_sales_strategy(
    org_name: str,
    org_type: str,
    departments: list[str],
    stakeholders: list[dict],
    opportunity_matrix: list[dict],
    contacts: dict,
    api_key: str | None,
) -> dict:
    """
    Ask the LLM for a concrete first-approach sales strategy based ONLY on
    structured extracted data. Returns {"strategy": str, "error": str|None}.
    """
    if not api_key:
        return {"strategy": None, "error": "No OpenRouter API key provided."}
    if not departments:
        return {"strategy": None, "error": "Insufficient data for strategy generation."}

    # Build a compact, fact-dense prompt — no waffle, every token counts
    top_depts   = ", ".join(departments[:6])
    top_products = ", ".join(r["opportunity"] for r in opportunity_matrix[:5] if r["priority"] == "High")
    top_contacts = ", ".join(
        f"{s['name']} ({s['title']})" for s in stakeholders[:3]
    ) or "Not identified"
    has_email    = bool(contacts.get("emails"))

    system_prompt = (
        "You are a B2B medical-equipment sales strategist for Apex Steritech. "
        "Generate a concise, actionable first-approach sales strategy. "
        "Use ONLY the facts provided. Do not invent departments, products, or names. "
        "Output 4-6 bullet points. Be specific — name actual departments and products."
    )
    user_prompt = (
        f"Organization: {org_name}\n"
        f"Type: {org_type}\n"
        f"Detected departments: {top_depts}\n"
        f"High-priority products: {top_products or 'see full list'}\n"
        f"Key stakeholders: {top_contacts}\n"
        f"Has contact email: {'Yes' if has_email else 'No'}\n\n"
        "Recommend the best first approach for Apex Steritech."
    )

    try:
        import requests
        response = requests.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_MODEL,
                "max_tokens": STRATEGY_MAX_TOKENS,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        strategy_text = data["choices"][0]["message"]["content"].strip()
        return {"strategy": strategy_text, "error": None}
    except Exception as exc:
        return {"strategy": None, "error": f"Strategy generation failed: {exc}"}


# ─────────────────────────────────────────────
#  CONFIDENCE SCORING
# ─────────────────────────────────────────────

def calculate_classification_confidence(
    org_type: str,
    classification_scores: dict[str, int],
    departments: list[str],
) -> dict:
    """
    Compute a human-readable confidence score for the organization type
    classification. Based on:
      - Gap between top score and second-best (larger gap = more confident)
      - Number of strong department signals that corroborate the type
      - Absolute top score magnitude

    Returns confidence as a percentage + a plain-English reason string.
    """
    if org_type == "Unknown":
        return {
            "confidence_pct": 0,
            "confidence_label": "None",
            "reason": "No meaningful signals detected.",
        }

    sorted_scores = sorted(classification_scores.values(), reverse=True)
    top_score  = sorted_scores[0]
    second     = sorted_scores[1] if len(sorted_scores) > 1 else 0
    gap        = top_score - second

    # --- Gap component (0-50 pts) ---
    gap_component = min(gap * 1.5, 50)

    # --- Absolute signal strength component (0-30 pts) ---
    strength_component = min(top_score * 0.4, 30)

    # --- Corroborating departments (0-20 pts) ---
    # Departments that strongly corroborate "Hospital" type
    hospital_corroborators = {"ICU", "Operation Theater", "Emergency", "Blood Bank",
                               "Radiology", "Pathology", "CSSD"}
    lab_corroborators      = {"Pathology", "Laboratory", "Microbiology"}
    college_corroborators  = {"Pathology", "Radiology", "Neurology", "Cardiology"}

    corroborator_map = {
        "Hospital":              hospital_corroborators,
        "Diagnostic Laboratory": lab_corroborators,
        "Medical College":       college_corroborators,
    }
    corroborators   = corroborator_map.get(org_type, set())
    matching_depts  = len(set(departments) & corroborators)
    dept_component  = min(matching_depts * 5, 20)

    raw_confidence  = gap_component + strength_component + dept_component
    confidence_pct  = min(round(raw_confidence), 99)  # cap at 99 — never claim 100%

    # Label
    if confidence_pct >= 85:   label = "Very High"
    elif confidence_pct >= 70: label = "High"
    elif confidence_pct >= 50: label = "Medium"
    elif confidence_pct >= 30: label = "Low"
    else:                      label = "Very Low"

    # Reason — build from actual detected signals
    supporting_depts = sorted(set(departments) & corroborators)
    if supporting_depts:
        dept_str = ", ".join(supporting_depts[:5])
        reason = (
            f"Classified as {org_type} based on keyword signal strength of {top_score} "
            f"(vs. {second} for next best). Supporting departments: {dept_str}."
        )
    else:
        reason = (
            f"Classified as {org_type} based on keyword signal strength of {top_score} "
            f"(vs. {second} for next best). No strong department corroboration found."
        )

    return {
        "confidence_pct":   confidence_pct,
        "confidence_label": label,
        "reason":           reason,
    }


# ─────────────────────────────────────────────
#  INTELLIGENCE PROFILE BUILDER
# ─────────────────────────────────────────────

def _guess_org_name(pages: list[dict]) -> str:
    """Best-effort organization name from the seed page's title or first heading."""
    if not pages:
        return "Unknown Organization"
    first = pages[0]
    title = (first.get("page_title") or "").strip()
    if title:
        # Strip common separators that append site taglines, e.g. "Home | Acme Hospital"
        for sep in ["|", "-", "–", "::"]:
            if sep in title:
                parts = [p.strip() for p in title.split(sep) if p.strip()]
                if parts:
                    title = max(parts, key=len)
                break
        return title
    headings = first.get("headings", [])
    if headings:
        return headings[0]["text"].strip()
    return "Unknown Organization"


def build_intelligence_profile(pages: list[dict], openrouter_api_key: str | None = None) -> dict:
    """
    Run all analytical passes over aggregated full-site text and return
    a structured intelligence profile: org type, departments, products,
    opportunity score, lead qualification, opportunity matrix, sales
    checklist, stakeholder classification, department head linking,
    contact recommendations, AI sales strategy, and confidence scores.
    """
    full_text = " ".join(
        " ".join(p.get("content_blocks", []))
        + " " + " ".join(h["text"] for h in p.get("headings", []))
        + " " + p.get("page_title", "")
        for p in pages
    )

    all_emails    = sorted({e  for p in pages for e  in p["contacts"]["emails"]})
    all_phones    = sorted({ph for p in pages for ph in p["contacts"]["phones"]})
    all_page_urls = [p["url"] for p in pages]
    aggregate_contacts = {"emails": all_emails, "phones": all_phones}

    org_name = _guess_org_name(pages)

    # ── Core classification ───────────────────
    classification = classify_organization(full_text)
    org_type       = classification["organization_type"]
    departments    = detect_departments(full_text)
    products       = recommend_products(departments)

    # ── Scoring ──────────────────────────────
    opportunity = calculate_opportunity_score(
        org_type, departments, aggregate_contacts, all_page_urls
    )
    lead = calculate_lead_score(
        full_text, org_type, departments, aggregate_contacts, all_page_urls
    )

    # ── Matrices & checklists ────────────────
    opportunity_matrix = build_opportunity_matrix(departments)
    checklist = build_sales_checklist(
        org_type, departments, aggregate_contacts, all_page_urls, lead
    )

    # ── Stakeholder classification (Task 1) ──
    stakeholders = classify_stakeholders(lead.get("decision_makers", []))

    # ── Department head linking (Task 2) ─────
    dept_heads = link_department_heads(full_text, departments)

    # ── Contact recommendations (Task 3) ─────
    contact_recommendations = recommend_contacts(all_emails, all_phones)

    # ── Classification confidence (Task 5) ───
    confidence = calculate_classification_confidence(
        org_type, classification["classification_scores"], departments
    )

    # ── AI outputs (Task 4 + email) ──────────
    email_result = generate_outreach_email(
        org_name, org_type, departments, products, aggregate_contacts, openrouter_api_key
    )
    strategy_result = generate_sales_strategy(
        org_name, org_type, departments, stakeholders,
        opportunity_matrix, aggregate_contacts, openrouter_api_key
    )

    return {
        "organization_name":       org_name,
        "organization_type":       org_type,
        "classification_scores":   classification["classification_scores"],
        "classification_confidence": confidence,
        "departments":             departments,
        "recommended_products":    products,
        "opportunity_score":       opportunity["score"],
        "score_breakdown":         opportunity["breakdown"],
        "lead_qualification":      lead,
        "stakeholders":            stakeholders,
        "department_heads":        dept_heads,
        "opportunity_matrix":      opportunity_matrix,
        "contact_recommendations": contact_recommendations,
        "sales_checklist":         checklist,
        "sales_strategy":          strategy_result["strategy"],
        "sales_strategy_error":    strategy_result["error"],
        "outreach_email":          email_result["email"],
        "outreach_email_error":    email_result["error"],
    }


# ─────────────────────────────────────────────
#  CORE CRAWLER
# ─────────────────────────────────────────────

def crawl(start_url: str, max_pages: int, delay: float, verbose: bool) -> list:
    logger = logging.getLogger("WebProfiler")
    target_domain = urlparse(start_url).netloc

    logger.info(f"Starting crawl → {start_url}")
    logger.info(f"Domain scope: {target_domain} | Max pages: {max_pages} | Delay: {delay}s")

    queue: list[tuple[int, str]] = [(-score_url(start_url), start_url)]
    visited: set[str] = set()
    results: list[dict] = []

    def normalize(url: str) -> str:
        return url.split("#")[0].rstrip("/")

    with sync_playwright() as pw:
        logger.info("Launching headless Chromium...")
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        while queue and len(visited) < max_pages:
            queue.sort(key=lambda x: x[0])
            _, current_url = queue.pop(0)
            current_url = normalize(current_url)

            if current_url in visited:
                continue
            visited.add(current_url)

            logger.info(f"[{len(visited)}/{max_pages}] Scraping: {current_url}")

            try:
                page.goto(current_url, wait_until="networkidle", timeout=60000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(0.5)
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(delay)

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")

                contacts = extract_contacts(soup, current_url)
                structured = extract_structured_data(soup)
                meta = extract_metadata(soup)
                headings = extract_headings(soup)
                content = extract_main_content(BeautifulSoup(html, "html.parser"))
                images = extract_images(soup, current_url)
                tables = extract_tables(BeautifulSoup(html, "html.parser"))
                navigation = extract_navigation(soup, current_url)

                social_profiles = contacts.pop("social_profiles", {})

                page_record = {
                    "url": current_url,
                    "scraped_at": datetime.utcnow().isoformat() + "Z",
                    "page_title": (page.title() or "").strip(),
                    "meta": meta,
                    "contacts": contacts,
                    "social_profiles": social_profiles,
                    "structured_data": structured,
                    "navigation": navigation,
                    "headings": headings,
                    "content_blocks": content,
                    "tables": tables,
                    "images": images,
                }

                results.append(page_record)
                logger.debug(
                    f"  → emails={len(contacts['emails'])} | "
                    f"phones={len(contacts['phones'])} | "
                    f"blocks={len(content)} | tables={len(tables)}"
                )

                for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
                    href = a["href"].strip()
                    if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                        continue
                    abs_url = normalize(urljoin(current_url, href))
                    parsed = urlparse(abs_url)
                    if (
                        parsed.scheme in ("http", "https")
                        and parsed.netloc == target_domain
                        and abs_url not in visited
                        and not any(abs_url == u for _, u in queue)
                    ):
                        priority = -score_url(abs_url)
                        queue.append((priority, abs_url))

            except Exception as exc:
                logger.warning(f"  Skipped {current_url}: {exc}")
                continue

        browser.close()

    logger.info(f"Crawl complete. {len(results)} pages scraped.")
    return results


# ─────────────────────────────────────────────
#  OUTPUT BUILDER
# ─────────────────────────────────────────────

def build_output(start_url: str, pages: list, openrouter_api_key: str | None = None) -> dict:
    """Assemble the final report envelope with aggregate data and intelligence profile."""
    all_emails = sorted({e for p in pages for e in p["contacts"]["emails"]})
    all_phones = sorted({ph for p in pages for ph in p["contacts"]["phones"]})
    all_socials: dict = {}
    for p in pages:
        for platform, links in p.get("social_profiles", {}).items():
            all_socials.setdefault(platform, [])
            for link in links:
                if link not in all_socials[platform]:
                    all_socials[platform].append(link)

    intelligence = build_intelligence_profile(pages, openrouter_api_key)

    aggregate_contacts = {"emails": all_emails, "phones": all_phones}
    executive_report_text = format_executive_report(
        intelligence.get("organization_name"),
        intelligence,
        aggregate_contacts,
        intelligence.get("sales_checklist", []),
    )

    return {
        "report": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "seed_url": start_url,
            "pages_scraped": len(pages),
            "aggregate": {
                "unique_emails": all_emails,
                "unique_phones": all_phones,
                "social_profiles": all_socials,
            },
            "intelligence": intelligence,
            "executive_report_text": executive_report_text,
        },
        "pages": pages,
    }


# ─────────────────────────────────────────────
#  SQLITE PERSISTENCE (STRETCH GOAL)
# ─────────────────────────────────────────────

DEFAULT_DB_PATH = "webprofiler.db"


def init_database(db_path: str = DEFAULT_DB_PATH) -> None:
    """Create the leads table if it doesn't already exist."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_name TEXT,
            website TEXT,
            lead_score INTEGER,
            lead_grade TEXT,
            city TEXT,
            organization_type TEXT,
            num_departments INTEGER,
            contact_email TEXT,
            last_crawl_date TEXT,
            UNIQUE(website)
        )
        """
    )
    conn.commit()
    conn.close()


def save_lead_to_database(
    output: dict,
    city: str | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """
    Upsert the analyzed organization into the local SQLite database.
    Existing rows for the same website are updated (last_crawl_date refreshed).
    """
    init_database(db_path)

    report = output["report"]
    intel = report["intelligence"]
    lead = intel.get("lead_qualification", {})
    contacts = report["aggregate"]

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO leads (
            organization_name, website, lead_score, lead_grade, city,
            organization_type, num_departments, contact_email, last_crawl_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(website) DO UPDATE SET
            organization_name=excluded.organization_name,
            lead_score=excluded.lead_score,
            lead_grade=excluded.lead_grade,
            city=excluded.city,
            organization_type=excluded.organization_type,
            num_departments=excluded.num_departments,
            contact_email=excluded.contact_email,
            last_crawl_date=excluded.last_crawl_date
        """,
        (
            intel.get("organization_name"),
            report["seed_url"],
            lead.get("score", 0),
            lead.get("grade", "D"),
            city,
            intel.get("organization_type"),
            len(intel.get("departments", [])),
            contacts["unique_emails"][0] if contacts.get("unique_emails") else None,
            report["generated_at"],
        ),
    )
    conn.commit()
    conn.close()