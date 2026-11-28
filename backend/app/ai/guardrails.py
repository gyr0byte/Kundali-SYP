"""Conservative local screening for interpretation requests and passages."""

import re
from dataclasses import dataclass
from enum import StrEnum
from unicodedata import category, normalize

MAX_QUESTION_CHARS = 300  # Matches the intent resolver's input boundary.


class SafetyAction(StrEnum):
    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    ABSTAIN = "abstain"
    CRISIS = "crisis"


class SafetyCode(StrEnum):
    CLEAR = "clear"
    INVALID_INPUT = "invalid_input"
    UNCERTAIN_RISK = "uncertain_risk"
    CRISIS_SUPPORT = "crisis_support"
    HARM_PREDICTION = "harm_prediction"
    MEDICAL_DIRECTIVE = "medical_directive"
    FINANCIAL_DIRECTIVE = "financial_directive"
    LEGAL_DIRECTIVE = "legal_directive"
    FEAR_OR_COERCION = "fear_or_coercion"
    PREDICTIVE_CERTAINTY = "predictive_certainty"
    INSTRUCTION_OVERRIDE = "instruction_override"
    PRIVATE_EVIDENCE_REQUEST = "private_evidence_request"


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    action: SafetyAction
    code: SafetyCode


def _tokens(text: str) -> str:
    normal = normalize("NFKC", text).casefold().replace("’", "'")
    normal = normal.replace("can't", "cannot").replace("won't", "will not")
    normal = re.sub(r"n't\b", " not", normal)
    # Join deliberately split ASCII words and remove zero-width formatting controls.
    normal = re.sub(
        r"(?<![a-z])(?:[a-z][ ._*-]+){2,}[a-z](?![a-z])",
        lambda match: re.sub(r"[^a-z]", "", match[0]),
        normal,
    )
    cleaned = "".join(
        char if category(char)[0] in "LMN" else " " for char in normal if category(char) != "Cf"
    )
    return f" {' '.join(cleaned.split())} "


def _has(tokens: str, phrases: str) -> bool:
    return any(f" {phrase} " in tokens for phrase in phrases.split("|"))


