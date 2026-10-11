# Kundali Frontend

The frontend is a Next.js web application built with the App Router, TypeScript, and Tailwind CSS.

---

## Current Status: Scaffold Only

* **Root Page:** The root page (`src/app/page.tsx`) is the unmodified starter page from `create-next-app`.
* **Route Groups:** Scaffolded route groups exist for three user roles:
  * `src/app/(user)/page.tsx` — Placeholder returning `<h1>User Panel</h1>`.
  * `src/app/(astrologer)/page.tsx` — Placeholder returning `<h1>Astrologer Panel</h1>`.
  * `src/app/(admin)/page.tsx` — Placeholder returning `<h1>Admin Panel</h1>`.
* **Components & Library:** `src/components/` and `src/lib/` are currently empty. No real interactive pages, chart visualizers, or forms have been implemented.
* **Internationalization (`next-intl`):** Message dictionary files exist for English (`src/i18n/en.json`) and Nepali (`src/i18n/ne.json`), each containing only two initial keys (`app.title` and `app.description`). Localization routing is not yet integrated.
* **Quality Verification:** `npm run lint` passes with 0 errors. Note that `npm run build` was not run during validation.

---

## Setup & Development

All package caches must point to `D:\DevCache`.

1. **Configure Environment:**
   ```powershell
   . ..\scripts\env.ps1
   ```

2. **Install Dependencies:**
   ```powershell
   cd frontend
   npm install
   ```

3. **Run Development Server:**
   ```powershell
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000) to view the local scaffold.

4. **Run Linter:**
   ```powershell
   npm run lint
   ```
