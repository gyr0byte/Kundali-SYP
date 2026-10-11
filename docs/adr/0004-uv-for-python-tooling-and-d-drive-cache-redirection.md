# ADR 0004: uv for Python Tooling and D: Drive Cache Redirection

## Status
Accepted

## Context
System constraints require that no development files, tool installations, caches, or temporary directories write to the `C:` drive. All project assets, packages, and temporary files must reside on `D:`.

## Decision
Use Astral's `uv` as the fast, single-binary Python package and virtual environment manager. Enforce cache isolation by requiring all PowerShell sessions to dot-source `scripts/env.ps1`, which redirects:
* `UV_CACHE_DIR`, `UV_TOOL_DIR`, `UV_PYTHON_INSTALL_DIR`, `PIP_CACHE_DIR` to `D:\DevCache`
* `npm_config_cache`, `npm_config_prefix`, `COREPACK_HOME` to `D:\DevCache`
* `TEMP`, `TMP`, `XDG_CACHE_HOME`, `HF_HOME`, `TORCH_HOME` to `D:\DevCache`

## Consequences
* Fast and reproducible virtual environment creation and dependency locking via `uv.lock`.
* Complete physical isolation from system paths on the `C:` drive.
* Developers and automation must dot-source `scripts/env.ps1` at the start of each terminal session.
