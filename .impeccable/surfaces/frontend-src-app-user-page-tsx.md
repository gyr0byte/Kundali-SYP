---
version: 1
slug: "frontend-src-app-user-page-tsx"
primary_target: "frontend/src/app/user/page.tsx"
related_targets: []
---

# Surface Brief: User Panel Chart Workspace

- **Primary target:** `frontend/src/app/user/page.tsx`
- **Visitor mode:** `Operate` (code-led build path)
- **Audience & job:** Everyday Nepali and South Asian users creating AD/BS birth profiles, inspecting deterministic sidereal placements, verifying chart settings and ephemeris provenance, and querying Dasha, transits, and cited AI explanations under honest non-predictive framing.
- **Proof & boundaries:** Exact `ChartFacts` alignment (`ChartSettings` for conventions, `ChartMetadata` for `ephemeris_source` with `swieph` / `moshier` / `unknown`, individual fact IDs only, no planetary dignity); allowlisted LLM payload excluding timestamps/Julian Day/coordinates; distinct `exact` / `approximate` / `unknown` birth-time modes; dedicated deterministic `ChartFacts` synthetic preview generated from `scripts/chart_cli.py` for North London (`2015-05-15 14:30:00 Europe/London`, never `fixture_north_london.json` as a raw partial `ChartFacts` and never `fixture_001_builder.json`); persist original `input_calendar` (`AD` | `BS`) and `entered_date` separately from `display_calendar` preference (`AD` | `BS` | `Both`); unknown-time Moon-boundary calculation defined over the complete local civil birth-date interval (`[00:00:00, 24:00:00)`) converted via the profile's IANA timezone (do not claim boundary detection until implemented); staged calculation settings with scoped **Apply & Recompute** (`year_days` does not recompute planetary positions); `whole_sign` shown as fixed convention; unimplemented backend modules held in contract/preview states.
- **Unresolved dependencies:** `birth_datetime_utc` at-rest encryption discrepancy, LLM allowlist & validator pipeline, unknown-time Moon-based calculation contract over complete local civil birth-date interval (IANA timezone), stubbed `bikram_sambat.py`/`dasha.py`/`transits.py`/API/knowledge modules, geocoding/timezone lookup, full `next-intl` dictionary expansion, and font stack finalization.

## Direction contract

- **THESIS:** An analytical **Observatory Timetable** workbench where deterministic Vedic astronomy, multi-level Vimshottari period rulers, and cited AI claims lock onto one calm, inspectable grid—refusing both dark cosmic horoscope clichés and generic SaaS gray boxes.
- **OWN-WORLD:** Prussian-navy top rail (`#13293D`), signal-cream ground (`#F7F6F1`), white chart/table sheets (`#FFFFFF`), emerald verified states (`#1B6B4A`), amber warning/fallback signals (`#B85D0A`), crimson error states (`#B42318`), bilingual Latin + Devanagari sans with `tabular-nums`, and column-locked rules.
- **STORY:** The user confirms their birth profile, input vs. display calendar (`AD`/`BS`), time certainty, and `swieph`/`moshier`/`unknown` provenance at a glance, cross-checks the North/South Indian SVG against the planetary table, and asks questions whose cited fact chips highlight the matching row and house in sync.
- **FIRST VIEWPORT:** Top shell bar (`Kundali / कुण्डली`, nav, provenance badge, `EN / नेपाली`), profile & conventions strip with staged `Calculation Settings` trigger, two-pane desktop split (conditional certainty/Lagna-sensitivity banners + SVG chart & planetary table left; stepped `Grounded Chat | Vimshottari Dasha | Transits` tabs right), and unobstructed persistent footer disclaimer.
- **FORM:** Observatory Timetable, candidate 6 of 7 in the ordered grounded list, `seed:af9075ad1d56dc53` (code-led; anchored on `.impeccable/mocks/decision/assigned.html`).
- **FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