_SELF_HARM = (
    "suicide|suicidal|self harm|selfharm|kill myself|end my life|hurt myself|want to die|"
    "do not want to live|do not want to be alive|kill themselves|wants to die|want to end it all|"
    "आत्महत्या|आत्महानी|आत्महानि|आत्महत्या गर्न|मर्न मन|बाँच्न मन छैन|"
    "आफूलाई मार्न|आफैलाई चोट|ज्यान लिन|ज्यान फाल्न|"
    "atmahatya|aatmahatya|marna man|bachna man chaina|afulai marna|afailai marna"
)
_NEGATED_CRISIS = (
    "i am not suicidal|i m not suicidal|i do not want to kill myself|"
    "i do not want to die|म आत्महत्या गर्न चाहन्नँ|म आत्महत्या गर्दिनँ|"
    "ma atmahatya garna chahanna|ma marna chahanna"
)
_HARM = (
    "death|die|died|dying|fatal|lifespan|end of my life|accident|accidents|crash|"
    "pass away|how long will i live|serious illness|serious disease|cancer|heart attack|"
    "harm me|get hurt|"
    "मृत्यु|मर्छु|मर्ने|मर्छ|मरण|आयु|दुर्घटना|क्यान्सर|गम्भीर रोग|हृदयाघात|"
    "mrityu|mrityo|mritu|marne|marchu|marchha|marnu|ayu|durghatana|durghatna|bimar"
)
_MEDICAL = (
    "diagnose|diagnosis|treatment|medicine|medication|medications|surgery|dose|vaccine|"
    "cure|doctor|chemotherapy|औषधि|औषधी|उपचार|रोग|शल्यक्रिया|डाक्टर|"
    "ausadhi|aushadhi|aushadi|dabai|upachar|dawai|roga|rog"
)
_FINANCIAL = (
    "invest|investment|investments|stocks|stock|shares|trading|financial advice|"
    "crypto|loan|borrow|bet|लगानी|सेयर|शेयर|ऋण|कर्जा|जुवा|lagani|share|rin|karja"
)
_LEGAL = (
    "lawsuit|sue|settlement|divorce|legal advice|legal action|contract|court|lawyer|"
    "अदालत|मुद्दा|सम्बन्धविच्छेद|सम्बन्ध विच्छेद|कानुनी|कानून|"
    "mudda|adalat|kanuni|kanuni salah|sambandha bichhed"
)
_FEAR = (
    "curse|cursed|doom|doomed|evil spell|black magic|sacrifice|force|threaten|"
    "श्राप|शाप|अभिशाप|अनिष्ट|कालो जादु|कालो जादू|बलि|धम्की|shrap|sarap|shraap|anista"
)
_CERTAINTY = (
    "guarantee|guaranteed|with certainty|absolutely certain|100 percent|100 sure|"
    "hundred percent|unavoidable|inevitable|definitely|पक्का|निश्चित|ग्यारेन्टी|"
    "शतप्रतिशत|सय प्रतिशत|pakka|nischit|nischita|guarantee dinu"
)
_FORECAST = (
    "predict|prediction|predictions|forecast|future|will|going to|happen|when|"
    "भविष्य|भविष्यवाणी|हुन्छ|हुनेछ|कहिले|कति बेला|बताऊ|बताइदेऊ|"
    "bhavishyabani|bhavishyawani|kahile|kaile|huncha|hunchha|hola"
)
_PERSONAL = "my|me|mine|i|myself|for us|our|मेरो|मलाई|म|मेरा|मेरोमा|हाम्रो|mero|malai|ma|merai|hamro"
_DIRECTIVE = (
    "should|must|best day|best time|tell me|advise|recommend|stop taking|take|"
    "skip|buy|sell|prescribe|sign my|sign the contract|गरूँ|गरु|गरौं|गर्नु|गर्नुपर्छ|गर्नु पर्छ|"
    "खानु|खाऊँ|छोडूँ|किनूँ|सल्लाह|garu|garnu|garna|khanu|khau|kindim|sallah"
)
_EDUCATION = (
    "what is|what are|what does|definition|meaning|history|symbolism|evidence|"
    "can astrology|can a horoscope|how does astrology|why can astrology|"
    "के हो|अर्थ|इतिहास|परम्परा|प्रमाण|ज्योतिषले किन|"
    "ke ho|k ho|artha|itihas|parampara|baneko|bhaneko"
)
_RISK_LIMITATION = (
    "cannot predict|can not predict|does not predict|do not predict|"
    "cannot diagnose|can not diagnose|does not diagnose|no scientific evidence|"
    "भविष्यवाणी गर्न सक्दैन|भन्न सक्दैन|निदान गर्न सक्दैन|"
    "bhavishyabani garna sakdaina|bhanna sakdaina"
)
_ZODIAC_CANCER = (
    "cancer sign|sign of cancer|cancer rashi|cancer राशि|cancer is a sign|"
    "moon in cancer|sun in cancer|mars in cancer|mercury in cancer|jupiter in cancer|"
    "venus in cancer|saturn in cancer|rahu in cancer|ketu in cancer"
)


def _removing(tokens: str, phrases: str) -> str:
    for phrase in phrases.split("|"):
        tokens = tokens.replace(f" {phrase} ", " ")
    return tokens


def _security_code(words: str) -> SafetyCode | None:
    exposure = _has(
        words,
        "show|reveal|dump|extract|expose|print|return|send|fetch|देखाऊ|देखाउनु|पठाऊ|निकाल|"
        "dekhau|pathau|nikala",
    )
    private = _has(
        words,
        "private evidence|private data|someone else|another user|other user|others chart|"
        "someone else s|birth coordinates|raw birth|api key|password|access token|"
        "api keys|environment variables|secret|secrets|credentials|"
        "गोप्य|निजी विवरण|अरूको|अर्काको|जन्म विवरण|"
        "arka ko|aru ko|gopya|niji|janma bibaran",
    )
    if exposure and private:
        return SafetyCode.PRIVATE_EVIDENCE_REQUEST
    override = _has(
        words,
        "ignore|forget|disregard|override|bypass|disable|replace|go against|"
        "बिर्स|बिर्सनु|बेवास्ता|उल्लङ्घन|naman|birsa|bewasta",
    )
    instructions = _has(
        words,
        "instructions|instruction|rules|policy|guardrails|system|prompt|developer|"
        "निर्देशन|निर्देश|नियम|नीति|niyam|nirdesh",
    )
    if (override and instructions) or (
        exposure
        and _has(words, "system prompt|your prompt|developer instructions|hidden instructions")
    ):
        return SafetyCode.INSTRUCTION_OVERRIDE
    return None


