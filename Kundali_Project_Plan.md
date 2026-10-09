# Kundali 🪐 — Transparent Vedic Astrology, Computed Then Interpreted

> *"Every number is computed. Every claim is cited. Every reading can be checked."*

---

## Table of Contents

1. Project Overview
2. The Problem and the Gap
3. Core Design Principle — Compute First, Interpret Second
4. Users and Panels
5. Feature Specification
6. System Architecture
7. Tech Stack (Hardware-Aware)
8. The Calculation Engine
9. The Interpretation Engine (Grounded RAG)
10. Astrologer Verification Workflow
11. Data Model
12. API Design
13. Frontend Design
14. Security, Privacy and Ethics
15. Testing and Validation Strategy
16. Evaluation Metrics
17. Hardware Constraints and Engineering Decisions
18. Project Structure
19. Risks and Mitigations
20. Viva Preparation — Hard Questions and Real Answers
21. Future Extensions

---

## 1. Project Overview

**Kundali** is a full stack web platform that generates a real, astronomically
computed Vedic birth chart and lets the user ask questions about it through
an AI assistant whose answers are **grounded in the user's own computed chart
data and in a curated, astrologer-verified knowledge base**.

It has three panels:

- **User Panel** — chart generation, chart visualization, Dasha timeline,
  transit tracking, grounded Q&A, compatibility matching
- **Astrologer Panel** — a review queue where practicing astrologers verify,
  correct and annotate AI-generated readings; their approved content becomes
  the highest-trust layer of the knowledge base
- **Admin Panel** — astrologer credentialing, calculation accuracy monitoring,
  content moderation, system analytics

**Type:** Full stack web application (frontend + backend + database + AI layer)
**Domain:** Computational astronomy + retrieval-augmented generation + human-in-the-loop review
**Regional focus:** Built with Nepal and South Asia in mind — Bikram Sambat
date support, Nepal Time (UTC+5:45), Nepali-language interface, North Indian
diamond chart style (the format users already see in Hamro Patro)

---

## 2. The Problem and the Gap

Mainstream astrology apps fall into two groups:

| Group | What they do | What is missing |
|---|---|---|
| Content apps (Co-Star style) | Sun/Moon/Rising with generic daily text | No real chart depth, no Vedic system, no transparency |
| Calculator apps (Hamro Patro, Jagannatha Hora style) | Accurate charts, Dasha tables, panchang | Static output — you read a table, you get no explanation and cannot ask questions |

And the newer wave of "AI astrologer" chatbots has a serious flaw: the LLM is
often asked to **both calculate and interpret**. LLMs cannot reliably compute
planetary positions, so they produce confident, plausible, wrong chart data —
and users cannot tell.

**The gap:** nobody combines an accurate deterministic calculator with an AI
interpreter that is *structurally prevented from inventing chart facts*, plus
a human expert review layer that makes the knowledge base trustworthy over time.

---

## 3. Core Design Principle — Compute First, Interpret Second

This is the sentence the whole project is built around:

> **The LLM never calculates. It only explains facts that a deterministic
> engine already computed, and every claim it makes must cite one.**

```
Birth data
    ↓
Deterministic calculation engine (Swiss Ephemeris)
    ↓
Structured Chart Facts (JSON, each fact has an ID)
    ↓
LLM receives ONLY these facts + retrieved knowledge chunks
    ↓
LLM must output claims that cite fact IDs and chunk IDs
    ↓
Validator rejects any claim citing a non-existent fact,
or mentioning a placement not present in the facts
    ↓
Verified response shown to user (and queued for astrologer review)
```

This one architectural rule is what separates Kundali from a chatbot with a
zodiac prompt. It is also the strongest thing to defend in a viva.

**Honest framing (important):** the *calculation* layer is verifiable
astronomy — planetary longitudes can be checked against any reference
ephemeris. The *interpretation* layer is a traditional, culturally
established practice and is **not scientifically validated as predictive**.
Kundali positions itself as a transparent tool for exploring a traditional
system and for reflection — not as a source of certain predictions. This is
reflected in product copy, guardrails and disclaimers (see Section 14).

---

## 4. Users and Panels

### 4.1 User Panel

- Create an account and one or more **birth profiles** (self, family, friends)
- Enter birth date in AD or BS, time, and place (geocoded to lat/long/timezone)
- View the computed chart (North Indian and South Indian styles)
- View planetary table: sign, degree, nakshatra, pada, house, retrograde, dignity
- View **Vimshottari Dasha timeline** (Mahadasha → Antardasha → Pratyantardasha)
- View **transits** relative to the natal chart, and upcoming ingress events
- Ask questions in a chat interface; every answer shows its **citations**
  (which chart facts and which knowledge sources it used)
- **Kundali Milan** — Ashtakoota (36-point) compatibility between two profiles
- Receive **transit alerts** (e.g. slow-planet sign changes affecting their chart)
- Export chart as PDF/PNG; delete all their data at any time

### 4.2 Astrologer Panel

- Apply and get credentialed by an admin
- **Review queue:** AI-generated readings awaiting verification
- For each item: see the chart facts, the retrieved sources, the AI output —
  then **approve**, **edit**, or **reject with a reason**
- Author original knowledge entries (rules, yoga descriptions, interpretation
  notes) which enter the knowledge base with their name and credentials attached
- Personal stats: items reviewed, approval rate, corrections made

### 4.3 Admin Panel

