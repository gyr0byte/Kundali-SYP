"""Server-authored copy and exact-text passage approvals."""

from dataclasses import dataclass
from enum import StrEnum

from app.ai.guardrails import passage_is_safe
from app.ai.schemas import (
    ActiveDashaClaim,
    ClaimKind,
    FactClaim,
    GeneralExplanation,
    Interpretation,
    Locale,
)
from app.knowledge.chunking import (
    Applicability,
    NakshatraRule,
    PadaRule,
    PlanetInHouse,
    PlanetInSign,
)
from app.knowledge.provenance import Digest, sha256
from app.knowledge.retrieval import Match


class FallbackCode(StrEnum):
    UNSUPPORTED_REQUEST = "unsupported_request"
    INSUFFICIENT_KNOWLEDGE = "insufficient_knowledge"
    UNCERTAIN_BIRTH_TIME = "uncertain_birth_time"
    GROUNDING_FAILED = "grounding_failed"
    PROVIDER_FAILURE = "provider_failure"
    PROVIDER_TIMEOUT = "provider_timeout"
    RESTRICTED_REQUEST = "restricted_request"
    CRISIS_SUPPORT = "crisis_support"
    SNAPSHOT_REQUIRED = "snapshot_required"
    DASHA_UNAVAILABLE = "dasha_unavailable"


_COPY: dict[FallbackCode, tuple[str, str]] = {
    FallbackCode.SNAPSHOT_REQUIRED: (
        "Select a saved Kundali chart to ask about your placements or Dasha.",
        "आफ्नो ग्रहस्थिति वा दशाबारे सोध्न सुरक्षित गरिएको कुण्डली छान्नुहोस्।",
    ),
    FallbackCode.DASHA_UNAVAILABLE: (
        "This chart has no active Dasha period at the evaluated time.",
        "गणना गरिएको समयमा यस कुण्डलीको कुनै दशा सक्रिय छैन।",
    ),
    FallbackCode.UNSUPPORTED_REQUEST: (
        "I couldn’t identify a supported Kundali question. Try asking about one planet, sign, "
        "house, or calculated placement.",
        "यो प्रश्न कुन विषयसँग सम्बन्धित हो भन्ने स्पष्ट भएन। कुनै एउटा ग्रह, राशि, भाव "
        "वा गणना गरिएको ग्रहस्थितिबारे सोध्नुहोस्।",
    ),
    FallbackCode.INSUFFICIENT_KNOWLEDGE: (
        "There isn’t enough approved material to explain this yet.",
        "यस विषयको व्याख्या गर्न पर्याप्त स्वीकृत सामग्री उपलब्ध छैन।",
    ),
    FallbackCode.UNCERTAIN_BIRTH_TIME: (
        "This question needs a birth time that supports the requested calculation.",
        "यो प्रश्नको उत्तर दिन आवश्यक गणनाका लागि जन्मसमय थाहा हुनुपर्छ।",
    ),
    FallbackCode.GROUNDING_FAILED: (
        "I couldn’t verify a response against the available facts and approved sources.",
        "उपलब्ध तथ्य र स्वीकृत स्रोतसँग उत्तर मिलेको पुष्टि गर्न सकिएन।",
    ),
    FallbackCode.PROVIDER_FAILURE: (
        "The interpretation service is temporarily unavailable. Please try again later.",
        "व्याख्या सेवा अहिले उपलब्ध छैन। कृपया केही समयपछि फेरि प्रयास गर्नुहोस्।",
    ),
    FallbackCode.PROVIDER_TIMEOUT: (
        "The interpretation service took too long to respond. Please try again later.",
        "व्याख्या सेवाले समयमै उत्तर दिन सकेन। कृपया केही समयपछि फेरि प्रयास गर्नुहोस्।",
    ),
    FallbackCode.RESTRICTED_REQUEST: (
        "Kundali can explain calculations and traditions. For decisions with serious "
        "consequences, seek qualified human help.",
        "कुण्डलीले गणना र परम्पराको व्याख्या गर्न सक्छ। गम्भीर असर पर्न सक्ने निर्णयका लागि "
        "सम्बन्धित विज्ञको सल्लाह लिनुहोस्।",
    ),
    FallbackCode.CRISIS_SUPPORT: (
        "I’m sorry things feel this hard. Please reach out to someone you trust now and "
        "ask them to stay with you. If you or someone else might be in immediate danger, "
        "contact local emergency services now or go to the nearest emergency department.",
        "यस्तो कठिन अवस्थामा एक्लै बस्नु पर्दैन। अहिले नै विश्वास लाग्ने व्यक्तिलाई सम्पर्क गरी "
        "साथमा बस्न भन्नुहोस्। तपाईं वा अरू कोही तत्काल जोखिममा हुनुहुन्छ भने स्थानीय "
        "आपत्कालीन सेवामा सम्पर्क गर्नुहोस् वा नजिकको अस्पतालको आकस्मिक कक्षमा जानुहोस्।",
    ),
}