def assess_input(question: str) -> SafetyDecision:
    words = _tokens(question[:MAX_QUESTION_CHARS])
    personal = _has(words, _PERSONAL)
    educational = _has(words, _EDUCATION)
    # First-person distress and reports of immediate risk take precedence over other blocks.
    crisis = _removing(words, _NEGATED_CRISIS)
    if _has(crisis, _SELF_HARM) and (
        not educational
        or personal
        or _has(crisis, "want|wants|right now|plan to|best way|quickest way|how to|मन|चाहन्छु")
    ):
        return SafetyDecision(SafetyAction.CRISIS, SafetyCode.CRISIS_SUPPORT)
    if len(question) > MAX_QUESTION_CHARS or not words.strip():
        return SafetyDecision(SafetyAction.ABSTAIN, SafetyCode.INVALID_INPUT)
    if code := _security_code(words):
        return SafetyDecision(SafetyAction.RESTRICTED, code)
    words = crisis  # The remaining clauses still go through all other risk checks.
    personal = _has(words, _PERSONAL)
    educational = _has(words, _EDUCATION)
    directive = _has(words, _DIRECTIVE)
    prediction = _has(words, _FORECAST)
    harmful_topic = _has(_removing(words, _ZODIAC_CANCER), _HARM)
    # A statement about limits is educational only when it makes no personal request.
    educational = (
        (educational or _has(words, _RISK_LIMITATION))
        and not (personal or directive)
        and not _has(words, "when|what date|will you|will there|कहिले|कति बेला|kahile|kaile")
    )
    if harmful_topic and not educational and (personal or prediction or directive):
        return SafetyDecision(SafetyAction.RESTRICTED, SafetyCode.HARM_PREDICTION)
    for vocabulary, code in (
        (_MEDICAL, SafetyCode.MEDICAL_DIRECTIVE),
        (_FINANCIAL, SafetyCode.FINANCIAL_DIRECTIVE),
        (_LEGAL, SafetyCode.LEGAL_DIRECTIVE),
        (_FEAR, SafetyCode.FEAR_OR_COERCION),
    ):
        if _has(words, vocabulary) and not educational and (personal or prediction or directive):
            return SafetyDecision(SafetyAction.RESTRICTED, code)
    if _has(words, _CERTAINTY) and (personal or prediction or directive):
        return SafetyDecision(SafetyAction.RESTRICTED, SafetyCode.PREDICTIVE_CERTAINTY)
    if not educational and (
        harmful_topic
        or any(_has(words, terms) for terms in (_MEDICAL, _FINANCIAL, _LEGAL, _FEAR, _CERTAINTY))
    ):
        return SafetyDecision(SafetyAction.ABSTAIN, SafetyCode.UNCERTAIN_RISK)
    return SafetyDecision(SafetyAction.ALLOWED, SafetyCode.CLEAR)


def passage_is_safe(text: str) -> bool:
    """Additional veto for approved exact-text passages. Editorial review is still required."""
    if (
        not text.strip()
        or len(text) > 6000
        or any(category(char) in {"Cc", "Cf"} and char != "\n" for char in text)
        or re.search(r"https?://|[<>]|\[[^\]]*\]\(", text, re.IGNORECASE)
    ):
        return False
    words = _tokens(text)
    harmful_topic = _has(_removing(words, _ZODIAC_CANCER), _HARM)
    # Educational carve-outs apply to questions only. A disclaimer cannot clear passage text.
    return (
        not harmful_topic
        and _security_code(words) is None
        and not any(
            _has(words, terms)
            for terms in (
                _SELF_HARM,
                _MEDICAL,
                _FINANCIAL,
                _LEGAL,
                _FEAR,
                _CERTAINTY,
                _FORECAST,
                "you will|you must|you should|must obey|तपाईंले गर्नुपर्छ|तपाईंलाई हुनेछ",
            )
        )
    )
