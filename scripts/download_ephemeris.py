r"""Download Swiss Ephemeris data files to backend/ephe/.

Downloads the three core .se1 files for the 1800-2399 AD range from
the official astro.com FTP mirror. These provide high-precision
planetary/lunar positions (sub-arcsecond). Without them, swisseph-ffi
falls back to the built-in Moshier analytical ephemeris (~1 arcsecond).

All downloads go to D:\SYP\Kundali\backend\ephe\ — nothing on C:.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

# Files to download: covers 1800–2399 AD
# sepl = planets, semo = moon, seas = main asteroids
FILES = [
    "sepl_18.se1",
    "semo_18.se1",
    "seas_18.se1",
]

BASE_URL = "https://raw.githubusercontent.com/aloistr/swisseph/master/ephe"
DEST_DIR = Path(__file__).resolve().parent.parent / "backend" / "ephe"


def download_file(filename: str) -> None:
    """Download a single ephemeris file if not already present."""
    dest = DEST_DIR / filename
    if dest.exists():
        print(f"  SKIP  {filename} (already exists, {dest.stat().st_size:,} bytes)")
        return

    url = f"{BASE_URL}/{filename}"
    print(f"  GET   {url}")
    print(f"        -> {dest}")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Kundali-Downloader/1.0"})
        with urllib.request.urlopen(req) as resp, open(dest, "wb") as out_file:
            out_file.write(resp.read())
        size = dest.stat().st_size
        print(f"  OK    {filename} ({size:,} bytes)")
    except Exception as exc:
        # Clean up partial download
        if dest.exists():
            dest.unlink()
        print(f"  FAIL  {filename}: {exc}")
        raise


def main() -> None:
    print(f"Ephemeris download target: {DEST_DIR}")
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    for f in FILES:
        download_file(f)

    # Verify all files exist
    print("\nVerification:")
    all_ok = True
    for f in FILES:
        p = DEST_DIR / f
        if p.exists():
            print(f"  OK    {f} ({p.stat().st_size:,} bytes)")
        else:
            print(f"  MISS  {f}")
            all_ok = False

    if all_ok:
        print("\nAll ephemeris files present.")
    else:
        print("\nSome files are missing!", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
