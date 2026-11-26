# Kundali Frontend Design Specification

- **Brand:** `Kundali` / `कुण्डली` — *"Transparent Vedic Astrology, Computed Then Interpreted."*
- **Core Principle:** *"Every number is computed. Every claim is cited. Every reading can be checked."*
- **Visual Direction:** **Observatory Timetable** workbench (`seed:af9075ad1d56dc53`; see [.impeccable/surfaces/frontend-src-app-user-page-tsx.md](../.impeccable/surfaces/frontend-src-app-user-page-tsx.md)).

> This document is the canonical frontend design specification under [AGENTS.md](../AGENTS.md). Future `/impeccable document` or `/learn-taste` updates targeting the frontend must update this file rather than creating a conflicting root `DESIGN.md`.

---

## 1. Product Identity & Surface Modes

Kundali separates deterministic Swiss Ephemeris computation (`Compute First`) from citation-enforced, human-reviewed interpretation (`Interpret Second`). The UI must communicate astronomical rigor, provenance transparency, cultural respect for Nepal and South Asia, and calm ethical restraint—never a dark cosmic horoscope site or a generic SaaS dashboard.

- **Public entry (`/`):** **Persuade** mode—clear explanation of the deterministic pipeline, honest framing, and verified product capabilities, directing users into `/user`, `/login`, or `/register`.
- **Authenticated & role surfaces (`/user`, `/astrologer`, `/admin`, `/login`, `/register`):** **Operate** mode—scanability, fixed tabular hierarchy, predictable controls, and explicit system status outrank decoration.
- **Permanent Honest Framing:** Every chart and interpretive reading surface must keep a visible, non-predictive disclaimer explaining that planetary positions are computed astronomically while traditional interpretive meanings are not scientifically proven to predict future events and are offered for reflection and cultural exploration.

---

## 2. Visual Identity & Preserved Tokens

All frontend surfaces must build on the existing tokens in [frontend/src/app/globals.css](src/app/globals.css). Do not introduce an unrelated color palette, dark theme, or competing token system.

### Color System (`frontend/src/app/globals.css`)

| Role | CSS Token | Hex | Usage |
| :--- | :--- | :--- | :--- |
| Primary Structural | `--kundali-navy` / `--kundali-navy-hover` | `#13293D` / `#1D3B56` | Top shell rail, primary buttons, active segment toggles, table header rules |
| Page Ground | `--kundali-cream` (`--background`) | `#F7F6F1` | Base canvas across all routes |
| Elevated Sheet | `--kundali-surface` | `#FFFFFF` | Chart cards, tables, forms, active tab panels, popovers |
| Secondary Neutral | `--kundali-strip` | `#EFECE3` | Profile/conventions strip, tab rail background, disabled control fills |
| Primary / Muted Ink | `--kundali-ink` / `--kundali-muted` | `#18222D` / `#4B5966` | Body copy, table values, secondary metadata and captions |
| Borders & Rules | `--kundali-border` / `--kundali-border-subtle` | `#D8D5CC` / `#E6E3DA` | Full 4-sided 1px sheet borders and horizontal row dividers |
| Verified / Positive | `--kundali-emerald` (`-bg`, `-border`) | `#1B6B4A` (`#E6F4EE`, `#A7D7C2`) | `swieph` provenance, `exact` birth time, selected chart/table rows, confirmed notices |
| Warning / Fallback | `--kundali-amber` (`-bg`, `-border`) | `#B85D0A` (`#FEF3E2`, `#F3C68F`) | `moshier` / `mixed` provenance notices, `f_lagna_sensitivity`, `approximate` time, retrograde pills, `:focus-visible` ring |
| Error / Destructive | `--kundali-crimson` (`-bg`, `-border`) | `#B42318` (`#FEF2F2`, `#FCA5A5`) | Validation/API/session errors, destructive delete & `Sign out all devices` confirmations |
| Unknown / Stub | `--kundali-slate-bg` (`-border`) | `#E2E8F0` (`#CBD5E1`) | `unknown` provenance, `unknown` birth time, `Backend Stub` / pending indicators |

### Typography & Devanagari Font Reality

- **Stacks in `globals.css` & `layout.tsx`:**
  - `--font-sans`: `Instrument Sans` (`next/font/local`) followed by `"Noto Sans Devanagari", "Nirmala UI", "Kohinoor Devanagari", sans-serif`.
  - `--font-mono`: `JetBrains Mono` (`next/font/local`) for fact IDs (`f_lagna`, `f_moon`), longitudes/degrees, `chart_id`, timestamps, and IANA timezones.
