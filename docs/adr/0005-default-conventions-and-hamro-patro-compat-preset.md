# ADR 0005: Default Calculation Conventions and hamro_patro_compat Preset

## Status
Accepted

## Context
Vedic astrology calculation engines exhibit variations across traditions and modern software applications due to differences in:
1. Sidereal Ayanamsha definition (e.g. standard Chitrapaksha/Lahiri vs older historical fixed offsets such as Lahiri 1940).
2. Lunar Node definition (Mean Node vs True Node).
3. House system division (Whole Sign vs Placidus or Sripati).

Hamro Patro is a reference standard in Nepal and South Asia, while textbook standard calculations typically use standard Lahiri and Mean Node.

## Decision
1. Retain standard conventions as the engine default in `ChartSettings`:
   * Ayanamsha: `lahiri` (`SE_SIDM_LAHIRI`)
   * Lunar Nodes: `mean` (`SE_MEAN_NODE`), with Ketu strictly $(Rahu + 180^\circ) \pmod{360^\circ}$
   * House System: `whole_sign` (`b'W'`)
2. Add `LAHIRI_1940` (`SE_SIDM_LAHIRI_1940`) to `AyanamshaMode`.
3. Provide a documented, non-default calculation preset `hamro_patro_compat` configured with `node_type = "true"` and `ayanamsha = "lahiri_1940"`.

## Consequences & Verification Findings
Benchmarking against Hamro Patro reference data yielded:
* **Planetary Longitudes:** Constant offset of about 41 arcseconds under default Lahiri, about 11 arcseconds under LAHIRI_1940 with true node; remaining difference unexplained.
* **Saturn Discrepancy:** Engine matches direct library call; Hamro Patro's displayed value matches the engine's position three days later; cause unconfirmed. The discrepancy is explicitly documented in the private fixture with `known_discrepancy: true` and asserted to exceed tolerance.
* **Lagna Discrepancy:** About 4 to 5 arcminutes, cause unconfirmed; engine matches stock Swiss Ephemeris.
* **External Checks:** Checked externally by the project author on 2026-10-10 (stock pyswisseph in Moshier mode; astropy's built-in ephemeris for Saturn); not reproduced by the repository's tests.
