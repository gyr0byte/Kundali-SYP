"""Conservative local resolution of a single knowledge topic."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from unicodedata import category, normalize

from pydantic import TypeAdapter

from app.ai.embeddings import EmbeddingQuery
from app.api.schemas.chart import ChartSnapshotResponse, SnapshotResponse
from app.api.schemas.dasha import DashaResponse
from app.calc.facts import ChartFactPlacement
from app.calc.nakshatra import NAKSHATRA_NAMES
from app.db.models.profile import TimeCertainty
from app.knowledge.chunking import Planet, Sign, Topic
from app.knowledge.provenance import Language
from app.knowledge.retrieval import DashaEvidence, Evaluation, PlacementEvidence, Search

_PLANET = TypeAdapter(Planet)
_SIGN = TypeAdapter(Sign)


@dataclass(frozen=True, slots=True)
class AuthorizedEvidence:
    """Local projection from server-side chart results after the caller checked ownership."""

    placements: tuple[PlacementEvidence, ...] = ()
    dashas: tuple[DashaEvidence, ...] = ()
    evaluation: Evaluation | None = None
    current_dasha_lookup: bool = False


def project_authorized_evidence(
    snapshot: SnapshotResponse,
    dasha: DashaResponse | None = None,
    *,
    current_at: datetime | None = None,
) -> AuthorizedEvidence:
    if not isinstance(snapshot, ChartSnapshotResponse) or snapshot.schema_version != 1:
        return AuthorizedEvidence()
    certainty: Literal["exact", "approximate"] = (
        "approximate" if snapshot.time_certainty == TimeCertainty.APPROXIMATE else "exact"
    )
    placements = tuple(
        PlacementEvidence(
            planet=_PLANET.validate_python(fact.planet),
            house=fact.house,
            sign=_SIGN.validate_python(fact.sign),
            nakshatra=fact.nakshatra,
            pada=fact.pada,
            certainty=certainty,
        )
        for fact in snapshot.chart.facts
        if isinstance(fact, ChartFactPlacement)
    )
    if (
        dasha is None
        or dasha.snapshot_id != snapshot.snapshot_id
        or dasha.chart_id != snapshot.chart.chart_id
        or dasha.time_certainty != certainty
        or dasha.is_conditional != (certainty == "approximate")
        or dasha.lookup.status != "active"
        or dasha.lookup.as_of is None
        or dasha.lookup.as_of.utcoffset() is None
        or dasha.lookup.periods is None
    ):
        return AuthorizedEvidence(placements)
    evaluation = Evaluation(snapshot_id=snapshot.snapshot_id, instant=dasha.lookup.as_of)
    active = dasha.lookup.periods
    periods = (
        (active.mahadasha, None),
        (active.antardasha, active.mahadasha.lord),
        (active.pratyantardasha, active.antardasha.lord),
    )
    dashas = tuple(
        DashaEvidence(
            evaluation=evaluation,
            method=dasha.method,
            level=period.level,
            lord=period.lord,
            parent_lord=parent,
            certainty=certainty,
        )
        for period, parent in periods
    )
    return AuthorizedEvidence(placements, dashas, evaluation, current_at == evaluation.instant)


Status = Literal["resolved", "ambiguous", "unsupported"]
Scope = Literal["general", "chart"]


@dataclass(frozen=True, slots=True)
class IntentResolution:
    status: Status
    reason: str | None = None
    scope: Scope | None = None
    intent: EmbeddingQuery | None = None


def _words(value: str) -> list[str]:
    local = normalize("NFKC", value).casefold()
    return "".join(char if category(char)[0] in "LMN" else " " for char in local).split()


def _alias_group(names: list[str], aliases: list[str]) -> dict[tuple[str, ...], str]:
    return {
        tuple(_words(alias)): name
        for name, group in zip(names, aliases, strict=True)
        for alias in (name, *group.split("|"))
    }


_PLANETS = _alias_group(
    ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"],
    [
        "सूर्य|surya",
        "चन्द्र|चन्द्रमा|चंद्र|चंद्रमा|chandra|chandrama",
        "मंगल|मङ्गल|mangal",
        "बुध|budh|budha",
        "बृहस्पति|गुरु|brihaspati|guru",
        "शुक्र|shukra|sukra",
        "शनि|shani|sani",
        "राहु|rahu",
        "केतु|ketu",
    ],
)
_SIGNS = _alias_group(
    [
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
    ],
    [
        "मेष|mesh|mesha",
        "वृषभ|वृष|vrishabh|vrishabha",
        "मिथुन|mithun|mithuna",
        "कर्कट|कर्क|karkat|karka",
        "सिंह|simha|singha",
        "कन्या|kanya",
        "तुला|tula",
        "वृश्चिक|vrishchik|vrischika",
        "धनु|dhanu",
        "मकर|makar|makara",
        "कुम्भ|कुंभ|kumbha",
        "मीन|meen|mina",
    ],
)
_NAKSHATRAS = _alias_group(
    NAKSHATRA_NAMES,
    [
        "अश्विनी|aswini|ashvini",
        "भरणी|bharani",
        "कृत्तिका|कृतिका|kritika",
        "रोहिणी|rohini",
        "मृगशिरा|मृगशीर्ष|mrigashirsha",
        "आर्द्रा|ardra",
        "पुनर्वसु|punarvasu",
        "पुष्य|pushya",
        "आश्लेषा|ashlesha",
        "मघा|magha",
        "पूर्व फाल्गुनी|purva falguni",
        "उत्तर फाल्गुनी|uttar falguni",
        "हस्त|hasta",
        "चित्रा|chitra",
        "स्वाती|swati",
        "विशाखा|visakha",
        "अनुराधा|anuradha",
        "ज्येष्ठा|jyeshta",
        "मूल|moola",
        "पूर्व आषाढा|पूर्वाषाढा",
        "उत्तर आषाढा|उत्तराषाढा",
        "श्रवण|sravana",
        "धनिष्ठा|dhanistha",
        "शतभिषा|shatabhishak",
        "पूर्व भाद्रपद|पूर्वभाद्रपद",
        "उत्तर भाद्रपद|उत्तरभाद्रपद",
        "रेवती|revathi",
    ],
)
_LEVELS = _alias_group(
    ["MD", "AD", "PD"],
    [
        "mahadasha|mahadashaa|महादशा",
        "antardasha|antardasa|अन्तर्दशा|अंतर्दशा",
        "pratyantardasha|pratyantar|प्रत्यन्तर्दशा|प्रत्यंतरदशा",
    ],
)
_NUMBERS = _alias_group(
    [str(i) for i in range(1, 13)],
    [
        "first|one|पहिलो|pahilo|ek",
        "second|two|दोस्रो|dosro|dui",
        "third|three|तेस्रो|tesro|tin",
        "fourth|four|चौथो|chauttho|char",
        "fifth|five|पाँचौँ|पाँचौं|पाँचौ|panchau|pancham|paanch",
        "sixth|six|छैटौँ|chhaitau|chha",
        "seventh|seven|सातौँ|satau|sat",
        "eighth|eight|आठौँ|aathau|aath",
        "ninth|nine|नवौँ|nawau|nau",
        "tenth|ten|दसौँ|दशौँ|dasau|das",
        "eleventh|eleven|एघारौँ|egharau",
        "twelfth|twelve|बाह्रौँ|bahrau",
    ],
)
_WORDS = {
    "chart": "my mine chart horoscope kundali kundli mero meri afno janma natal "
    "मेरो मेरी आफ्नो कुण्डली कुन्डली जन्म",
    "current": "current active now ahile aile अहिले हाल चलिरहेको",
    "general": "meaning means define concept general generally symbolism artha samanya "
    "अर्थ परिभाषा सामान्य प्रतीक",
    "planet": "planet graha grah ग्रह",
    "sign": "sign rashi raashi rasi राशि राशी",
    "house": "house bhava bhav bhaav भाव घर",
    "nakshatra": "nakshatra naksatra nakshatram नक्षत्र",
    "pada": "pada paada quarter पद पाद चरण charan",
    "dasha": "dasha dasa vimshottari vimshodari दशा विंशोत्तरी विम्शोत्तरी",
    "ambiguous": "or versus vs not होइन वा कि hoina athawa",
    "grammar": "what which where is are the a an in of for about tell me please does mean "
    "ho cha chha kun kaha ma ko ke k bhanne bhaneko bhannus pani "
    "के कुन कहाँ हो छ को मा बारे भनेको भन्नुहोस् बताउनुहोस् र and",
}
_LEXICON = {
    alias: (kind, value)
    for kind, aliases in (
        ("planet_name", _PLANETS),
        ("sign_name", _SIGNS),
        ("star_name", _NAKSHATRAS),
        ("level", _LEVELS),
        ("number", _NUMBERS),
    )
    for alias, value in aliases.items()
} | {(word,): (kind, word) for kind, words in _WORDS.items() for word in words.split()}
_INFLECTED_KINDS = {
    "planet_name",
    "sign_name",
    "star_name",
    "level",
    "planet",
    "sign",
    "house",
    "nakshatra",
    "pada",
    "dasha",
    "chart",
}


def _lookup(words: tuple[str, ...]) -> tuple[str, str] | None:
    if match := _LEXICON.get(words):
        return match
    for ending in ("लाई", "को", "मा", "का", "की", "ले"):
        if words[-1].endswith(ending):
            match = _LEXICON.get((*words[:-1], words[-1][: -len(ending)]))
            if match is not None and match[0] in _INFLECTED_KINDS:
                return match
    return None


def _parse(question: str) -> dict[str, set[str]] | None:
    if not 0 < len(question) <= 300:
        return None
    local = normalize("NFKC", question)
    if "@" in local or re.search(r"\d[.:/-]\d", local):
        return None
    words = _words(local)
    result: dict[str, set[str]] = {}
    position = 0
    while position < len(words):
        word = words[position]
        for width in range(min(3, len(words) - position), 0, -1):
            match = _lookup(tuple(words[position : position + width]))
            if match is not None:
                break
        else:
            if not word.isdecimal() or len(word) > 2 or not 1 <= int(word) <= 12:
                return None
            width, match = 1, ("number", str(int(word)))
        kind, value = match
        result.setdefault(kind, set()).add(value)
        position += width
    return result


def _resolved(scope: Scope, **target: object) -> IntentResolution:
    return IntentResolution(
        "resolved",
        scope=scope,
        intent=EmbeddingQuery.model_validate({"targets": [target]}),
    )


def resolve_intent(
    question: str,
    evidence: AuthorizedEvidence = AuthorizedEvidence(),
) -> IntentResolution:
    parsed = _parse(question)
    if not parsed:
        return IntentResolution("unsupported", "outside_supported_vocabulary")
    ambiguous = IntentResolution("ambiguous", "needs_single_concept_or_context")
    entity_kinds = ("planet_name", "sign_name", "star_name", "number", "level")
    if "ambiguous" in parsed or any(len(parsed.get(kind, ())) > 1 for kind in entity_kinds):
        return ambiguous
    planet, sign, star, number, level = (
        next(iter(parsed.get(kind, ())), None) for kind in entity_kinds
    )
    scopes = set(parsed) & {"house", "sign", "nakshatra", "pada", "dasha"}
    if star:
        scopes.add("nakshatra")
    if sign:
        scopes.add("sign")
    if level:
        scopes.add("dasha")
    if "pada" in scopes:
        scopes.discard("nakshatra")
    if len(scopes) > 1:
        return ambiguous
    topic = next(iter(scopes), None)
    if number and topic not in {"house", "pada"}:
        return ambiguous
    if not set(parsed) & {"chart", "current"}:
        if topic in {"dasha", "pada", "nakshatra"}:
            return IntentResolution("unsupported", "requires_chart_context")
        if "general" not in parsed and not (
            parsed.get("grammar", set()) & {"what", "के", "ke", "bhaneko", "भनेको"}
        ):
            return ambiguous
        if planet and topic is None:
            return _resolved("general", topic="planet_general", planet=planet)
        if sign and not planet:
            if sign == "Cancer" and "sign" not in parsed and "cancer" in _words(question):
                return ambiguous
            return _resolved("general", topic="sign_general", sign=sign)
        if topic == "house" and number and not planet:
            return _resolved("general", topic="house_general", house=int(number))
        return ambiguous

    unavailable = IntentResolution("unsupported", "authorized_evidence_unavailable")
    mismatch = IntentResolution("unsupported", "assertion_not_supported_by_chart")
    if topic == "dasha":
        if level is None:
            return ambiguous
        if "current" in parsed and not evidence.current_dasha_lookup:
            return unavailable
        active = [
            item
            for item in evidence.dashas
            if item.level == level
            and item.evaluation == evidence.evaluation
            and item.evaluation.instant.utcoffset() is not None
        ]
        if len(active) != 1:
            return unavailable
        dasha = active[0]
        if planet and planet != dasha.lord:
            return mismatch
        return _resolved(
            "chart",
            topic="dasha",
            method=dasha.method,
            level=dasha.level,
            lord=dasha.lord,
            parent_lord=dasha.parent_lord,
        )
    if topic is None or planet is None or (topic == "pada" and number and int(number) > 4):
        return ambiguous
    placements = [
        fact
        for fact in evidence.placements
        if fact.planet == planet and fact.certainty != "uncertain"
    ]
    if len(placements) != 1:
        return unavailable
    fact = placements[0]
    if topic == "house" and fact.house is not None:
        if number and int(number) != fact.house:
            return mismatch
        return _resolved("chart", topic="planet_in_house", planet=planet, house=fact.house)
    if topic == "sign" and fact.sign is not None:
        if sign and sign != fact.sign:
            return mismatch
        return _resolved("chart", topic="planet_in_sign", planet=planet, sign=fact.sign)
    if topic in {"nakshatra", "pada"} and fact.nakshatra in NAKSHATRA_NAMES:
        if star and star != fact.nakshatra:
            return mismatch
        if topic == "nakshatra":
            return _resolved("chart", topic=topic, body=planet, nakshatra=fact.nakshatra)
        if fact.pada is not None:
            if number and int(number) != fact.pada:
                return mismatch
            return _resolved(
                "chart", topic="pada", body=planet, nakshatra=fact.nakshatra, pada=fact.pada
            )
    return unavailable


def canonical_keyword_text(intent: EmbeddingQuery) -> str:
    return " ".join(
        str(value)
        for target in intent.targets
        for field, value in target.model_dump(exclude_none=True).items()
        if field not in {"topic", "method"}
    )


def intent_search(
    intent: EmbeddingQuery,
    evidence: AuthorizedEvidence,
    *,
    query: str,
    languages: tuple[Language, ...] = ("en", "ne"),
    limit: int = 5,
) -> Search:
    topics: tuple[Topic, ...] = tuple(dict.fromkeys(target.topic for target in intent.targets))
    return Search(
        query=query,
        topics=topics,
        languages=languages,
        targets=intent.targets,
        placements=evidence.placements,
        dashas=evidence.dashas,
        evaluation=evidence.evaluation,
        limit=limit,
    )