- **Numeric Discipline:** Apply `.tabular-data` (`font-variant-numeric: tabular-nums`) to every degree, house number, date, count, coordinate, and table column so aligned numbers never jitter.
- **Current Font Asset Caveat:** `frontend/public/fonts/` currently bundles `instrument-sans-latin*.woff2`, `jetbrains-mono-latin*.woff2`, and only `latin` / `latin-ext` subsets of `noto-sans-devanagari` (which lack `U+0900–U+097F` Devanagari glyphs). Devanagari rendering currently depends on OS fallback (`Nirmala UI` / `Kohinoor Devanagari`) until a genuine Devanagari-subset `.woff2` is added later.

### Shape, Elevation & Surface Rules

- **Flat by default:** Sheets separate from `--kundali-cream` via crisp 1px borders (`--kundali-border`) and `rounded` (`4px`) / `rounded-sm` (`2–3px`) corners. Reserve soft shadows strictly for floating overlays (`CalculationSettingsPopover`, dialogs).
- **Four-sided borders:** Keep full borders around boxes or use subtle surface tints; avoid single-sided accent bars on rounded containers.

---

## 3. Design Philosophy

**Avoid:**
- Generic AI-generated SaaS dashboard grids, repetitive uniform cards, or excessive rounded containers.
- Unnecessary gradients (especially gradient text), glowing halos, glassmorphism/backdrop-blur decoration, or dark zodiac/constellation backdrops.
- Random decorative astronomy illustrations or fake cosmic metaphors.
- Unnecessary animations, scroll-triggered reveals on workbenches, or heavy shadows.
- Fabricated statistics, fake user counts, invented testimonials, or mock astrologer endorsements.
- Fabricated astronomical numbers, guessed birth times, or invented planetary dignity/predictions.

**Prefer:**
- Clear typographic and grid hierarchy (`1.22fr / 0.78fr` split and `@container` grids where appropriate).
- Intentional whitespace, clean hairline rules, and calm information density.
- Structured, inspectable data tables paired with crisp deterministic SVG visualizations.
- Distinctive, purposeful page compositions tailored to each role rather than one cloned layout.
- Subtle, fast (`150–250ms` `ease-out`) state-confirming interactions that stay out of frequent workflows.

---

## 4. Product-Specific UI Requirements

All application features must strictly remain within [docs/Kundali_Project_Plan.md](../docs/Kundali_Project_Plan.md). Never display stubbed backend features as functional.

| Surface | Required Workflows & Visual Hierarchy | Stub / Pending Guardrails |
| :--- | :--- | :--- |
| **Public Landing (`/`)** | Product overview explaining *"Compute First, Interpret Second"*, verifiable astronomy vs traditional interpretation, honest non-predictive framing, bilingual EN/NE clarity, and clear entry actions to `/user`, `/login`, `/register`. | Zero fake stats, reviews, or unverified accuracy claims. Keep any demo/sample entry explicitly labeled as synthetic engine output. |
| **User Panel (`/user`)** | Encrypted AD/BS birth profiles (explicit coordinates & IANA timezone, no silent Kathmandu prefill); `input_calendar` vs `display_calendar` separation; explicit `time_certainty` (`exact`, `approximate`, `unknown`); North/South Indian SVG charts synchronized with `PlanetaryTable`; `swieph`/`moshier`/`mixed`/`unknown` provenance badge; staged `CalculationSettingsPopover` (`whole_sign` fixed, `year_days` scoped cleanly); future Dasha, Transits, Grounded Chat (with expandable `fact_ids`/`chunk_ids` chips and `traditional`/`tentative` badges), and `/me/export` / `DELETE /me` privacy controls. | Keep `SAMPLE_NORTH_LONDON_PROFILE` strictly isolated from saved profiles. Show explicit `409` / `Backend Stub` / pending states for BS conversion (`bikram_sambat.py`), unknown-time Moon bounds, Dasha, Transits, AI Chat, Milan, D9/Yogas, and privacy export/delete until implemented. |
| **Astrologer Panel (`/astrologer`)** | Role-gated workbench (`astrologer` approved or `admin`, plus application flow for `user`): review queue -> side-by-side inspection (**ChartFacts** \| **Retrieved Sources** \| **AI Reading**) -> **Approve / Edit / Reject with categorized reason** -> Tier-1 knowledge entry editor -> personal review statistics. | Enforce data-visibility isolation: astrologers inspect derived facts only, never raw user identity or birth date/time/coordinates. Clearly label unimplemented queue/decision/knowledge endpoints until backend APIs exist. |
| **Admin Panel (`/admin`)** | Role-gated operational console: user activation/deactivation (with self and last-admin protections), astrologer application review (approve/suspend), audit log inspection (PII-sanitized), and planned calculation accuracy, grounding/validator metrics, KB source provenance/toggles, and moderation escalations. | Keep implemented admin APIs (`/admin/users`, `/admin/astrologers`, `/admin/audit`) cleanly separated from clearly badged stub/pending analytics, accuracy suite, and KB source management panels. |

