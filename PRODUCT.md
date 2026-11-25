# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary users:** Everyday Nepali and South Asian users generating and exploring personal or family birth charts (`birth_profiles`), verifying planetary placements against familiar local tools (such as Hamro Patro), tracking Vimshottari Dasha and planetary transits, and asking grounded interpretive questions.
- **Secondary users — Credentialed astrologers:** Practicing astrologers approved by an admin who review sampled, user-flagged, or user-requested AI readings side by side with computed facts and sources, approve/edit/reject outputs, and author Tier-1 knowledge entries.
- **Secondary users — Administrators:** Platform admins managing astrologer credentialing, calculation regression accuracy, AI grounding/quality metrics, content moderation, knowledge source provenance, and audit logs.
- **Evaluation audience:** Academic / SYP viva evaluators reviewing computational precision, grounding enforcement, and human-in-the-loop quality metrics as an inspectable engineering system.

## Product Purpose

Kundali exists to close the gap between generic lifestyle horoscope apps (which lack astronomical depth and transparency), static Vedic chart calculators (which output raw tables without explanation or Q&A), and ungrounded AI astrology chatbots (which hallucinate planetary placements).

Success means:
1. Every astronomical number is deterministically computed from birth data before any interpretation runs.
2. Every interpretive claim in AI Q&A cites verifiable chart fact IDs and provenance-tracked knowledge chunks, enforced structurally by a validator before display.
3. Credentialed astrologers review and correct readings so the knowledge base becomes more trustworthy over time, while users maintain full privacy and data control.

## Positioning

**"Compute First, Interpret Second."** The LLM never calculates planetary positions or chart geometry. A deterministic Swiss Ephemeris engine emits an immutable `ChartFacts` contract with stable IDs (`f_lagna`, `f_sun`..`f_ketu`, `f_lagna_sensitivity`). The AI layer receives only derived facts and metadata-filtered knowledge chunks and must emit structured claims citing fact IDs and chunk IDs; a post-generation grounding validator rejects any claim referencing non-existent facts, absent placements, or prohibited advice before the response reaches the user—paired with an astrologer verification workflow that promotes approved readings into Tier-1 knowledge.

## Operating Context

- **Three role-gated panels:** User Panel (`/user`), Astrologer Panel (`/astrologer`), and Admin Panel (`/admin`), sharing one Next.js App Router frontend and FastAPI backend with strict RBAC and profile ownership isolation.
- **Regional & astronomical conventions:** Designed for Nepal and South Asia—supporting birth dates in either **AD or Bikram Sambat (BS)**, Nepal Time (`UTC+5:45`, `Asia/Kathmandu`) alongside global IANA timezones, North Indian diamond and South Indian chart formats, and explicit, user-visible astronomical conventions (`ayanamsha`: `lahiri`, `lahiri_1940`, `raman`, `krishnamurti`; `node_type`: `mean` vs `true`, including the `hamro_patro_compat` preset; `whole_sign` houses; configurable Dasha year-length conventions `365.25`, `360`, `365.2425`).
- **Birth-time uncertainty & sensitivity:** Lagna changes sign roughly every two hours; charts carry explicit `time_certainty` (`exact`, `approximate`, `unknown`) and emit `f_lagna_sensitivity` warnings when Lagna sits within `0.5°` of a sign boundary.
- **Core workflows:**
  - *User:* Create account and birth profiles (entering birth date in AD or BS, local time, and place geocoded to lat/lon/timezone) → view computed chart (North/South Indian SVG + planetary table + sensitivity notice) → explore Vimshottari Dasha timeline (Mahadasha → Antardasha → Pratyantardasha) and transits/ingress alerts → ask grounded questions in chat with expandable citation chips and confidence badges (`traditional` vs `tentative`) → flag/request astrologer review → export or permanently delete personal data (`/me/export`, `DELETE /me`).
  - *Astrologer:* View review queue → inspect chart facts, retrieved sources, and AI output side by side → approve, edit, or reject with categorized reason → author Tier-1 knowledge entries and review personal stats.
  - *Admin:* Approve/suspend astrologer credentials → monitor calculation accuracy and AI grounding dashboards → manage knowledge sources, moderation escalations, and audit logs.