_DISCLAIMER = (
    "Astrology is a traditional interpretive practice. Science has not established it "
    "as a way to predict outcomes.",
    "ज्योतिष एउटा परम्परागत व्याख्या पद्धति हो। यसबाट भविष्यका परिणाम थाहा पाउन सकिन्छ "
    "भन्ने वैज्ञानिक प्रमाण स्थापित भएको छैन।",
)

_CONDITIONAL = (
    "This result depends on the approximate birth time entered. ",
    "यो नतिजा तपाईंले दिनुभएको अनुमानित जन्मसमयमा आधारित छ। ",
)


@dataclass(frozen=True, slots=True, repr=False)
class PassageApproval:
    """Server-side approval of the exact passage for plain-text display."""

    citation_id: str
    content_sha256: Digest
    language: str


@dataclass(frozen=True, slots=True)
class RenderedClaim:
    text: str
    kind: ClaimKind
    target: Applicability
    conditional: bool
    citation_id: str | None = None
    passage: str | None = None
    passage_language: str | None = None


def fallback_text(code: FallbackCode, language: Locale) -> str:
    return _COPY[code][language == "ne"]


def disclaimer_text(language: Locale) -> str:
    return _DISCLAIMER[language == "ne"]


def passage_approval(match: Match) -> PassageApproval:
    return PassageApproval(match.citation_id, sha256(match.content.encode("utf-8")), match.language)


def _fact_text(basis: FactClaim, language: Locale) -> str:
    target = basis.target
    if isinstance(basis, ActiveDashaClaim):
        level = {"MD": "Mahadasha", "AD": "Antardasha", "PD": "Pratyantardasha"}[basis.target.level]
        if language == "ne":
            level = {"MD": "महादशा", "AD": "अन्तर्दशा", "PD": "प्रत्यन्तर्दशा"}[basis.target.level]
            text = f"छानिएको समयमा {basis.target.lord} को {level} चलिरहेको छ।"
            if basis.target.parent_lord:
                text += f" यो {basis.target.parent_lord} को मूल दशाअन्तर्गत पर्छ।"
        else:
            text = f"{basis.target.lord} is the {level} lord at the selected instant."
            if basis.target.parent_lord:
                text += f" The parent period is ruled by {basis.target.parent_lord}."
    elif isinstance(target, PlanetInHouse):
        text = (
            f"{target.planet} {target.house} औँ भावमा छ।"
            if language == "ne"
            else f"{target.planet} is in house {target.house}."
        )
    elif isinstance(target, PlanetInSign):
        text = (
            f"{target.planet} {target.sign} राशिमा छ।"
            if language == "ne"
            else f"{target.planet} is in {target.sign}."
        )
    elif isinstance(target, (NakshatraRule, PadaRule)):
        if isinstance(target, PadaRule):
            text = (
                f"{target.body} {target.nakshatra} नक्षत्रको {target.pada} औँ चरणमा छ।"
                if language == "ne"
                else f"{target.body} is in Pada {target.pada} of {target.nakshatra}."
            )
        else:
            text = (
                f"{target.body} {target.nakshatra} नक्षत्रमा छ।"
                if language == "ne"
                else f"{target.body} is in {target.nakshatra} Nakshatra."
            )
    else:
        raise ValueError("Unsupported fact template")
    return _CONDITIONAL[language == "ne"] + text if basis.certainty == "approximate" else text


def render_claim(
    claim: FactClaim | GeneralExplanation | Interpretation,
    language: Locale,
    passages: dict[str, Match],
    approvals: frozenset[PassageApproval],
) -> RenderedClaim | None:
    if isinstance(claim, (GeneralExplanation, Interpretation)):
        passage = passages.get(claim.citation_id)
        if (
            passage is None
            or passage_approval(passage) not in approvals
            or not passage_is_safe(passage.content)
        ):
            return None
        if isinstance(claim, GeneralExplanation):
            text = "परम्परागत व्याख्या" if language == "ne" else "Traditional explanation"
        else:
            text = _fact_text(claim.basis, language)
        return RenderedClaim(
            text=text,
            kind=claim.kind,
            target=claim.basis.target if isinstance(claim, Interpretation) else claim.target,
            conditional=passage.conditional,
            citation_id=passage.citation_id,
            passage=passage.content,
            passage_language=passage.language,
        )
    return RenderedClaim(
        _fact_text(claim, language), claim.kind, claim.target, claim.certainty == "approximate"
    )