- Approve/suspend astrologer accounts
- **Calculation accuracy dashboard** — regression tests against reference charts
- **AI quality dashboard** — citation validity rate, rejection rate by validator,
  astrologer acceptance rate, unsupported-claim rate over time
- Moderation queue for flagged responses and user reports
- Knowledge base management (source provenance, versioning, disable a source)
- Usage analytics, audit logs

---

## 5. Feature Specification

### Core Features (Must Have)

| # | Feature | Description |
|---|---|---|
| 1 | Ephemeris-based chart calculation | Sidereal positions via Swiss Ephemeris, configurable ayanamsha (default Lahiri), Lagna, houses, nakshatra/pada, retrograde, Rahu/Ketu |
| 2 | Vimshottari Dasha engine | Three-level Dasha periods with exact start/end dates computed from Moon's nakshatra position |
| 3 | Grounded AI chat | Answers scoped to the user's chart; every claim cites fact IDs and knowledge chunk IDs; validator enforces grounding |
| 4 | Astrologer review workflow | Human-in-the-loop verification; approved content promoted to trusted knowledge |
| 5 | Role-based access across 3 panels | User / Astrologer / Admin with permission middleware and audit logging |
| 6 | Transit engine + alerts | Computes current/future transits and ingress events, notifies users |
| 7 | Chart visualization | SVG North Indian and South Indian charts, Dasha timeline, planetary table |

### Enhanced Features (Strong Additions)

| # | Feature | Description |
|---|---|---|
| 8 | Kundali Milan | Ashtakoota 36-point matching (Varna, Vashya, Tara, Yoni, Graha Maitri, Gana, Bhakoot, Nadi) — fully deterministic |
| 9 | Divisional charts | Navamsa (D9) first, then D10 and others |
| 10 | Yoga detection | Rule-based detection of classical yogas (Budhaditya, Gajakesari, Raja yogas, etc.) with the rule and its source shown |
| 11 | Bikram Sambat support | Date conversion and Nepali calendar-aware input |
| 12 | Nepali-language UI and responses | Interface localization and Nepali answer generation |
| 13 | Panchang for a date | Tithi, vara, nakshatra, yoga, karana for any date |

---

## 6. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js)                             │
│  User Panel  |  Astrologer Panel  |  Admin Panel   (role-gated routes) │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ REST + (optional) SSE for chat streaming
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                          BACKEND (FastAPI)                             │
│                                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ Auth & RBAC  │  │ Calculation  │  │Interpretation│  │  Review   │ │
│  │  (JWT, roles)│  │   Engine     │  │   Engine     │  │ Workflow  │ │
│  └──────────────┘  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘ │
│                           │                  │                │       │
│                           ▼                  ▼                ▼       │
│                  ┌────────────────┐   ┌────────────┐   ┌──────────┐  │
│                  │ Swiss Ephemeris│   │  Retriever │   │ Validator│  │
│                  │  (pyswisseph)  │   │ (pgvector) │   │(grounding│  │
│                  └────────────────┘   └─────┬──────┘   │  checks) │  │
│                                             │          └────┬─────┘  │
│                                             ▼               │        │
│                                    ┌─────────────────┐      │        │
│                                    │  LLM Adapter    │◄─────┘        │
│                                    │(hosted / local) │               │
│                                    └─────────────────┘               │
│                                                                        │
│  ┌──────────────────────┐   ┌────────────────────────────────────┐   │
│  │ Scheduler (APScheduler│   │ Notification service (email/in-app)│   │
│  │  transit alert jobs)  │   └────────────────────────────────────┘   │
│  └──────────────────────┘                                              │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │ PostgreSQL + pgvector          │
                 │ users • profiles • charts •    │
                 │ facts • dashas • knowledge •   │
                 │ chunks(vector) • reviews • logs│
                 └──────────────────────────────┘
```

### Module Dependency Map

```
Calculation Engine  ──►  Chart Facts  ──►  Interpretation Engine  ──►  Review Workflow
        │                     │                      ▲                        │
        ▼                     ▼                      │                        ▼
  Dasha + Transit         Kundali Milan       Knowledge Base  ◄────  Verified Astrologer Content
```

The calculation engine has **zero dependency on any AI component** — it can be
built, tested and validated completely on its own.

---

## 7. Tech Stack (Hardware-Aware)

All choices below were made with a laptop of **Intel i7 8th gen, 8 GB RAM,
GTX 1060 6 GB, Windows** in mind (see Section 17 for the reasoning).

### Frontend
```
Next.js (App Router) + TypeScript
Tailwind CSS
next-intl                 — English / Nepali localization
React Query               — server state
Custom SVG components     — North/South Indian charts, Dasha timeline
Recharts                  — admin analytics charts
```

### Backend
```
Python 3.11+
FastAPI + Uvicorn
Pydantic v2               — strict schemas for facts and LLM output
SQLAlchemy 2.0 + Alembic  — ORM and migrations
APScheduler               — transit alert jobs (lighter than Celery+Redis)
Argon2 (passlib/argon2-cffi) — password hashing
```

### Calculation Layer
```
pyswisseph                — Python bindings to Swiss Ephemeris
                            (note: AGPL / commercial dual license —
                             fine for an academic project, note it in docs)
timezonefinder + zoneinfo — coordinates → timezone
Custom BS↔AD converter    — lookup-table based
```

### AI Layer
```
Embeddings:  multilingual-e5-small (384-dim, CPU-friendly, handles
             Nepali/Hindi/English) via sentence-transformers
