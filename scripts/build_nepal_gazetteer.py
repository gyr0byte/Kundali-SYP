"""Extract the pinned GeoNames Nepal archive into the packaged birthplace dataset."""

import argparse
import csv
import gzip
import hashlib
import io
import unicodedata
from pathlib import Path
from zipfile import ZipFile

SOURCE_SHA256 = "d46b480c53e30f68800474f4dabd8eeec2138afbb12bb3fecdfcdfc1815e021a"
OUTPUT = Path(__file__).resolve().parents[1] / "backend/app/geo/data/nepal.tsv.gz"
POPULATED = {"PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLC", "PPLF", "PPLS", "PPLX"}


def supported_alias(name: str) -> bool:
    """Retain source spellings in Latin or Devanagari script."""
    return bool(name) and all(
        character.isascii()
        or "\u0900" <= character <= "\u097f"
        or unicodedata.name(character, "").startswith("LATIN ")
        or "\u0300" <= character <= "\u036f"
        or character in "\u200c\u200d\u2019"
        for character in name
    )


def build(archive: Path) -> int:
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("GeoNames Nepal source archive checksum does not match")
    with ZipFile(archive) as source, source.open("NP.txt") as data:
        rows = list(csv.reader(io.TextIOWrapper(data, encoding="utf-8"), delimiter="\t"))

    admin = {
        (row[7], *row[10 : 10 + int(row[7][-1])]): row[1]
        for row in rows
        if row[7] in {"ADM1", "ADM2", "ADM3"}
    }
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    count = 0
    for row in sorted(rows, key=lambda row: int(row[0])):
        place_id, name, ascii_name, alternate, lat, lon, feature_class, kind, country = row[:9]
        population, timezone = row[14], row[17]
        # Border entries assigned to another country's timezone require manual verification.
        if feature_class != "P" or country != "NP" or timezone != "Asia/Kathmandu":
            continue
        if kind not in POPULATED and not (kind == "PPLL" and (alternate or int(population))):
            continue
        context = list(
            dict.fromkeys(
                label
                for level in (3, 2, 1)
                if (label := admin.get((f"ADM{level}", *row[10 : 10 + level]))) and label != name
            )
        )
        aliases = sorted({alias for alias in alternate.split(",") if supported_alias(alias)})
        writer.writerow(
            (
                place_id,
                name,
                ascii_name,
                ",".join(aliases),
                lat,
                lon,
                timezone,
                " · ".join(context),
                population,
            )
        )
        count += 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with (
        OUTPUT.open("wb") as target,
        gzip.GzipFile(filename="", fileobj=target, mode="wb", mtime=0) as compressed,
    ):
        compressed.write(output.getvalue().encode("utf-8"))
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    print(f"Wrote {build(parser.parse_args().archive)} Nepal birthplace records")
