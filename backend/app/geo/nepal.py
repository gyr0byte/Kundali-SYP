"""Search the packaged GeoNames Nepal gazetteer without external requests."""

import csv
import gzip
import unicodedata
from functools import cache
from importlib.resources import files
from typing import NamedTuple

from pydantic import BaseModel

MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 80
RESULT_LIMIT = 12


class Birthplace(BaseModel, frozen=True):
    id: int
    name: str
    devanagari_names: tuple[str, ...]
    context: str
    latitude: float
    longitude: float
    timezone: str

    @property
    def profile_name(self) -> str:
        label = self.name
        for part in self.context.split(" · "):
            if part and len(label) + len(part) + 2 <= 200:
                label = f"{label}, {part}"
        return label


class _SearchEntry(NamedTuple):
    place: Birthplace
    primary: tuple[str, ...]
    aliases: tuple[str, ...]
    context: str
    population: int


def _normalize(value: str) -> str:
    # Latin accent folding must preserve Devanagari vowel signs and other marks.
    output = []
    latin = False
    for char in unicodedata.normalize("NFKD", value.casefold()):
        kind = unicodedata.category(char)
        if kind.startswith("M"):
            if not latin:
                output.append(char)
        elif kind.startswith(("L", "N")):
            latin = unicodedata.name(char, "").startswith("LATIN ")
            output.append(char)
        elif char not in "\u200c\u200d":
            latin = False
            output.append(" ")
    return " ".join("".join(output).split())


@cache
def _index() -> dict[int, _SearchEntry]:
    data = files("app.geo").joinpath("data", "nepal.tsv.gz")
    index = {}
    with data.open("rb") as raw, gzip.open(raw, "rt", encoding="utf-8", newline="") as table:
        for row in csv.reader(table, delimiter="\t"):
            ident, name, ascii_name, alt, lat, lon, timezone, context, population = row
            aliases = tuple(alt.split(",")) if alt else ()
            primary = tuple(dict.fromkeys((_normalize(name), _normalize(ascii_name))))
            place = Birthplace(
                id=int(ident),
                name=name,
                devanagari_names=tuple(
                    alias
                    for alias in (name, *aliases)
                    if any("\u0900" <= char <= "\u097f" for char in alias)
                ),
                context=context,
                latitude=float(lat),
                longitude=float(lon),
                timezone=timezone,
            )
            terms = (_normalize(alias) for alias in aliases)
            index[place.id] = _SearchEntry(
                place,
                primary,
                tuple(dict.fromkeys(term for term in terms if term)),
                _normalize(context),
                int(population),
            )
    return index


def resolve_birthplace(place_id: int) -> Birthplace | None:
    record = _index().get(place_id)
    return record.place if record else None


def validate_search_query(value: str) -> str:
    if (
        len(value.strip()) < MIN_QUERY_LENGTH
        or len(value) > MAX_QUERY_LENGTH
        or any(
            unicodedata.category(ch).startswith("C") and ch not in "\u200c\u200d" for ch in value
        )
        or not any(ch.isalpha() for ch in value)
    ):
        raise ValueError("Enter 2 to 80 characters including letters to search birthplaces")
    return _normalize(value)


def _rank(query: str, entry: _SearchEntry) -> int | None:
    if query in entry.primary:
        return 0
    if query in entry.aliases:
        return 1
    names = (*entry.primary, *entry.aliases)
    if any(name.startswith(query) for name in names):
        return 2
    if any(f" {query}" in name for name in names):
        return 3
    if any(
        query.startswith(f"{name} ") and f" {query[len(name) + 1 :]}" in f" {entry.context}"
        for name in names
    ):
        return 4
    return None


def search_birthplaces(value: str) -> list[Birthplace]:
    query = validate_search_query(value)
    matches = []
    for ident, entry in _index().items():
        rank = _rank(query, entry)
        if rank is not None:
            matches.append((rank, -entry.population, entry.primary[0], ident, entry.place))
    matches.sort(key=lambda match: match[:4])
    return [match[4] for match in matches[:RESULT_LIMIT]]