---

## 5. Bilingual Design (English & Nepali / Devanagari)

English (`en`) and Nepali (`ne`) are co-equal primary interfaces:

- **Dictionary Parity:** Maintain strict key parity between [frontend/src/i18n/en.json](src/i18n/en.json) and [frontend/src/i18n/ne.json](src/i18n/ne.json) within the existing `next-intl` architecture; prohibit hardcoded English-only interface strings.
- **Expansion & Wrapping:** Allow ~25–35% horizontal/vertical breathing room for Nepali copy. Use `min-w-0`, content-driven button widths (`min-h`), and generous `line-height` so Devanagari *matras* and stacked conjuncts never clip.
- **Domain Terminology & Numbers:** Keep classical Jyotish terms (*Lagna*, *Rashi*, *Nakshatra*, *Pada*, *Dasha*, *Gochara*) recognizable alongside plain explanations in English and idiomatic Devanagari in Nepali. Format astronomical degrees, timestamps, and numeric metrics clearly with `tabular-nums` and `JetBrains Mono`.
- **Language Attributes:** Ensure `lang` reflects the active locale on localized shells/surfaces as internationalization routing is wired in.

---

## 6. Accessibility & Responsive Design (WCAG 2.1 AA)

- **Semantic Structure:** Use `<header>`, `<nav>`, `<main>`, `<section>`, `<aside>`, and semantic `<table>` (`<caption>`, `<th scope="col">`) elements; preserve sequential `<h1>`–`<h6>` hierarchy and include a keyboard skip link on every panel shell.
- **Keyboard & Focus:** Every interactive element must be reachable via keyboard (`Tab`, `Enter`/`Space`, `Escape` to dismiss popovers/selections) with visible `:focus-visible` outlines (`2px solid var(--kundali-amber)`, `2px` offset) unobstructed by sticky bars.
- **Forms & Live Regions:** Every form control requires an explicit `<label htmlFor>` (or `aria-label` where visually implied), `id`/`name`, appropriate `type`/`inputMode`/`autoComplete`, inline accessible error announcements (`role="alert"`), and `aria-live="polite"` status updates.
- **Chart Accessibility:** Every North/South Indian SVG chart (`role="img"`, interactive house/sign `role="button"` groups with `aria-label` and `aria-pressed`) must ship alongside a synchronized textual/tabular equivalent (`PlanetaryTable`, mobile stacked placement cards under `<640px`).
- **Responsive Viewports & Reduced Motion:** Support desktop (`1440px` / `1280px`), tablet (`768px` / `820px`), and mobile (`390px` / `320px`) without horizontal overflow or overlapping controls. Preserve `@media (prefers-reduced-motion: reduce)` from `globals.css`.
- **Contrast:** Maintain ≥4.5:1 contrast for body/label/placeholder text and ≥3:1 for large text and UI state borders.

---

## 7. Skill Orchestration Hierarchy

This file is the primary authority for Kundali's visual identity. Follow the [project plan](../docs/Kundali_Project_Plan.md), [PRODUCT.md](../PRODUCT.md), [root agent rules](../AGENTS.md), [frontend agent rules](AGENTS.md), and the relevant `.impeccable/surfaces/` brief. Use the installed Next.js documentation for framework behavior. These sources take precedence over generic skill guidance. Activate only the skills relevant to the task.