- **Hardware-aware deployment context:** Engineered around an 8 GB RAM / 6 GB VRAM Windows development constraint (PostgreSQL + pgvector in one database, APScheduler instead of Celery/Redis, hosted LLM API primary with standalone quantized local Ollama fallback).

## Capabilities and Constraints

- **Initial Core Scope & Foundational Requirements (Phase 1 priority):**
  - Ephemeris-based sidereal chart calculation (implemented in `backend/app/calc/`).
  - **Bikram Sambat (BS) birth-date input** alongside Gregorian (AD) input in user birth-profile workflows (`docs/Kundali_Project_Plan.md` Sections 1, 4.1, 5 #11).
  - **Accurate BS-to-Gregorian (AD) date conversion** via a lookup-table-based `BS↔AD` converter verified with round-trip unit tests before ephemeris computation (`docs/Kundali_Project_Plan.md` Sections 7, 8.1, 15.2; currently a stub in `backend/app/calc/bikram_sambat.py` awaiting its planned implementation).
  - **Calculation workflow date/time normalization:** Combine the resolved AD birth date with local birth time and birth place (latitude, longitude, IANA timezone—explicitly handling Nepal Time `UTC+5:45` and DST gap/overlap disambiguation), convert `local time → UTC → Julian Day` (`backend/app/calc/timeconv.py`), and encrypt raw local datetime and coordinates at rest while storing `birth_datetime_utc` (`docs/Kundali_Project_Plan.md` Sections 8.1, 8.2, 11).
  - Authentication, rotating refresh tokens, and 3-role RBAC (implemented in `backend/app/api/v1/auth.py`, `admin.py`, `astrologer.py`).
  - Interactive SVG North Indian and South Indian charts, planetary placement table, and birth-time sensitivity banner.
  - Vimshottari Dasha timeline, transit tracking and ingress alerts, grounded AI chat with citation chips and validator enforcement, astrologer review workflow, and admin accuracy/quality dashboards.
  - Full English and Nepali (Devanagari) UI parity from the start via `next-intl`.
- **Deferred / Later Phases (from `docs/Kundali_Project_Plan.md`):**
  - Kundali Milan (Ashtakoota 36-point compatibility), divisional charts (D9 Navamsa, D10, etc.), rule-based Yoga detection, and Panchang for a date are deferred until after the core experience.
  - Unimplemented backend modules (`bikram_sambat.py`, `dasha.py`, `transits.py`, `ai/*`, `jobs/*`, `knowledge/*`) remain stubs in the repository until their planned implementation phases.
- **Explicitly Undecided Product Facts:**
  - Public entry access boundary (whether the root route allows a guest/demo chart calculation before login, or directs directly to authentication for `/user`, `/astrologer`, `/admin`).
  - Initial seeded knowledge-base source catalog and initial practicing astrologer reviewer roster.
- **Binding Technical, Privacy & Ethical Constraints:**
  - `docs/Kundali_Project_Plan.md` is the authoritative feature boundary—do not invent features outside it.
  - `backend/app/calc/` must never import from `backend/app/ai/` (enforced by `import-linter`).
  - Development tooling, caches, and temp files must live on `D:` (never write to `C:`).
  - Birth date, time, and coordinates are encrypted at rest, never logged, and never sent raw to third-party LLMs (only derived `ChartFacts` are sent); users can export or hard-delete all data at any time.
  - Validator-enforced guardrails prohibit predicting death, serious illness, or accidents; giving medical, legal, or financial directives; presenting future events with certainty; or continuing fear-based framing (crisis/distress queries trigger supportive redirection).
  - Licensed under GNU AGPL-3.0 (required by Swiss Ephemeris / `swisseph-ffi`). Knowledge sources require explicit provenance metadata (`title`, `author`, `edition`, `license`, `url`); copyrighted translations without reuse rights are excluded.

## Brand Commitments

- **Product Name:** `Kundali` / `कुण्डली`
- **Binding Taglines & Copy:**
  - *"Every number is computed. Every claim is cited. Every reading can be checked."* (`docs/Kundali_Project_Plan.md`)
  - *"Transparent Vedic Astrology, Computed Then Interpreted"* / *"पारदर्शी वैदिक ज्योतिष, गणना पहिले, व्याख्या पछि"* (`frontend/src/i18n/en.json`, `ne.json`)
- **Binding Honest-Framing Disclaimer:** Every chart/reading experience must carry a visible, permanent note stating that Kundali computes planetary positions with astronomical accuracy while traditional interpretive meanings are not scientifically proven to predict events, and are intended for reflection and cultural exploration.
- **Voice & Terminology:** Calm, transparent, respectful, and non-alarmist. Keep classical Vedic terms (*Lagna*, *Rashi*, *Nakshatra*, *Pada*, *Dasha*, *Gochara*) inline in English UI paired with plain explanations rather than translating them away, and maintain natural, idiomatic Nepali (Devanagari) parity.
- **Assets:** No final logo, brand mark, or custom illustration assets exist on hand (`frontend/public/` contains only default Next.js starter SVGs).

## Evidence on Hand

- **Implemented Calculation & Auth Foundation:** `backend/app/calc/` (`timeconv`, `ayanamsha`, `ephemeris`, `houses`, `nakshatra`, `facts`), `backend/app/core/`, `backend/app/services/`, `backend/app/db/models/`, `backend/app/api/v1/auth.py`, `admin.py`, `astrologer.py`, and `scripts/chart_cli.py`, backed by unit, regression, and integration tests (`README.md` reports 161 passing tests).
- **Calculation Regression & Benchmark Data:** Four public synthetic golden-master chart snapshots in `fixtures/charts/` (`fixture_001_builder.json`, `fixture_near_midnight_tokyo.json`, `fixture_north_london.json`, `fixture_south_sydney.json`) and documented variance/benchmark comparisons against Hamro Patro in `docs/architecture/calc-engine.md` and `docs/adr/0005-default-conventions-and-hamro-patro-compat-preset.md`.
- **Frontend & i18n Scaffold:** `frontend/src/app/` placeholder routes (`/`, `/user`, `/astrologer`, `/admin`) and starter dictionaries `frontend/src/i18n/en.json` and `frontend/src/i18n/ne.json` (currently 2 keys each).
- **Explicit Absences (must not be fabricated):** No running database instance, no ingested knowledge-base corpus, no real astrologer accounts or review decisions, no user testimonials, customer logos, case studies, press mentions, or production latency/accuracy metrics exist yet.

## Product Principles

1. **Compute First, Interpret Second:** Never compute astronomy in AI or fabricate placements; surface deterministic facts, ephemeris provenance (`swieph` vs `moshier`), and convention settings openly.
2. **Radical Provenance & Citation:** Every interpretive claim displays its cited chart facts, knowledge source tier/provenance, and confidence level (`traditional` vs `tentative`) alongside honest non-predictive framing.
3. **Human Verification Over Autonomous Authority:** AI outputs remain accountable to credentialed astrologer review and measurable quality/validator metrics.
4. **Privacy, Restraint & Emotional Safety:** Protect raw birth details at rest and in transit, avoid fear-based or directive predictions, and preserve user-initiated export and deletion.
5. **Bilingual Parity & Accessible Clarity:** Treat English and Nepali (Devanagari) as equal primary surfaces, explain Vedic terms inline, and pair visual charts with accessible structured tables.

## Accessibility & Inclusion

- Target **WCAG 2.1 AA** across User, Astrologer, and Admin surfaces.
- Provide full keyboard navigation and structured text/table equivalents (planetary table, house-by-house breakdown, ARIA summaries) alongside SVG North Indian and South Indian chart visualizations so chart reading never relies solely on spatial geometry.
- Maintain full English and Nepali (Devanagari) UI parity from the start, ensuring legible Devanagari rendering, AD and Bikram Sambat (BS) date-input parity, and consistent non-standard timezone handling (`UTC+5:45`).
