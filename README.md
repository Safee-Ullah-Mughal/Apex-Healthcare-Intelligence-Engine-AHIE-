
# Apex Healtcare Intelligence Engine (AHIE) — B2B Medical Sales Intelligence Platform

> A professional-grade web scraper and sales intelligence engine purpose-built
> for medical equipment distributors. Crawls any healthcare organization's
> website, extracts structured data, classifies the organization, detects
> clinical departments, identifies decision makers, scores lead quality, and
> generates AI-powered sales strategy — all from a single command.

Built for **Apex Steritech** and similar B2B medical equipment sales teams who
need to prioritize hundreds of hospital leads without manual research.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Setup & Installation](#setup--installation)
3. [Quick Start](#quick-start)
4. [CLI Reference](#cli-reference)
5. [How It Works — Scraping Layer](#how-it-works--scraping-layer)
6. [How It Works — Intelligence Layer](#how-it-works--intelligence-layer)
   - [Organization Classification](#1-organization-classification)
   - [Department Detection](#2-department-detection)
   - [Product Recommendations](#3-product-recommendations)
   - [Opportunity Scoring](#4-opportunity-scoring-generic)
   - [Lead Qualification Engine](#5-lead-qualification-engine)
   - [Product Opportunity Matrix](#6-product-opportunity-matrix)
   - [Stakeholder Classification](#7-stakeholder-classification)
   - [Department Head Linking](#8-department-head-linking)
   - [Contact Recommendations](#9-contact-recommendations)
   - [Sales Readiness Checklist](#10-sales-readiness-checklist)
   - [AI Outreach Email](#11-ai-outreach-email)
   - [AI Sales Strategy](#12-ai-sales-strategy)
   - [Classification Confidence](#13-classification-confidence)
7. [Executive Report](#executive-report)
8. [SQLite Lead Database](#sqlite-lead-database)
9. [Output JSON Schema](#output-json-schema)
10. [OpenRouter API & Token Budget](#openrouter-api--token-budget)
11. [Customization Guide](#customization-guide)
12. [Module Map](#module-map)
13. [Limitations & Known Caveats](#limitations--known-caveats)

---

## Architecture Overview

WebProfiler is split into two files that work together:

```
scraper.py          (561 lines)   — Crawling & raw extraction
intelligence.py     (1544 lines)  — All analytical & AI logic
```

This separation means you can:
- Swap the scraper (e.g. switch from Playwright to Scrapy) without touching the analysis layer
- Test or run the intelligence layer on any data source, not just live websites
- Add new analytical modules to `intelligence.py` without affecting the crawl pipeline

**Data flow:**

```
URL
 │
 ▼
scraper.py: crawl()
 │  Playwright headless Chromium
 │  Domain-locked crawl queue (priority-sorted)
 │  Per-page: contacts, emails, phones, socials,
 │            structured data, metadata, headings,
 │            content blocks, tables, images, navigation
 │
 ▼
List of page dicts
 │
 ▼
intelligence.py: build_intelligence_profile()
 │  Organization classification (7 types)
 │  Department detection (25 departments)
 │  Product recommendations
 │  Opportunity score (0-100)
 │  Lead qualification score + grade (A+ to D)
 │  Stakeholder classification (star-rated)
 │  Department head linking
 │  Contact recommendations (High/Medium/Low)
 │  Sales readiness checklist
 │  Classification confidence (% + reason)
 │  AI outreach email (OpenRouter)
 │  AI sales strategy (OpenRouter)
 │
 ▼
JSON report + plain-text executive summary + SQLite row
```

---

## Setup & Installation

**Requirements:** Python 3.10+

```bash
pip install -r requirements.txt
playwright install chromium
```

**requirements.txt:**
```
playwright>=1.44.0
beautifulsoup4>=4.12.0
lxml>=5.2.0
requests>=2.31.0
```

**OpenRouter API key** (optional — only needed for AI email + strategy):

On Linux / Mac:
```bash
export OPENROUTER_API_KEY="sk-or-your-key-here"
```

On Windows PowerShell:
```powershell
$env:OPENROUTER_API_KEY="sk-or-your-key-here"
```

On Windows CMD:
```cmd
set OPENROUTER_API_KEY=sk-or-your-key-here
```

Both files (`scraper.py` and `intelligence.py`) must be in the **same directory**.

---

## Quick Start

```bash
# Minimal — crawl 10 pages, save JSON
python scraper.py https://example-hospital.com

# Standard sales workflow
python scraper.py https://example-hospital.com \
  --max-pages 20 \
  --output hospital_report.json \
  --exec-report hospital_summary.txt \
  --save-db --city "Lahore"

# With AI features enabled
python scraper.py https://example-hospital.com \
  --max-pages 20 \
  --output report.json \
  --exec-report summary.txt \
  --save-db --city "Karachi" \
  --openrouter-key "sk-or-..."

# Skip AI to conserve daily token budget
python scraper.py https://example-hospital.com --no-email

# Debug mode — see every step
python scraper.py https://example-hospital.com --verbose
```

**What you get after a run:**

| Output | Description |
|--------|-------------|
| `hospital_report.json` | Full structured data — every page, all intelligence fields |
| `hospital_summary.txt` | Sectioned plain-text executive report — readable in 2 minutes |
| `webprofiler.db` | SQLite database row — accumulates across all your runs |
| Terminal output | Live progress + final summary (org name, lead grade, score) |

---

## CLI Reference

| Flag | Default | Description |
|------|---------|-------------|
| `url` | *(required)* | Seed URL to start crawling from |
| `--max-pages` | `10` | Maximum pages to crawl per run |
| `--output` | `scraped_output.json` | JSON output file path |
| `--delay` | `1.0` | Seconds to wait between page loads (politeness) |
| `--verbose` | off | Enable debug-level logging |
| `--openrouter-key` | `None` | OpenRouter API key (overrides `OPENROUTER_API_KEY` env var) |
| `--no-email` | off | Skip AI email + strategy generation (saves tokens) |
| `--save-db` | off | Persist this lead into the local SQLite database |
| `--city` | `None` | City label stored alongside the lead in the database |
| `--db-path` | `webprofiler.db` | Path to the SQLite database file |
| `--exec-report` | `None` | Path to also save the executive summary as a `.txt` file |

---

## How It Works — Scraping Layer

**File:** `scraper.py`

### Crawl Engine

The crawler uses **Playwright** (headless Chromium) which means it executes JavaScript, handles lazy-loaded content, and renders SPAs — something `requests` + `BeautifulSoup` alone cannot do.

Key behaviours:
- **Domain-locked**: only follows links within the seed domain. External links are ignored.
- **Priority queue**: URLs are scored before entering the queue. Pages with keywords like `contact`, `about`, `team`, `staff`, `directory`, `services`, `leadership` in their path are crawled first — these tend to contain the most useful data.
- **Lazy-load trigger**: scrolls to the bottom of each page before extracting, forcing deferred images and widgets to render.
- **Polite crawling**: configurable delay between requests (`--delay`). Default is 1 second.
- **URL normalisation**: strips `#fragments` and trailing slashes before deduplication to avoid crawling the same page twice.

### Per-Page Extraction

For each page visited, the following signals are extracted:

| Signal | Method | Details |
|--------|--------|---------|
| **Emails** | Regex + `mailto:` links | RFC-pattern validated, lowercased, deduplicated |
| **Phones** | Regex + `tel:` links | International format, 7–15 digits enforced, year-pattern filtered |
| **Social profiles** | Domain matching on all `<a>` hrefs | 17 platforms: LinkedIn, Twitter/X, Facebook, Instagram, YouTube, GitHub, ResearchGate, ORCID, Telegram, WhatsApp, TikTok, Pinterest, Reddit, Medium, and more |
| **Structured data** | `<script type="application/ld+json">` + `<meta>` | JSON-LD schemas, OpenGraph tags, Twitter Card meta |
| **Page metadata** | All `<meta>` tags | description, keywords, author, robots, etc. |
| **Navigation** | All `<nav>` anchor tags | Label + absolute URL pairs |
| **Headings** | H1–H4 in document order | Level + text |
| **Content blocks** | Semantic container heuristic | Prefers `<main>`, `<article>`, content-classed divs; strips nav/footer/sidebar/scripts before extracting `<p>`, `<li>`, `<td>`, `<blockquote>`; filters boilerplate (copyright strings, very short text) |
| **Tables** | All `<table>` elements | Parsed into `{headers, rows}` JSON; rows as dicts when headers present |
| **Images** | All `<img>` tags | Only images with meaningful alt text (> 3 chars); src resolved to absolute URL |

---

## How It Works — Intelligence Layer

**File:** `intelligence.py`

All analysis runs after crawling completes, inside `build_intelligence_profile()`. The full site text is assembled by concatenating content blocks, headings, and page titles from all scraped pages before any analysis begins — this maximises signal for keyword-based detection.

---

### 1. Organization Classification

**Function:** `classify_organization(full_text)`

Scores the full aggregated site text against weighted keyword signals for each of **7 healthcare organization types**:

| Type | Example high-weight signals |
|------|-----------------------------|
| Hospital | "hospital" (+10), "bed capacity" (+8), "inpatient" (+8), "operation theater" (+7) |
| Diagnostic Laboratory | "diagnostic laboratory" (+12), "sample collection" (+8), "histopathology" (+7) |
| Medical Equipment Distributor | "medical equipment" (+10), "authorized dealer" (+8), "spare parts" (+7) |
| Pharmaceutical Company | "pharmaceutical" (+10), "manufacturing plant" (+8), "gmp" (+7) |
| Medical College | "medical college" (+12), "mbbs" (+10), "faculty of medicine" (+9) |
| Clinic | "clinic" (+9), "polyclinic" (+9), "specialist clinic" (+8) |
| NGO | "ngo" (+10), "non-governmental" (+10), "free medical" (+8) |

The type with the highest total score wins. If the top score is below 6, the result is `Unknown`. The full score breakdown for all 7 types is included in the output for transparency.

---

### 2. Department Detection

**Function:** `detect_departments(full_text)`

Scans site text for **25 clinical departments** using keyword alias lists. Each department maps to multiple synonyms and abbreviations:

```
Cardiology     → "cardiology", "cardiac", "heart", "ecg", "cathlab"
Radiology      → "radiology", "x-ray", "mri", "ct scan", "ultrasound"
Pathology      → "pathology", "histopathology", "cytology", "biopsy"
ICU            → "icu", "intensive care", "critical care", "ccu"
Operation Theater → "operation theater", "ot ", "surgical suite", "surgery"
...and 20 more
```

Full department list: Cardiology, Radiology, Pathology, Emergency, ICU, CSSD, Operation Theater, Blood Bank, Laboratory, Pharmacy, Microbiology, Nephrology, Oncology, Gynecology, Orthopedics, Pediatrics, Neurology, Dermatology, Ophthalmology, ENT, Psychiatry, Physiotherapy, Dental, Gastroenterology, Urology.

---

### 3. Product Recommendations

**Function:** `recommend_products(departments)`

Each detected department maps to a curated list of relevant biomedical equipment in `DEPARTMENT_PRODUCTS`. Products are aggregated across all detected departments and deduplicated.

**Examples:**

| Department | Recommended Products |
|------------|---------------------|
| Pathology | CBC Analyzer, Chemistry Analyzer, Microscope, IVD Consumables, Centrifuge |
| ICU | Patient Monitor, Mechanical Ventilator, Infusion Pump, Syringe Pump, ECG Machine |
| Radiology | Digital X-Ray System, MRI Scanner, CT Scanner, Ultrasound Machine, PACS System |
| Operation Theater | Surgical Lights, Operating Table, Anesthesia Machine, Electrosurgical Unit |

> **Customization note:** `DEPARTMENT_PRODUCTS` is a plain Python dictionary. Replace the generic product names with Apex Steritech's actual catalog items and the entire recommendation + opportunity matrix pipeline updates automatically.

---

### 4. Opportunity Scoring (Generic)

**Function:** `calculate_opportunity_score(org_type, departments, contacts, all_page_urls)`

A general-purpose, explainable score normalized to 100. Separate from the lead score — this reflects overall commercial potential regardless of org type.

| Factor | Points |
|--------|--------|
| Organization type base score | up to 30 (Hospital=30, Medical College=20, Diagnostic Lab=20, Clinic=15, NGO/Pharma=10) |
| Department bonuses (capped at 40 total) | ICU=20, Operation Theater=18, Laboratory=15, Blood Bank/Radiology/Pathology=12 each, ... |
| Has contact email | +10 |
| Has procurement/tender page (URL detected) | +20 |

---

### 5. Lead Qualification Engine

**Functions:** `calculate_lead_score()`, `grade_lead()`, `detect_private_hospital()`, `detect_decision_maker()`

The sales-rule scoring model — reflects business priority, not just data completeness. Separate from the opportunity score.

**Scoring rules:**

| Parameter | Points | Detection Method |
|-----------|--------|-----------------|
| Private Hospital | +20 | Keywords: "private hospital", "pvt ltd", "trust hospital", "privately owned" |
| Large Hospital (20+ departments) | +20 | Count of detected departments ≥ 20 |
| Has Pathology | +15 | "Pathology" in detected departments |
| Has ICU | +10 | "ICU" in detected departments |
| Has Cath Lab | +10 | "cath lab", "cathlab", "catheterization" in text |
| Has Radiology | +10 | "Radiology" in detected departments |
| Has Contact Email | +5 | At least one email extracted |
| Has Procurement/Vendor Page | +10 | URL contains: procurement, tender, rfq, quotation, bid, purchase |
| Has Decision Maker (bonus) | +5 | Named person + leadership title detected |

**Lead Grade Bands:**

| Score | Grade | Recommended Action |
|-------|-------|--------------------|
| 90–100 | A+ | Visit within 7 days |
| 75–89 | A | Visit within 14 days |
| 55–74 | B | Follow up by phone/email within 30 days |
| 35–54 | C | Add to nurture campaign |
| 0–34 | D | Low priority — monitor only |

**Decision Maker Detection:** Scans for leadership titles (CEO, Medical Director, Medical Superintendent, Chairman, CMO, Procurement Manager, etc.) and looks for a capitalized name within the same sentence. Returns name + title pairs, e.g. `"Dr. Ahmed Khan (Medical Director)"`.

---

### 6. Product Opportunity Matrix

**Function:** `build_opportunity_matrix(departments)`

Converts the flat product list into a structured, priority-sorted table:

| Department | Opportunity | Priority |
|------------|-------------|----------|
| ICU | Patient Monitor | High |
| ICU | Mechanical Ventilator | High |
| Pathology | CBC Analyzer | High |
| Radiology | Ultrasound Machine | Medium |
| Gynecology | Fetal Monitor | Low |

Priority tiers are defined in `DEPARTMENT_PRIORITY`. High = large deal size / urgent replacement cycle. Sorted High → Medium → Low. Designed to be re-mapped onto a specific vendor catalog later.

---

### 7. Stakeholder Classification

**Function:** `classify_stakeholders(decision_makers)`

Takes raw decision-maker strings from the detection step and assigns each person a **sales priority score** and **star rating** based on their role title.

```
ROLE_PRIORITY = {
    "Procurement Manager":   100,   ★★★★★
    "Chief Executive Officer": 100, ★★★★★
    "Chief Operating Officer": 95,  ★★★★★
    "Biomedical Engineer":    95,   ★★★★★
    "Medical Director":       90,   ★★★★
    "Medical Superintendent": 90,   ★★★★
    "Lab Manager":            90,   ★★★★
    "Pathologist":            85,   ★★★★
    "Radiologist":            80,   ★★★
    "Consultant":             50,   ★★
    ...
}
```

Star rating bands: ★★★★★ (≥95), ★★★★ (≥85), ★★★ (≥70), ★★ (≥50), ★ (<50).

Output is sorted highest priority first. Duplicates (same name detected via multiple title matches) are deduplicated, keeping the highest-priority entry.

---

### 8. Department Head Linking

**Function:** `link_department_heads(full_text, departments)`

Best-effort heuristic that associates a named person with a clinical department when their name appears within ~120 characters of a department-specific keyword.

**Example output:**
```
Pathology → Dr. Ahmed Khan → Potential buyer for IVD / CBC Analyzer
Radiology → Dr. Sara Malik → Potential buyer for Digital X-Ray / Ultrasound
ICU       → Dr. Bilal Raza → Potential buyer for Patient Monitor / Ventilator
```

Requires a courtesy title prefix (Dr., Prof., Mr., Mrs., Ms.) to reduce false positives from matching organization names as "persons". One head per department maximum.

> This is explicitly a best-effort feature — it will miss cases where names appear without titles or far from department mentions. It is a signal, not a verified fact.

---

### 9. Contact Recommendations

**Function:** `recommend_contacts(emails, phones)`

Classifies every extracted email by its prefix against a priority-ordered rule table and returns a ranked list with reason and confidence:

| Email Prefix Pattern | Reason | Confidence |
|---------------------|--------|-----------|
| procurement, purchase, tender | Direct Sales Opportunity | High |
| biomedical | Technical Decision Maker | High |
| lab, pathology, radiology | Department-specific | High |
| ceo, director | Executive Outreach | High |
| admin | Administrative Contact | Medium |
| info, contact | General Inquiry | Medium |
| reception, hello, support | Front Desk / Low Priority | Low |

Phones receive "Direct Call — Verify Department First" at Medium confidence. Output sorted High → Medium → Low.

---

### 10. Sales Readiness Checklist

**Function:** `build_sales_checklist(...)`

Seven automatic pass/fail checks that give a salesperson a quick pre-visit overview:

```
✔ Website Available
✔ Contact Email Found
✔ Phone Found
✔ Decision Maker Found
✖ Procurement Page Present
✔ Multiple Clinical Departments
✔ Pathology Lab Present
```

---

### 11. AI Outreach Email

**Function:** `generate_outreach_email(...)`

Generates a short, professional B2B introductory email using **only** the extracted facts. Rules enforced via system prompt:

- Mentions exactly **one** detected department
- Mentions exactly **one** specific recommended product
- Never invents facts, names, products, or services
- Under 200 words
- Ends with a meeting request

Uses **OpenRouter** (`meta-llama/llama-3.1-8b-instruct:free` by default). Capped at **280 output tokens** to stay within the free-tier daily budget. Skipped gracefully (with an error message in the JSON) if no API key is provided or `--no-email` is passed.

---

### 12. AI Sales Strategy

**Function:** `generate_sales_strategy(...)`

Asks the LLM for a concrete, actionable first-approach strategy based only on the structured data. The prompt passes:
- Organization name and type
- Top detected departments
- High-priority products from the opportunity matrix
- Top-ranked stakeholders (name + title)
- Whether a contact email exists

Output is 4–6 bullet points, specific to the actual departments and products detected. Capped at **350 output tokens**.

**Example output:**
```
• Start with the Pathology department — CBC Analyzer and IVD consumables
  are high-margin, high-urgency items for their diagnostic workflow.
• Request a meeting with Dr. Ahmed Khan (Medical Director) or the
  Lab Manager — both have direct procurement influence.
• Lead with a reagent compatibility discussion rather than a product pitch.
• Follow up with the ICU team on Patient Monitor replacement cycle.
• Contact procurement@maxhealth.com first — highest-confidence entry point.
```

---

### 13. Classification Confidence

**Function:** `calculate_classification_confidence(org_type, classification_scores, departments)`

Produces an explainable confidence percentage for the organization type classification. Three components:

| Component | Max Points | Logic |
|-----------|-----------|-------|
| Signal gap (top score vs. second-best) | 50 | Larger gap = more confident |
| Absolute signal strength | 30 | Higher raw score = more confident |
| Corroborating departments | 20 | Departments that strongly support the classified type |

Normalized to a percentage, capped at 99% (never claims certainty). Includes a plain-English reason string citing actual scores and supporting departments.

**Example output:**
```
Hospital Type
Confidence: 87% (High)
Reason: Classified as Hospital based on keyword signal strength of 62
(vs. 14 for next best). Supporting departments: Emergency, ICU,
Operation Theater, Pathology, Radiology.
```

---

## Executive Report

Generated by `format_executive_report()` and saved via `--exec-report summary.txt`.

A plain-text, sectioned report a sales manager can read in under two minutes:

```
========================================
EXECUTIVE SUMMARY
========================================
Organization     : Max Health Private Hospital
Type             : Hospital
Type Confidence  : 87% (High)
Confidence Reason: Classified as Hospital based on signal strength...
Departments      : 12 detected
Lead Grade       : A+ (Score: 95/100)
Next Action      : Visit within 7 days

========================================
KEY CONTACTS & RECOMMENDATIONS
========================================
  Contact                             Type   Reason                         Confidence
  procurement@maxhealth.com           email  Direct Sales Opportunity       High
  info@maxhealth.com                  email  General Inquiry                Medium
  +92-51-1234567                      phone  Direct Call — Verify Dept First Medium

========================================
DECISION MAKERS & STAKEHOLDERS
========================================
  ★★★★★  Sara Ali       — Procurement Manager  (Priority: 100)
  ★★★★   Ahmed Khan     — Medical Director     (Priority: 90)

========================================
DEPARTMENT HEADS
========================================
  Pathology
    ↓  Dr. Bilal Raza
    ↓  Potential buyer for IVD / CBC Analyzer

========================================
DEPARTMENTS
========================================
  Blood Bank, Cardiology, Emergency, ICU, Laboratory, Oncology...

========================================
SALES OPPORTUNITIES
========================================
  [High  ] ICU                  Patient Monitor
  [High  ] Pathology            CBC Analyzer
  [Medium] Radiology            Ultrasound Machine
  ...

========================================
AI SALES STRATEGY
========================================
  • Start with Pathology department...
  • Request meeting with Procurement Manager...

========================================
LEAD SCORE
========================================
  Score : 95/100
  Grade : A+
  + Private Hospital               +20
  + Has Pathology                  +15
  + Has Icu                        +10
  + Has Cath Lab                   +10
  + Has Radiology                  +10
  + Has Contact Email               +5
  + Has Decision Maker              +5

========================================
SALES READINESS CHECKLIST
========================================
  ✔ Website Available
  ✔ Contact Email Found
  ✔ Phone Found
  ✔ Decision Maker Found
  ✖ Procurement Page Present
  ✔ Multiple Clinical Departments
  ✔ Pathology Lab Present

========================================
RECOMMENDED NEXT ACTION
========================================
  Visit within 7 days
```

---

## SQLite Lead Database

Pass `--save-db` to persist each analyzed organization into a local SQLite database (default: `webprofiler.db`). Every re-crawl of the same website **updates** the existing row rather than creating a duplicate.

**Schema — `leads` table:**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Auto-increment primary key |
| organization_name | TEXT | Detected from page title / first heading |
| website | TEXT (UNIQUE) | Seed URL — upsert key |
| lead_score | INTEGER | 0–100 |
| lead_grade | TEXT | A+, A, B, C, D |
| city | TEXT | Passed via `--city` flag |
| organization_type | TEXT | Hospital, Clinic, etc. |
| num_departments | INTEGER | Count of detected departments |
| contact_email | TEXT | First email found |
| last_crawl_date | TEXT | ISO timestamp of most recent run |

**Querying your accumulated leads:**

```python
import sqlite3
conn = sqlite3.connect("webprofiler.db")

# All leads ranked by score
for row in conn.execute(
    "SELECT organization_name, lead_score, lead_grade, city, organization_type "
    "FROM leads ORDER BY lead_score DESC"
):
    print(row)

# A+ and A leads in a specific city
for row in conn.execute(
    "SELECT organization_name, lead_score, contact_email FROM leads "
    "WHERE lead_grade IN ('A+', 'A') AND city = ?",
    ("Rawalpindi",)
):
    print(row)

# Hospitals with pathology (num_departments proxy)
for row in conn.execute(
    "SELECT organization_name, num_departments, lead_score FROM leads "
    "WHERE organization_type = 'Hospital' AND num_departments >= 5 "
    "ORDER BY lead_score DESC"
):
    print(row)
```

Once you have hundreds of leads, you can sort by score, filter by city or type, and generate regional sales priority lists directly from this database.

---

## Output JSON Schema

```json
{
  "report": {
    "generated_at": "2026-07-01T00:00:00Z",
    "seed_url": "https://example-hospital.com",
    "pages_scraped": 15,
    "aggregate": {
      "unique_emails": ["procurement@example.com", "info@example.com"],
      "unique_phones": ["+92-51-1234567"],
      "social_profiles": { "linkedin": ["https://linkedin.com/..."] }
    },
    "intelligence": {
      "organization_name": "Max Health Private Hospital",
      "organization_type": "Hospital",
      "classification_scores": { "Hospital": 62, "Clinic": 9, "NGO": 0 },
      "classification_confidence": {
        "confidence_pct": 87,
        "confidence_label": "High",
        "reason": "Classified as Hospital based on..."
      },
      "departments": ["Cardiology", "ICU", "Pathology", "Radiology"],
      "recommended_products": ["CBC Analyzer", "Patient Monitor", "..."],
      "opportunity_score": 78,
      "score_breakdown": { "organization_type": 30, "departments": 40 },
      "lead_qualification": {
        "score": 95,
        "grade": "A+",
        "recommended_action": "Visit within 7 days",
        "breakdown": { "private_hospital": 20, "has_pathology": 15 },
        "decision_makers": ["Dr. Ahmed Khan (Medical Director)"],
        "is_private_hospital": true,
        "is_large_hospital": false
      },
      "stakeholders": [
        { "name": "Sara Ali", "title": "Procurement Manager",
          "priority": 100, "stars": "★★★★★" }
      ],
      "department_heads": [
        { "department": "Pathology", "person": "Dr. Ahmed Khan",
          "product_hint": "IVD / CBC Analyzer" }
      ],
      "opportunity_matrix": [
        { "department": "ICU", "opportunity": "Patient Monitor", "priority": "High" }
      ],
      "contact_recommendations": [
        { "contact": "procurement@example.com", "type": "email",
          "reason": "Direct Sales Opportunity", "confidence": "High" }
      ],
      "sales_checklist": [
        { "label": "Website Available", "passed": true },
        { "label": "Procurement Page Present", "passed": false }
      ],
      "sales_strategy": "• Start with Pathology department...",
      "sales_strategy_error": null,
      "outreach_email": "Dear Team, ...",
      "outreach_email_error": null
    },
    "executive_report_text": "========================================\nEXECUTIVE SUMMARY\n..."
  },
  "pages": [
    {
      "url": "https://example-hospital.com/about",
      "scraped_at": "2026-07-01T00:00:00Z",
      "page_title": "About Us | Max Health Private Hospital",
      "meta": { "description": "...", "keywords": "..." },
      "contacts": { "emails": ["..."], "phones": ["..."] },
      "social_profiles": { "linkedin": ["..."] },
      "structured_data": [{ "source": "json_ld", "data": {} }],
      "navigation": [{ "label": "Home", "url": "https://..." }],
      "headings": [{ "level": "h1", "text": "About Us" }],
      "content_blocks": ["..."],
      "tables": [{ "headers": ["Name", "Role"], "rows": [{}] }],
      "images": [{ "src": "https://...", "alt": "Hospital entrance" }]
    }
  ]
}
```

---

## OpenRouter API & Token Budget

WebProfiler uses [OpenRouter](https://openrouter.ai) to access the LLM for two features:

| Feature | Function | Token cap | When called |
|---------|----------|-----------|-------------|
| Outreach email | `generate_outreach_email()` | 280 tokens out | Once per run |
| Sales strategy | `generate_sales_strategy()` | 350 tokens out | Once per run |

Both use `meta-llama/llama-3.1-8b-instruct:free` by default, which is available on OpenRouter's free tier.

**Free tier budget:** ~4,000 tokens/day. With the caps above, you can run approximately **6–8 full AI-enabled analyses per day** before hitting the limit.

**To stay within budget:**
- Use `--no-email` while testing scraping and classification features
- Run AI generation only on leads that score B or above
- Change `OPENROUTER_MODEL` in `intelligence.py` to a paid model for higher limits

If either AI call fails (rate limit, invalid key, network error), the pipeline continues normally. The error message is recorded in `sales_strategy_error` / `outreach_email_error` in the JSON output. The rest of the report is unaffected.

---

## Customization Guide

All configurable elements are plain Python dictionaries or lists at the top of their respective sections — no config files needed.

| What to change | Where | Effect |
|---------------|-------|--------|
| Product catalog | `DEPARTMENT_PRODUCTS` in `intelligence.py` | Updates recommendations + opportunity matrix |
| Department priority tiers | `DEPARTMENT_PRIORITY` in `intelligence.py` | Changes High/Medium/Low in opportunity matrix |
| Lead scoring weights | `LEAD_SCORE_RULES` in `intelligence.py` | Adjusts point values per parameter |
| Grade thresholds | `LEAD_GRADE_BANDS` in `intelligence.py` | Changes A+/A/B/C/D cutoffs |
| Role priority scores | `ROLE_PRIORITY` in `intelligence.py` | Reweights stakeholder star ratings |
| AI model | `OPENROUTER_MODEL` in `intelligence.py` | Switch to any OpenRouter-hosted model |
| Org type keyword signals | `ORG_TYPE_SIGNALS` in `intelligence.py` | Add/reweight classification keywords |
| Department keyword aliases | `DEPARTMENT_KEYWORDS` in `intelligence.py` | Add new departments or aliases |
| Crawl priority pages | `PRIORITY_KEYWORDS` in `scraper.py` | Which URL patterns are crawled first |
| Private hospital keywords | `PRIVATE_HOSPITAL_KEYWORDS` in `intelligence.py` | Expand ownership-type detection |
| Contact email rules | `EMAIL_PREFIX_RULES` in `intelligence.py` | Add new email pattern classifications |

**City detection** is intentionally manual (`--city` flag). Extracting city reliably from arbitrary website text produces too many false positives to be useful — pass it per crawl or per batch.

---

## Module Map

### `scraper.py` — Crawling & Extraction

| Function / Constant | Purpose |
|--------------------|---------|
| `setup_logger()` | Configures console logging |
| `PHONE_RE`, `EMAIL_RE` | Compiled regex patterns |
| `SOCIAL_DOMAINS` | Platform name lookup by domain |
| `is_valid_phone()` | 7–15 digit validator, rejects years |
| `extract_contacts()` | Emails, phones, social profiles from page |
| `extract_structured_data()` | JSON-LD + OpenGraph meta |
| `extract_metadata()` | All `<meta>` tags |
| `extract_headings()` | H1–H4 in document order |
| `extract_main_content()` | Boilerplate-filtered body paragraphs |
| `extract_images()` | Images with meaningful alt text |
| `extract_tables()` | Tables as header+rows JSON |
| `extract_navigation()` | Nav links with labels |
| `PRIORITY_KEYWORDS`, `score_url()` | Crawl priority scoring |
| `crawl()` | Main Playwright crawl loop |
| `build_output()` | Assembles final report envelope |
| `parse_args()`, `main()` | CLI entry point |

### `intelligence.py` — Analysis & AI

| Function / Constant | Purpose |
|--------------------|---------|
| `ORG_TYPE_SIGNALS`, `classify_organization()` | 7-type org classification |
| `DEPARTMENT_KEYWORDS`, `detect_departments()` | 25-department keyword detection |
| `DEPARTMENT_PRODUCTS`, `recommend_products()` | Product recommendations per dept |
| `ORG_TYPE_BASE_SCORES`, `DEPARTMENT_BONUS_SCORES`, `calculate_opportunity_score()` | Generic opportunity score |
| `PRIVATE_HOSPITAL_KEYWORDS`, `detect_private_hospital()` | Ownership type detection |
| `DECISION_MAKER_TITLES`, `DECISION_MAKER_NAME_RE`, `detect_decision_maker()` | Named person + title detection |
| `LEAD_SCORE_RULES`, `LEAD_GRADE_BANDS`, `grade_lead()`, `calculate_lead_score()` | Sales-rule lead scoring + grading |
| `DEPARTMENT_PRIORITY`, `build_opportunity_matrix()` | Prioritised product-opportunity table |
| `build_sales_checklist()` | 7-item pass/fail checklist |
| `OPENROUTER_API_URL`, `OPENROUTER_MODEL`, `generate_outreach_email()` | AI email generation |
| `ROLE_PRIORITY`, `_stars()`, `classify_stakeholders()` | Role-based stakeholder priority |
| `DEPT_HEAD_SIGNALS`, `DEPT_PRODUCT_HINT`, `link_department_heads()` | Dept → person → product linking |
| `EMAIL_PREFIX_RULES`, `recommend_contacts()` | Contact classification + ranking |
| `STRATEGY_MAX_TOKENS`, `generate_sales_strategy()` | AI sales strategy generation |
| `calculate_classification_confidence()` | Explainable confidence % for org type |
| `format_executive_report()` | Plain-text sectioned report renderer |
| `_guess_org_name()` | Org name from page title/heading |
| `build_intelligence_profile()` | Master orchestration function |
| `DEFAULT_DB_PATH`, `init_database()`, `save_lead_to_database()` | SQLite persistence |

---

## Limitations & Known Caveats

**Department head linking is best-effort.** It relies on a named person with a courtesy title (Dr./Prof./Mr./Mrs./Ms.) appearing within ~120 characters of a department keyword. Websites that list staff without titles, or in JavaScript-rendered modals, will not be matched.

**Decision maker detection can produce false positives.** Any capitalized 2+ word name near a leadership keyword will be flagged. Names that are incidentally near the word "Director" in a sentence like "Board of Directors" may be captured. Always have a salesperson verify before acting on a name.

**Organization classification is keyword-based, not semantic.** A Pharmaceutical Company that happens to mention "hospital" frequently (e.g. "we supply hospitals") could score as a Hospital. The confidence score and full score breakdown exist specifically to flag these ambiguous cases.

**Phone extraction can include false positives.** International phone regex is inherently imprecise — reference numbers, zip codes, or ID numbers with 7+ digits may occasionally match. Always verify phones before calling.

**AI features require an internet connection and a valid OpenRouter API key.** All other features (crawling, classification, scoring, checklist, executive report, database) work fully offline.

**The crawler respects `--max-pages` strictly.** Large sites with hundreds of pages will be partially crawled. The priority queue ensures the most valuable pages (contact, about, team, services) are visited first, so the intelligence output is still useful even on a 10-page crawl.

**JavaScript-heavy SPAs may not render completely.** Playwright handles most JavaScript, but sites that require login, CAPTCHA, or have very unusual rendering pipelines may return incomplete HTML. The `--verbose` flag will show which pages were skipped and why.

---

*WebProfiler — Built for Apex Steritech. Extensible for any B2B medical sales workflow.*