| Skill | Assigned Role in Kundali | Boundary / Conflict Resolution |
| :--- | :--- | :--- |
| **`design-taste-frontend`** | High-level anti-slop visual critique, layout rhythm, equal edges, and content realism checks. | **Do not** run its `start.mjs` palette/font dealer, kit scaffold, `output: 'export'`, stock-photo replacement, or WebGL/shader effects; Kundali's tokens and Next.js server routes govern. |
| **`impeccable`** | Design critique and refinement (`critique`, `audit`, `polish`, `harden`) and upkeep of surface briefs (`.impeccable/surfaces/*`). | Use `frontend/DESIGN.md` for design documentation. Honor `Operate` restraint on panels and `Persuade` clarity on `/`. |
| **`emil-design-eng`** | Micro-interaction craft, CSS transitions (`150–250ms` `ease-out`), `:active` press feedback (`scale(0.97)`), origin-aware popovers, GPU-only `transform`/`opacity`. | Use restrained motion and honor reduced-motion preferences. **Do not** add `motion` / `framer-motion` without explicit requirement; never animate frequent keyboard actions. |
| **`break-ui`** | Adversarial stress-testing against worst-case realistic data (long emails, Devanagari expansion, zero/one/many rows, `mixed` provenance, 320px/200% zoom). | Any "Demo data / Worst case" toggle must remain strictly dev/test-only, never leak into API requests, and never mutate deterministic `ChartFacts`. |
| **`learn-taste`** | Capturing explicit user design corrections and recurring taste preferences into concrete rules or checks. | Propose rules first and stop for confirmation; target `frontend/DESIGN.md` (or project lint rules) when approved. |
| **`landing-page-design`** | Public landing page (`/`) only. Apply Part A to page structure, value proposition, FAQ, and SEO/AEO. | Subordinate Part B rules to Kundali: **ignore** Geist/Manrope/Poppins replacement, hero text gradients, glassmorphic blur navbars, mandatory scroll-reveal words, and the "no-hyphens" ban where astronomical/technical terms require them. |
| **`web-design-guidelines`** | Accessibility, focus-visible, form attributes, semantic HTML, contrast, and `file:line` interface audits. | Follow `references/command.md` checks; keep Kundali's sentence/title phrasing conventions and existing `useState`/Next Router state patterns unless URL state is genuinely needed. |
| **`vercel-react-best-practices`** | React 19 / Next.js rendering performance (server vs client boundary, avoiding waterfalls, bundle discipline, stable callbacks/rerenders). | Subordinate to [frontend/AGENTS.md](AGENTS.md) and `node_modules/next/dist/docs/` for Next.js `16.4.6` (`cacheComponents` / `partialPrefetching`). Do not add `swr` or `React Query` unnecessarily. |
| **`playwright-cli`** | Real-browser verification methodology (snapshots, console/network audit, responsive checks, keyboard & reduced-motion checks). | **Never** run `npm install -g @playwright/cli`. Reuse the local `playwright` (`1.65.1`) package and `D:\DevCache\ms-playwright` binaries via `scripts/env.ps1`. |

---

## 8. Technical Architecture & Verification Standard

### Existing Frontend Stack (Preserve)
- **Framework:** Next.js `16.4.6` App Router (`cacheComponents: true`, `partialPrefetching: true` in [frontend/next.config.ts](next.config.ts)), React `19.3.0`, TypeScript `5` (`strict: true`), Tailwind CSS `4`, `next-intl`, Playwright `1.65.1`.
- **Next.js 16.4.6 Rule:** Before writing or modifying routes, layouts, data fetching, or caching, read the relevant installed docs in `frontend/node_modules/next/dist/docs/`.
- **Security & State Boundaries:** Preserve same-origin BFF `/api/auth/*` (`HttpOnly` refresh cookie + `Origin` + `X-Kundali-CSRF: 1`), in-memory `AuthSessionProvider` (`navigator.locks` + `BroadcastChannel`), `apiRequest` (`credentials: "omit"` + single 401 retry), and strict synthetic isolation (`assertNotSynthetic`). Do not add component libraries, state libraries, or animation packages without explicit necessity.

### Browser & Quality Verification Workflow
1. Always load `. .\scripts\env.ps1` so Node, npm, temp, and `PLAYWRIGHT_BROWSERS_PATH` (`D:\DevCache\ms-playwright`) stay on `D:`.
2. On Windows, run `npm run lint` (`eslint`), `next build`, and Playwright Chromium checks outside the restricted sandbox (`BypassSandbox: true`); keep `node --test` and `tsc --noEmit` green after edits.
3. Reuse and extend [frontend/e2e/auth-browser.test.mjs](e2e/auth-browser.test.mjs) (and add focused E2E specs for `/`, `/user`, `/astrologer`, `/admin`) using the installed `playwright` Node API (`chromium.launch()`) rather than deleting existing coverage.
4. Every UI milestone must verify in a real headless browser:
   - Desktop (`1440x900` / `1280x800`), tablet (`768x1024`), and mobile (`390x844` / `375x812`) with zero horizontal overflow or control overlaps.
   - Zero uncaught `pageerror`, `console.error`, or unexpected failed network requests.
   - Interactive flows in both `EN` and `नेपाली` (`AD`/`BS` inputs, chart/table cross-highlighting, form validation, role guards, stub notices).
   - Keyboard navigation (`Tab`, `Enter`, `Space`, `Escape`), visible focus rings, and `prefers-reduced-motion` behavior, plus screenshot inspection for layout changes.
