# System Architecture Documentation

This directory contains architectural specifications and component guides for the Kundali project.

---

## Documents Index

* [`calc-engine.md`](calc-engine.md): Specification of the deterministic calculation engine, sidereal conventions, thread-safety locking, Chart Facts schema, and third-party benchmark findings.
* [`DATABASE_SETUP.md`](DATABASE_SETUP.md): Instructions for provisioning hosted PostgreSQL with `pgvector` (Neon or Supabase), connection security (`sslmode=require`), and current stub status.

---

## High-Level Calculation Pipeline

The core pipeline transforms raw birth data into an immutable, validated `ChartFacts` document:

```
Birth Input (Date, Time, Lat/Lon, Timezone)
    │
    ▼ [IMPLEMENTED]
timeconv: UTC timestamp and Julian Day conversion via swe_julday
    │
    ├─────────────────────────────┬─────────────────────────────┐
    ▼ [IMPLEMENTED]               ▼ [IMPLEMENTED]               ▼ [IMPLEMENTED]
ayanamsha: Sidereal Mode      ephemeris: Sidereal Longitudes   houses: Whole-Sign Houses
(Lahiri, Lahiri 1940, Raman)  Sun..Saturn, Rahu, Ketu          Lagna & House Allocation
under SWE_LOCK                Speed & Retrograde flags         under SWE_LOCK
    │                             │                             │
    └─────────────────────────────┼─────────────────────────────┘
                                  ▼ [IMPLEMENTED]
                           nakshatra: Longitude to 27 Nakshatras & 4 Padas
                                  │
                                  ▼ [IMPLEMENTED]
                           facts: Immutable ChartFacts Document (Pydantic v2)
                                  │
    ┌─────────────────────────────┼─────────────────────────────┐
    ▼ [STUB]                      ▼ [STUB]                      ▼ [STUB]
dasha: Vimshottari Timeline   transits: Ingress & Gochara   yogas: Combination Rules
                                  │
                                  ▼ [STUB]
                      ai: Grounded RAG Interpretation
```

### Pipeline Implementation Status
* **Implemented:** Birth input validation, Julian Day conversion (`timeconv`), sidereal modes (`ayanamsha`), planetary longitudes and nodes (`ephemeris`), whole-sign houses and Lagna (`houses`), nakshatra/pada mapping (`nakshatra`), and Chart Facts document generation (`facts`).
* **Stubs (Planned):** Dasha timeline (`dasha`), transit tracking (`transits`), yogas (`yogas`), compatibility (`ashtakoota`), calendar conversion (`bikram_sambat`), and all AI interpretation modules (`app/ai/`).