Vector DB:   pgvector inside PostgreSQL (one database, no extra service)
LLM:         Provider-agnostic adapter
               - Primary: hosted inference API (free-tier friendly —
                 e.g. HuggingFace Inference, Groq, Gemini, OpenRouter)
               - Fallback/offline demo: local Ollama with a quantized
                 3B–7B instruct model (Q4) on the GTX 1060
Structured output: JSON schema + Pydantic validation + retry
```

### Database
```
PostgreSQL 15/16 + pgvector extension
Column-level encryption for birth data (pgcrypto or app-level Fernet)
```

### Infrastructure
```
Docker — PostgreSQL only during development (see Section 17)
Docker Compose for final deployment demo
GitHub Actions — tests + calculation regression suite on every push
```

---

## 8. The Calculation Engine

This is the deterministic heart of the project. It must be **correct,
testable and independent of any AI**.

### 8.1 Inputs and Normalization

```
Birth date  (AD, or BS converted to AD)
Birth time  (local time)
Birth place → latitude, longitude, IANA timezone
              (Nepal Time is UTC+5:45 — verify your timezone library
               handles the 45-minute offset correctly)
```

Convert local time → UTC → Julian Day. **Timezone/offset mistakes are the #1
source of wrong charts**, so this step gets its own dedicated tests.

### 8.2 Planetary Positions (Sidereal)

```python
import swisseph as swe
from datetime import datetime

# Ayanamsha is configurable; Lahiri (Chitrapaksha) is the common default
swe.set_sid_mode(swe.SIDM_LAHIRI)

FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

PLANETS = {
    "Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS,
    "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER,
    "Venus": swe.VENUS, "Saturn": swe.SATURN,
    "Rahu": swe.MEAN_NODE,          # Ketu = Rahu + 180°
}

def julian_day_utc(dt_utc: datetime) -> float:
    hour = dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour)

def compute_positions(jd: float) -> dict:
    out = {}
    for name, body in PLANETS.items():
        xx, _ = swe.calc_ut(jd, body, FLAGS)
        lon, speed = xx[0] % 360, xx[3]
        out[name] = {"longitude": lon, "retrograde": speed < 0}
    out["Ketu"] = {
        "longitude": (out["Rahu"]["longitude"] + 180) % 360,
        "retrograde": True,   # nodes are conventionally shown retrograde
    }
    return out
```

### 8.3 Lagna (Ascendant) and Houses

```python
def compute_lagna(jd: float, lat: float, lon: float) -> float:
    # 'W' = whole sign; ascendant is returned in ascmc[0]
    _, ascmc = swe.houses_ex(jd, lat, lon, b'W', swe.FLG_SIDEREAL)
    return ascmc[0] % 360

