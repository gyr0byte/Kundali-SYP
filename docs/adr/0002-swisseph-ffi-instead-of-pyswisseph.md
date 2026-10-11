# ADR 0002: Use swisseph-ffi Instead of pyswisseph

## Status
Accepted

## Context
The project requires Swiss Ephemeris bindings in Python for high-precision astronomical calculations (planetary positions, sidereal ayanamsha, and house cusps).
During initial backend environment setup, the coding agent reported that no prebuilt `pyswisseph` binary wheel was available for this Windows setup and that a source build would require a local C compiler toolchain (MSVC), which was not installed. This claim was not independently re-verified.

## Decision
Use `swisseph-ffi` as the Swiss Ephemeris binding for Python.
Package details from metadata:
* Package: `swisseph-ffi`
* Version: `1.0.0`
* Author: Jayesh Mepani <jayeshmepani777@gmail.com>
* Repository: <https://github.com/jayeshmepani/Swiss-Ephemeris-Python>

## Consequences
* `swisseph-ffi` is a single-maintainer package that bundles precompiled Swiss Ephemeris dynamic libraries and accesses C routines via `ctypes`.
* Requires managing `ctypes` data buffers (e.g. `c_double * 6`, string buffers) and explicit thread synchronization for shared C-library state (`swe_set_sid_mode`).
* Calculation results produced by `swisseph-ffi` were cross-checked externally by the author against stock `pyswisseph` and verified to match within sub-arcsecond tolerances.
* The underlying Swiss Ephemeris C library is licensed under GNU AGPL-3.0, determining the project licence.
