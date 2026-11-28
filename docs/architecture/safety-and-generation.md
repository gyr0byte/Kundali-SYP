# Interpretation safety and bounded generation

## Input policy

`app.ai.guardrails.assess_input` normalizes English, Devanagari Nepali,
Romanized Nepali, and mixed text. It checks bounded phrases in context,
including markers of prediction, personal intent, directives, education and
negation. It recognizes some obfuscation such as zero-width characters and
separated ASCII letters. Crisis signals take priority over other restrictions.
Ambiguous high-risk requests abstain. A request that passes safety still has
to resolve through the existing intent resolver before it can reach a provider.

| Action | Decision codes |
| --- | --- |
| `allowed` | `clear` |
| `restricted` | `harm_prediction`, `medical_directive`, `financial_directive`, `legal_directive`, `fear_or_coercion`, `predictive_certainty`, `instruction_override`, `private_evidence_request` |
| `abstain` | `invalid_input`, `uncertain_risk` |
| `crisis` | `crisis_support` |

Fallbacks use fixed English and Nepali copy. Crisis responses prioritize
contacting a trusted person and local emergency help in immediate danger.
They skip reading content and the astrology disclaimer. Other responses
include a localized note about astrology's traditional use and the lack of
scientific evidence for predictive outcomes.

## Generation and output policy

`app.ai.generation.generate_reading` accepts the local question, the
server-authorized `GroundingEvidence` bundle, and an async
`GenerationProvider`. The caller still owns account authentication,
snapshot authorization, and current retrieval. The orchestrator resolves the
intent again from the question and supplied evidence and checks that it agrees
with the bundle. For a current Dasha lookup the caller also supplies
`current_at`, separately from the requested evaluation instant.

The initial mode is interpretation. It abstains when there are no applicable,
render-approved passages. A caller can explicitly select facts mode for a
chart question. That mode uses deterministic facts without citations to
knowledge. Both modes use the [grounding validator](grounding-validator.md).
For interpretation, a current retrieval match also needs an explicit
server-side display approval for the citation ID, exact content SHA-256 and
language. The passage must pass a separate safety veto. A valid citation or a
disclaimer cannot authorize unsafe content. No display approvals are
configured by this change.

The provider receives up to 12 numbered choices with a claim kind and the
typed concept. It receives no raw question, passage text, snapshot UUID,
evaluation timestamp, citation ID, or raw birth data. It returns only a JSON
object containing a `choices` array of distinct offered integers. The server
expands the chosen entries into the existing version 1 reading and validates
the whole reading again. The renderer uses fixed templates and exact approved
passages. Consumers must render passage fields as plain text. Approximate-time
claims carry a conditional flag and visible wording.

A malformed numeric selection can receive one correction. Its feedback
contains only `malformed_selection` and a fixed instruction for the JSON
shape. Prose, extra fields, unauthorized choice numbers, oversized payloads,
unsafe passages and failed grounding receive no correction. No partial claims
are returned. The two attempts share one timeout budget. The caller stops
waiting at the deadline and signals provider cancellation. Caller cancellation
propagates to the caller and signals provider cancellation. A provider that
ignores cancellation may continue work in the background. The adapter must
use cancellation-aware I/O and enforce its own transport timeouts.

| Result field | Values |
| --- | --- |
| Fallback | `unsupported_request`, `insufficient_knowledge`, `uncertain_birth_time`, `grounding_failed`, `provider_failure`, `provider_timeout`, `restricted_request`, `crisis_support` |
| Generation failure | `malformed_selection`, `output_policy_violation`, `unauthorized_choice`, `response_too_large`, `unsafe_passage`, `grounding_rejected` |
| Grounding code | Existing validator code when grounding failed |

## Limits

Phrase and context checks are conservative. They cannot reliably detect all
paraphrases, dialects, obfuscations, forms of distress, quoted speech, or
complex negation. Crisis detection is not a clinical assessment. Reviewed
passages can still be vetoed, and the veto cannot prove that arbitrary text is
safe. The human approval boundary, intent whitelist, numeric selection
envelope and trusted rendering remain necessary. Validation establishes
structured consistency and applicability, without proving semantic entailment
or translation quality. The templates retain some canonical astrology terms.
The [Gemini generation pilot](gemini-generation-pilot.md) exercises this
boundary with a pinned synthetic fixture. There is no production generation
route, display approval, publication, translation or frontend integration.