def sign_of(longitude: float) -> int:          # 0 = Aries ... 11 = Pisces
    return int(longitude // 30)

def house_of(planet_lon: float, lagna_lon: float) -> int:
    return (sign_of(planet_lon) - sign_of(lagna_lon)) % 12 + 1
```

The Lagna is extremely time-sensitive (it changes sign roughly every two hours),
so the UI should show a **birth-time sensitivity warning** — if the Lagna is
within a small number of degrees of a sign boundary, tell the user the chart
may change with a few minutes' error in birth time.

### 8.4 Nakshatra and Pada

```python
NAK_SPAN = 360 / 27            # 13°20'
PADA_SPAN = NAK_SPAN / 4       # 3°20'

def nakshatra_of(longitude: float) -> tuple[int, int]:
    idx = int(longitude // NAK_SPAN)                       # 0..26
    pada = int((longitude % NAK_SPAN) // PADA_SPAN) + 1    # 1..4
    return idx, pada
```

### 8.5 Vimshottari Dasha

```python
DASHA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars",
               "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
               "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17}   # = 120
YEAR_DAYS = 365.25   # configurable — some software uses 360 or 365.2425

def dasha_lord_of_nakshatra(nak_idx: int) -> str:
    return DASHA_ORDER[nak_idx % 9]

def dasha_balance_at_birth(moon_lon: float) -> tuple[str, float]:
    nak_idx = int(moon_lon // NAK_SPAN)
    lord = dasha_lord_of_nakshatra(nak_idx)
    elapsed_fraction = (moon_lon % NAK_SPAN) / NAK_SPAN
    balance_years = DASHA_YEARS[lord] * (1 - elapsed_fraction)
    return lord, balance_years

def antardasha_sequence(md_lord: str, md_years: float):
    """Sub-periods start from the Mahadasha lord and follow the same order.
    Antardasha length = md_years * planet_years / 120."""
    start = DASHA_ORDER.index(md_lord)
    for i in range(9):
        planet = DASHA_ORDER[(start + i) % 9]
        yield planet, md_years * DASHA_YEARS[planet] / 120
```

The year-length convention (365.25 vs 360 vs 365.2425 days) shifts period
boundaries by days over a lifetime — expose it as a setting and **state which
convention is used** on every Dasha table.

### 8.6 Transits

Transits reuse `compute_positions` at the current date and compare against the
natal chart:

- Current sign/house of each planet from natal Lagna and natal Moon
- **Ingress events:** find the date when a planet crosses a sign boundary
  (bisection search on longitude within a date range — cheap and precise)
- Retrograde station dates (speed sign change)
- Slow planets (Saturn, Jupiter, Rahu/Ketu) are the most alert-worthy

### 8.7 Kundali Milan (Ashtakoota)

A deterministic scoring module using both Moon nakshatras/rashis. Each koota
is a small lookup table plus a rule; the total is out of 36. Because it is
entirely rule-based it needs **no AI**, and the interpretation layer only
explains the resulting numbers. Every koota score is returned with the rule
that produced it (this transparency is the point).

### 8.8 Yoga Detection

Yogas are encoded as **declarative rules** stored in the database, not hardcoded
prose:

```json
{
  "id": "budhaditya",
  "name": "Budhaditya Yoga",
  "condition": {"type": "conjunction", "planets": ["Sun", "Mercury"]},
  "source_id": "src_042",
  "notes": "Strength reduced if Mercury is closely combust."
}
```

A small rule evaluator checks each rule against the chart facts and emits a
fact with the rule ID. Astrologers can add or refine rules from their panel —
this is how expert knowledge enters the *computation* layer, not only the
text layer.

### 8.9 Chart Facts — The Contract Between Engine and AI

Everything the AI is allowed to say comes from this structure:

```json
{
  "chart_id": "c_9f2",
  "engine_version": "1.0.0",
  "settings": {"ayanamsha": "lahiri", "house_system": "whole_sign", "year_days": 365.25},
  "facts": [
    {"id": "f_lagna",   "type": "lagna",     "sign": "Cancer", "degree": 12.4},
    {"id": "f_moon",    "type": "placement", "planet": "Moon", "sign": "Libra",
     "house": 5, "nakshatra": "Swati", "pada": 1},
    {"id": "f_md_now",  "type": "dasha",     "level": "MD", "lord": "Mercury",
     "start": "2023-06-01", "end": "2040-06-01"},
    {"id": "f_yoga_1",  "type": "yoga",      "rule_id": "budhaditya", "planets": ["Sun","Mercury"]}
  ]
}
```

Every fact has a stable ID. **The LLM may only reference these IDs.**

---

## 9. The Interpretation Engine (Grounded RAG)

### 9.1 Knowledge Base Sources

| Tier | Source | Trust |
|---|---|---|
| 1 | Astrologer-authored and approved entries (with name/credentials) | Highest |
| 2 | Public-domain classical text translations | High |
| 3 | Admin-curated reference summaries | Medium |

**Licensing note:** many modern translations of classical works (including
popular editions of Brihat Parashara Hora Shastra) are copyrighted. Use
public-domain translations, texts explicitly licensed for reuse, or content
written by your credentialed astrologers. Record source, edition, license and
URL for every document — **provenance metadata is a required field**, not a
nice-to-have.

### 9.2 Chunking and Metadata

Chunk by *conceptual unit* (one yoga, one planet-in-house rule, one Dasha
lord description), not by fixed token windows. Attach structured metadata so
retrieval can be **filtered, not just similarity-ranked**:

```
chunk: { text, embedding, source_id, tier, language,
         topic: "planet_in_house" | "yoga" | "dasha" | "nakshatra" | ...,
         applies_to: {"planet": "Moon", "house": 5} }   # when applicable
```

### 9.3 Retrieval Strategy

1. Parse the user's question into topics/entities (career, relationships,
   a specific planet, a specific Dasha)
2. Select the **relevant chart facts** deterministically (e.g. a career
   question pulls 10th house, its lord, Saturn, Sun, current Dasha)
3. Retrieve chunks by **metadata filter first** (`applies_to` matches the
   selected facts), then rank by vector similarity, boost by tier
4. Cap the context: a handful of facts + a handful of chunks — this also keeps
   prompts small for free-tier and local models

### 9.4 Generation Contract

The model must return a structured object:

```python
from pydantic import BaseModel

class Claim(BaseModel):
    text: str
    fact_ids: list[str]        # which chart facts support this claim
    chunk_ids: list[str]       # which knowledge chunks support it
    confidence: str            # "traditional" | "tentative"

class Reading(BaseModel):
    summary: str
    claims: list[Claim]
    caveats: list[str]
```

### 9.5 The Grounding Validator (the critical component)

Runs after every generation, before anything is shown:

```
For each claim:
  ✔ every fact_id exists in this chart's facts
  ✔ every chunk_id exists and was actually in the retrieved set
  ✔ no planet/sign/house/nakshatra named in claim.text that is
    absent from the cited facts  (regex + entity check)
  ✔ claim is not a forbidden category (see Section 14)
If validation fails → one automatic retry with the failure reason
                    → else return a safe "could not ground this" response
```

This makes hallucinated chart data **structurally rejected**, not just
"discouraged in the prompt."

### 9.6 Prompt Design Principles

- The system prompt states the rules once: *only use provided facts; cite IDs;
  traditional framing; no certainty about future events; no medical/legal/
  financial directives*
- Chart facts and chunks are injected as clearly delimited data blocks
- User text is treated as untrusted data (basic prompt-injection hygiene)
- Tone modes (gentle / direct / concise) change style, never the grounding rules

### 9.7 Nepali and Multilingual Behavior

- Retrieval uses a multilingual embedding model, so a Nepali question can
  retrieve English chunks
- Generation language follows the user's setting; the validator still operates
  on fact IDs, so grounding is language-independent
- Measure Nepali answer quality separately (see Section 16) — do not assume
  parity with English

---

## 10. Astrologer Verification Workflow

```
AI response generated  ──►  Validator passes  ──►  Shown to user immediately
                                                        │
                                           (sampled or flagged, or user-requested)
                                                        ▼
                                             Review queue (Astrologer Panel)
                                                        │
                        ┌───────────────┬───────────────┴──────────────┐
                        ▼               ▼                              ▼
                    Approve           Edit                       Reject + reason
                        │               │                              │
                        └──────┬────────┘                              ▼
                               ▼                              Logged as failure case
              Promoted to Tier-1 knowledge (with reviewer name)   (feeds evaluation set)
```

Design details:

- **Two ways an item enters the queue:** random sampling for quality
  measurement, and any response a user marks as "wrong/unhelpful"
- **Users can request an "astrologer-verified" answer** — it goes to the queue
  and they are notified when a reviewer responds (optional feature)
- Reviewers see **facts + sources + output side by side** and must give a reason
  for every rejection (reasons are categorized: wrong rule, misapplied fact,
  tone problem, unsupported claim)
- Approved edits become **new Tier-1 chunks**, so the knowledge base improves
  from real use; this is the project's feedback loop
- Reviewer disagreement: if two reviewers disagree on the same item, escalate
  to admin (and record it — inter-reviewer agreement is itself a metric)

---

## 11. Data Model

```sql
users (
  id UUID PK, email UNIQUE, password_hash, role ENUM('user','astrologer','admin'),
  language, created_at, deleted_at
)

astrologer_profiles (
  user_id FK, display_name, credentials TEXT, tradition TEXT,
  status ENUM('pending','approved','suspended'), approved_by, approved_at
)

birth_profiles (
  id UUID PK, owner_id FK, label,
  birth_datetime_utc, birth_datetime_local_enc BYTEA,   -- encrypted
  latitude_enc BYTEA, longitude_enc BYTEA, timezone,
  time_certainty ENUM('exact','approximate','unknown'),
  created_at
)

charts (
  id UUID PK, profile_id FK, engine_version, settings JSONB,
  lagna_longitude, positions JSONB, computed_at
)

chart_facts (
  id TEXT, chart_id FK, type, payload JSONB,
  PRIMARY KEY (chart_id, id)
)

dasha_periods (
  id, chart_id FK, level SMALLINT, lord, start_date, end_date, parent_id
)

transit_events (
  id, planet, event_type ENUM('ingress','station_retro','station_direct'),
  from_sign, to_sign, event_at
)

alert_subscriptions (id, profile_id FK, planet, channel, active)
alerts (id, profile_id FK, transit_event_id FK, sent_at, read_at)

knowledge_sources (
  id, title, author, edition, license, url, tier SMALLINT,
  added_by, added_at, enabled BOOLEAN
)

knowledge_chunks (
  id, source_id FK, text, embedding VECTOR(384),
  language, topic, applies_to JSONB, version, created_at
)

yoga_rules (id, name, condition JSONB, source_id FK, authored_by, enabled)

conversations (id, profile_id FK, created_at)
messages (
  id, conversation_id FK, role, content, language, created_at
)
message_claims (
  id, message_id FK, claim_text, fact_ids TEXT[], chunk_ids TEXT[],
  confidence
)

review_items (
  id, message_id FK, reason ENUM('sampled','user_flagged','user_requested'),
  status ENUM('open','approved','edited','rejected','escalated'),
  assigned_to FK NULL, created_at
)
review_decisions (
  id, review_item_id FK, reviewer_id FK, decision, edited_text,
  rejection_category, reason TEXT, decided_at
)

audit_logs (id, actor_id, action, target_type, target_id, metadata JSONB, at)
eval_runs (id, suite, metrics JSONB, engine_version, run_at)
```

**Indexes:** `knowledge_chunks` HNSW/IVFFlat on `embedding` plus a GIN index on
`applies_to`; `dasha_periods(chart_id, level, start_date)`;
`review_items(status, created_at)`.

---

## 12. API Design (Representative)

```
AUTH
POST   /auth/register            POST /auth/login          POST /auth/refresh

PROFILES & CHARTS
POST   /profiles                 GET  /profiles            DELETE /profiles/{id}
POST   /profiles/{id}/chart      GET  /charts/{id}
GET    /charts/{id}/facts        GET  /charts/{id}/dashas
GET    /charts/{id}/divisional/{d}   (d9, d10, ...)
GET    /charts/{id}/yogas

TRANSITS
GET    /charts/{id}/transits?date=...
GET    /transits/upcoming?planets=Saturn,Jupiter
POST   /alerts/subscribe

MATCHING
POST   /milan                    { profile_a, profile_b } → koota breakdown

CHAT
POST   /charts/{id}/chat         { question, language, tone } → Reading + citations
GET    /conversations/{id}
POST   /messages/{id}/flag       POST /messages/{id}/request-review

ASTROLOGER
GET    /review/queue             POST /review/{id}/decide
POST   /knowledge                (author a Tier-1 entry)
POST   /rules/yoga               (propose a yoga rule)

ADMIN
GET    /admin/astrologers        POST /admin/astrologers/{id}/approve
GET    /admin/metrics            GET  /admin/eval-runs      POST /admin/eval-runs
POST   /admin/sources            PATCH /admin/sources/{id}/disable
GET    /admin/audit

PRIVACY
GET    /me/export                DELETE /me     (hard-deletes birth data)
```

RBAC is enforced by a dependency (`require_role("astrologer")`) on every route,
and profile ownership is checked on every chart endpoint — **a user must never
be able to fetch another user's birth data by guessing an ID.**

---

## 13. Frontend Design

### Pages by Panel

**User:** Dashboard → Profile creation → Chart view → Dasha timeline →
Transits → Chat → Milan → Settings/Privacy

**Astrologer:** Review queue → Review detail (facts | sources | AI output) →
Knowledge editor → My stats

**Admin:** Metrics overview → Accuracy suite results → Reviewer management →
Source management → Moderation → Audit log

### Key UI Components

- **Chart renderer** — pure SVG, North Indian diamond (12 fixed houses) and South
  Indian grid; planets placed with glyph + short degree; hover for details.
  Built as a function of the chart facts, so it is easy to unit test.
- **Dasha timeline** — horizontal, zoomable timeline with the current
  Mahadasha/Antardasha highlighted and "now" marker
- **Citation chips** — under every AI sentence, small chips that expand to show
  the cited chart fact (e.g. "Moon in Libra, house 5, Swati pada 1") and the
  source (author, tier). This is the visible proof of the grounding design.
- **Confidence badges** — "traditional" vs "tentative" per claim
- **Birth-time sensitivity banner** — appears when the Lagna is near a boundary
  or when time certainty is not "exact"
- **Nepali/English toggle** — full interface localization

---

## 14. Security, Privacy and Ethics

### Privacy
- Birth date, time and place are **personal data**. Encrypt time and coordinates
  at rest; never log them; never send them to third-party LLM providers
  beyond the minimum fact set needed for a question
- Send the LLM **derived chart facts, not raw birth details**
- One-click export and permanent deletion (`/me/export`, `DELETE /me`)
- Store the minimum; provide a retention policy in the docs

### Security
- Argon2 password hashing, short-lived JWT + refresh tokens
- Rate limiting on auth and chat endpoints
- Strict RBAC with server-side ownership checks
- Input validation everywhere (Pydantic); treat chat text as untrusted
- Audit log for all astrologer/admin actions

### Content Guardrails (enforced by the validator, not only the prompt)
The system will **not**:
- Predict death, serious illness, or accidents
- Give medical, legal, or financial directives ("stop your medication",
  "invest in X", "divorce")
- Present any event as certain — future-facing language is framed as
  "traditionally associated with…"
- Encourage major life decisions solely on a reading
- Continue a fear-based framing (curses, doom) — such requests are redirected
  to a calm, non-alarming response

If a user's message suggests distress or crisis, the assistant responds with a
supportive message and encourages reaching out to a trusted person or a
professional, instead of continuing a reading.

### Honest Positioning
Add a visible, permanent note: *"Astrology is a traditional interpretive
system. Kundali computes planetary positions with astronomical accuracy; the
meanings attached to them are traditional and not scientifically proven to
predict events. Use this for reflection and cultural exploration."*

This is both the ethically correct stance and the more defensible one
in a viva — the project's claim is about **transparency and computational
correctness**, not about the truth of astrology.

---

## 15. Testing and Validation Strategy

### 15.1 Calculation Regression Suite (the most important test set)

Build a **fixture library of reference charts** with known-correct values from
trusted tools, and assert engine output against them within tolerance.

**Fixture #1 is the builder's own chart**, because a trusted reference already
exists: the Hamro Patro kundali shows **Rashi Tula (Libra), Nakshatra Swati,
Pada 1** for 2 August 2006, 02:10 AM, Morang, Nepal (87.283°E, 26.45°N,
UTC+5:45). The engine's Moon sign, nakshatra and pada must match that.

Suggested fixture set (aim for 20–30 charts):
- Edge cases: births near sign boundaries, near nakshatra boundaries,
  near midnight, near daylight-saving transitions (for non-Nepal profiles)
- Southern and northern hemisphere, different timezones
- Charts from published examples (textbooks) and from established software

Assertions:
```
planet longitudes         ± 0.01° vs Swiss Ephemeris direct call
Lagna sign                exact match (flag if within 0.5° of boundary)
Moon nakshatra + pada     exact match against reference tool
Dasha start/end dates     ± 1 day (state the year-length convention)
Ingress dates             ± 1 minute vs ephemeris brute-force scan
```

When a result **disagrees** with a reference tool, investigate the *setting*
(ayanamsha, node type — mean vs true — house system, year length, timezone)
before assuming a bug. Disagreements between reputable tools are usually
convention differences; the correct behavior is to make the convention an
explicit, documented, user-visible setting.

### 15.2 Unit Tests
- BS↔AD conversion round-trips
- Timezone handling (including the 45-minute Nepal offset)
- Dasha sequence sums to 120 years; Antardasha lengths sum to the Mahadasha
- Ashtakoota table lookups
- Yoga rule evaluator against hand-built charts

### 15.3 Grounding Tests
- Adversarial prompts trying to make the model invent placements
  ("your Mars is in Aries, right?" when it is not) → validator must reject
- Prompt-injection strings inside the question
- Guardrail tests: death/health/finance certainty requests

### 15.4 Integration and Frontend Tests
- End-to-end: register → create profile → chart → chat → citation display
- RBAC tests: a user cannot access another user's chart; an astrologer cannot
  hit admin routes
- Snapshot tests for SVG chart output from fixed facts

---

## 16. Evaluation Metrics

| Category | Metric | How measured |
|---|---|---|
| Calculation | Position error vs reference | Regression suite, degrees |
| Calculation | Nakshatra/pada match rate | Fixture library |
| Calculation | Dasha date deviation | Days vs reference |
| Grounding | Citation validity rate | % of claims with all IDs valid |
| Grounding | Unsupported-claim rate | Validator rejections + reviewer flags |
| Grounding | Hallucination-attack pass rate | Adversarial suite |
| Human review | Astrologer approval rate | Review decisions |
| Human review | Inter-reviewer agreement | Items reviewed by two reviewers |
| Quality | Nepali vs English acceptance rate | Reviewer decisions split by language |
| Performance | Chart generation latency | p50 / p95 |
| Performance | Chat response latency | p50 / p95, hosted vs local model |
| Safety | Guardrail trigger correctness | Test set of prohibited requests |

Track all of these in the `eval_runs` table and show trends on the Admin panel.
Being able to show **a number that improves over time because of the
astrologer feedback loop** is the strongest possible demonstration in a viva.

---

## 17. Hardware Constraints and Engineering Decisions

**Development machine:** Intel i7 (8th gen), **8 GB RAM**, GTX 1060 **6 GB VRAM**,
Windows.

The honest constraint is **RAM, not GPU**. With Windows itself and a browser
using a large share of 8 GB, you cannot casually run Docker Desktop + Postgres +
Redis + Next.js dev server + a local LLM + an embedding model at the same time.
The architecture is chosen to make that unnecessary.

| Decision | Reasoning |
|---|---|
| **Swiss Ephemeris for calculation** | Tiny footprint, CPU only, microseconds per planet — the core of the project costs almost no resources |
| **pgvector instead of a separate vector DB** | One service fewer, one process fewer in RAM, simpler ops |
| **APScheduler instead of Celery + Redis** | Removes Redis and worker processes; transit alert jobs are light and infrequent |
| **`multilingual-e5-small` embeddings** | ~118M params, runs on CPU with modest RAM, multilingual for Nepali |
| **Hosted LLM API as primary** | 0 MB of local model RAM; use a free-tier provider during development |
| **Local Ollama as fallback, not default** | A 7B model at Q4 quantization fits in 6 GB VRAM, but should be run **alone**, on demand, for offline demos |
| **Provider-agnostic LLM adapter** | Swap hosted ↔ local with a config change; also protects against free-tier limits |
| **Small, capped prompts** | Only relevant facts + a few chunks — keeps latency and token use low on any provider |

### Practical Setup Advice for This Laptop

1. **Run only PostgreSQL in Docker** during development; run FastAPI and
   Next.js natively. Full `docker compose up` is for the final integration demo.
2. If you use Docker Desktop with WSL2, **cap its memory** (e.g. `memory=3GB`
   in `.wslconfig`) so it does not starve Windows.
3. **Never run Ollama and the full stack simultaneously** on 8 GB. Stop the
   Next.js dev server or use a production build when testing the local model.
4. Use `next build && next start` (or a deployed frontend) rather than the dev
   server when RAM is tight — it uses less memory.
5. Batch-embed the knowledge base **once**, offline, and store vectors in
   Postgres; do not re-embed at runtime.
6. Prefer 3B models for local fallback if 7B feels sluggish; the validator
   makes a smaller model safe because grounding is enforced structurally.
7. The GTX 1060 has no tensor cores — expect usable but not fast local
   generation; treat local inference as a demo/fallback path, not the main one.
8. Native Windows TensorFlow GPU is not supported on recent versions — this
   project deliberately uses **no TensorFlow** (PyTorch/Ollama/sentence-transformers only).

**Deployment note:** for the final demo, host the backend and database on a
small free/low-cost cloud instance and keep the local-LLM path as an
offline backup.

---

## 18. Project Structure

```
kundali/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/               # config, security, dependencies, RBAC
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic schemas (facts, claims, readings)
│   │   ├── api/                # routers: auth, profiles, charts, chat,
│   │   │                       #          review, admin, privacy
│   │   ├── calc/               # ★ deterministic engine (no AI imports)
│   │   │   ├── ephemeris.py    #   positions, lagna, houses
│   │   │   ├── nakshatra.py
│   │   │   ├── dasha.py
│   │   │   ├── transits.py
│   │   │   ├── divisional.py
│   │   │   ├── yogas.py        #   rule evaluator
│   │   │   ├── milan.py        #   Ashtakoota
│   │   │   ├── calendar_bs.py  #   Bikram Sambat conversion
│   │   │   └── facts.py        #   builds the Chart Facts contract
│   │   ├── ai/
│   │   │   ├── embeddings.py
│   │   │   ├── retriever.py    #   metadata filter + vector rank
│   │   │   ├── prompts.py
│   │   │   ├── llm_adapter.py  #   hosted / local providers
│   │   │   ├── generator.py
│   │   │   ├── validator.py    # ★ grounding + guardrail checks
│   │   │   └── guardrails.py
│   │   ├── review/             # workflow, promotion to Tier-1
│   │   ├── scheduler/          # APScheduler jobs (transit alerts)
│   │   └── services/           # notifications, export, deletion
│   ├── tests/
│   │   ├── calc/               # regression fixtures (reference charts)
│   │   ├── ai/                 # grounding + adversarial tests
│   │   └── api/                # RBAC + integration tests
│   ├── alembic/
│   └── pyproject.toml
├── frontend/
│   ├── app/
│   │   ├── (user)/  (astrologer)/  (admin)/
│   ├── components/
│   │   ├── charts/             # NorthIndianChart, SouthIndianChart
│   │   ├── dasha/  chat/  citations/  review/
│   ├── lib/  messages/         # i18n (en, ne)
│   └── package.json
├── knowledge/                  # source documents + ingestion scripts + provenance
├── eval/                       # eval suites, reference charts, reports
├── docs/                       # architecture diagrams, ADRs, viva notes
├── docker-compose.yml
└── README.md
```

The `calc/` package must never import from `ai/`. Enforce this with a simple
import-linter rule — it makes the "compute first, interpret second" claim
verifiable in the codebase itself.

---

## 19. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Calculation mismatch with popular apps | Expose ayanamsha / node type / house system / year length as settings; document defaults; regression suite against references |
| Wrong birth time → wrong Lagna | Time-certainty field + boundary-sensitivity warning + "unknown time" mode (Moon-based reading only) |
| LLM hallucinated placements | Structured output + grounding validator + retry + safe fallback |
| Copyrighted source material | Provenance metadata; only public-domain/licensed/astrologer-authored content |
| Users over-relying on readings | Persistent disclaimer, guardrails, calm framing, crisis handling |
| Free-tier LLM limits/outages | Provider adapter + local fallback + response caching per (chart, question) |
| Not enough real astrologers to verify | Recruit a small number of practitioners early; design the workflow to be useful even with one reviewer; record reviewer credentials transparently |
| Sensitive personal data leak | Encryption at rest, minimal logging, facts-not-raw-data to LLM providers, deletion endpoint |
| 8 GB RAM limits | Section 17 architecture (no Redis, pgvector, hosted LLM primary, Postgres-only Docker) |
| Swiss Ephemeris AGPL licensing | Acceptable for academic use; document it; note the commercial-license path |

---

## 20. Viva Preparation — Hard Questions and Real Answers

**Q: Astrology isn't scientific. Why build this?**
A: The project makes no claim that astrology predicts events. It has two
verifiable parts — accurate astronomical calculation, and transparent,
cited interpretation of a traditional system — and one honest framing:
reflection and cultural exploration. The engineering problems (deterministic
computation, grounded generation, human review) are real regardless of one's
view of astrology. Millions of people in South Asia use kundali software daily;
the question is whether the tools they use are transparent.

**Q: Why not just ask an LLM to make the chart?**
A: LLMs cannot reliably compute planetary positions; they produce plausible
but wrong data. That is why calculation is deterministic (Swiss Ephemeris) and
the LLM is only allowed to explain computed facts it cites by ID.

**Q: How do you *prove* the AI doesn't hallucinate chart facts?**
A: I can't prove it never will — I can prove it can't *surface* one unnoticed.
The validator rejects any claim citing a non-existent fact or naming a
placement absent from the cited facts, and I measure the rejection rate and an
adversarial-attack pass rate.

**Q: Why is there a human review layer?**
A: The interpretation knowledge is traditional and contested between schools.
Credentialed practitioners verify and correct outputs; their approved content
becomes the highest-trust tier, so quality improves from real use.

**Q: Why pgvector, not a dedicated vector database?**
A: One database, one source of truth, no dual-write consistency problem, lower
memory footprint — and my corpus is small enough that pgvector's performance
is more than sufficient.

**Q: What if your chart disagrees with another app?**
A: Usually a convention difference — ayanamsha, mean vs true node, house
system, or year length. I expose these as explicit settings, document the
defaults, and validate against multiple reference tools in the regression suite.

**Q: How do you handle privacy?**
A: Encryption at rest for birth data, minimal logging, only derived facts (not
raw birth details) sent to LLM providers, and full export/deletion.

**Q: What is the hardest engineering problem here?**
A: Constraining generation so it is *useful* yet structurally grounded —
retrieval design (metadata-filtered), the claim/citation schema, and the
validator together — plus getting Nepali-language quality up to parity.

**Q: What would you do with more time/compute?**
A: Fine-tune a small multilingual model on the astrologer-approved corpus,
add more divisional charts and Ashtakavarga, and run a formal inter-reviewer
agreement study.

---

## 21. Future Extensions

- Ashtakavarga and Shadbala (planetary strength computations)
- More divisional charts (D10, D7, D12…) with per-chart interpretation
- Muhurta (auspicious time) finder with configurable rules
- Panchang calendar with festival integration (Nepali calendar aware)
- Fine-tuned small multilingual model on the verified corpus
- Mobile PWA with push notifications for transit alerts
- Public API for the calculation engine (rate-limited)
- Comparative mode — the same chart interpreted under different traditions
  (Parashari vs Jaimini), clearly labeled

---

## Why This Is a Strong Second-Year Project

- **Genuine full stack:** auth + RBAC, three role-specific panels, relational
  and vector data, background jobs, SVG chart rendering, i18n
- **Real computation:** astronomical calculation and Dasha mathematics that can
  be *verified against reference software* — not a black box
- **Real AI engineering:** retrieval with metadata filtering, structured
  generation, a grounding validator, and an evaluation harness — not an API
  wrapper
- **Human-in-the-loop design:** a verification workflow that measurably
  improves the system, with numbers to show for it
- **Fits real constraints:** built to run on an 8 GB laptop
- **Authentic:** the builder has spent months reading his own chart, cross-
  checking a local astrologer against software output, and noticing where tools
  disagree — this project is the tool he kept wishing existed

---

*Built by gyr0byte — "Not a person, a process — always building, never stopping."*

**Status:** Planning complete
**Type:** Second Year full stack project
