"""Typed conceptual applicability. A rule always matches one fact."""

from typing import Annotated, Literal
from unicodedata import normalize

from pydantic import Field, field_validator

from app.calc.dasha import DashaLevel, DashaLord
from app.calc.nakshatra import NAKSHATRA_NAMES
from app.knowledge.provenance import Digest, Key, Label, Language, Record, Version

Planet = Literal["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
Sign = Literal[
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]
House = Annotated[int, Field(strict=True, ge=1, le=12)]
Pada = Annotated[int, Field(strict=True, ge=1, le=4)]


class PlanetGeneral(Record):
    topic: Literal["planet_general"]
    planet: Planet


class SignGeneral(Record):
    topic: Literal["sign_general"]
    sign: Sign


class HouseGeneral(Record):
    topic: Literal["house_general"]
    house: House


class PlanetInHouse(Record):
    topic: Literal["planet_in_house"]
    planet: Planet
    house: House


class PlanetInSign(Record):
    topic: Literal["planet_in_sign"]
    planet: Planet
    sign: Sign


class NakshatraTarget(Record):
    body: Planet
    nakshatra: Label

    @field_validator("nakshatra")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if value not in NAKSHATRA_NAMES:
            raise ValueError("Unknown Nakshatra")
        return value


class NakshatraRule(NakshatraTarget):
    topic: Literal["nakshatra"]


class PadaRule(NakshatraTarget):
    topic: Literal["pada"]
    pada: Pada


class DashaRule(Record):
    topic: Literal["dasha"]
    method: Literal["vimshottari-v1"]
    level: DashaLevel
    lord: DashaLord
    parent_lord: DashaLord | None = None


Applicability = Annotated[
    PlanetGeneral
    | SignGeneral
    | HouseGeneral
    | PlanetInHouse
    | PlanetInSign
    | NakshatraRule
    | PadaRule
    | DashaRule,
    Field(discriminator="topic"),
]
Topic = Literal[
    "planet_general",
    "sign_general",
    "house_general",
    "planet_in_house",
    "planet_in_sign",
    "nakshatra",
    "pada",
    "dasha",
]


class Locator(Record):
    chapter: Label
    page: Label
    canvas: Label
    verse: Label | None = None
    image_sha256: Digest


class Chunk(Record):
    key: Key
    revision: Version
    language: Language
    locator: Locator
    applicability: Applicability
    text: Annotated[str, Field(min_length=1, max_length=6000)]
    content_sha256: Digest

    @field_validator("text", mode="before")
    @classmethod
    def canonicalize_text(cls, value: object) -> object:
        if isinstance(value, str):
            clean = normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n")).strip()
            if any(ord(char) < 32 and char != "\n" for char in clean):
                raise ValueError("Unexpected control character in chunk text")
            return clean
        return value
