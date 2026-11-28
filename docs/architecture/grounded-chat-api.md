# Authenticated grounded chat API

`POST /api/v1/chat` is a grounded, locally selected, template-rendered
assistant. It reuses the multilingual intent resolver, structured grounding
validator and trusted rendering. The serving path uses canonical keyword
retrieval and requires no Gemini, Vertex or embedding credentials. It has no
conversation history, message storage, generation logs or chat tables.

## Contract

Send JSON with a bearer access token. The account must have `chat:use`.
`question` accepts 1–300 characters after trimming. `language` is `en`
(default) or `ne`. `snapshot_id` is an optional saved snapshot UUID. The API
rejects extra request fields, duplicate JSON keys and bodies over 4 KiB.
Chart facts, Dasha facts, citations and approvals are server inputs only.

Example deterministic question:

```json
{
  "question": "Which house is my Moon in?",
  "language": "en",
  "snapshot_id": "00000000-0000-0000-0000-000000000009"
}
```

Example response for a synthetic snapshot:

```json
{
  "language": "en",
  "outcome": "answered",
  "answer": "Moon is in house 5.",
  "claims": [{
    "kind": "chart_fact",
    "target": {"topic": "planet_in_house", "planet": "Moon", "house": 5},
    "text": "Moon is in house 5.",
    "conditional": false,
    "citation_id": null
  }],
  "citations": [],
  "disclaimer": "Astrology is a traditional interpretive practice. Science has not established it as a way to predict outcomes.",
  "snapshot": {
    "snapshot_id": "00000000-0000-0000-0000-000000000009",
    "is_current_profile_revision": true,
    "time_certainty": "exact"
  },
  "evaluated_at": null
}
```

A general question can omit the chart, for example
`{"question":"चन्द्रमा के हो?","language":"ne"}`. With no display-approved
passage, the response is:

```json
{
  "language": "ne",
  "outcome": "insufficient_knowledge",
  "answer": "यस विषयको व्याख्या गर्न पर्याप्त स्वीकृत सामग्री उपलब्ध छैन।",
  "claims": [],
  "citations": [],
  "disclaimer": "ज्योतिष एउटा परम्परागत व्याख्या पद्धति हो। यसबाट भविष्यका परिणाम थाहा पाउन सकिन्छ भन्ने वैज्ञानिक प्रमाण स्थापित भएको छैन।",
  "snapshot": null,
  "evaluated_at": null
}
```

`answer` and claim text are plain text. An interpretation includes one
applicable passage and at most one citation. Public citation fields are the
immutable citation ID, source version, language, tier, title, author, edition,
chapter, page, verse and attribution. Internal provenance and review notes
stay local. Approximate-time answers have visibly conditional wording and
`conditional: true`. General answers and fallbacks can have no snapshot
metadata. Answered Dasha responses include the server's evaluation instant.

Every chat response uses `Cache-Control: no-store`. A missing or non-owned
snapshot returns the same HTTP 404 with `{"detail":"Item not found"}`.
Other transport outcomes include 401 or 403 for authentication or permission
failure, 400 for invalid body framing, 413 for request size, 422 for invalid
JSON or fields, 429 with `Retry-After` for rate limiting, and 503 for
database or unreadable snapshot failures. Invalid payloads and operational
errors return sanitized diagnostics.

| HTTP 200 outcome | Meaning |
| --- | --- |
| `answered` | A validated fact or an applicable display-approved passage. |
| `snapshot_required` | The requested chart topic requires a saved snapshot. |
| `uncertain_birth_time` | The saved unknown-time chart cannot support the requested fact. |
| `dasha_unavailable` | The snapshot cannot supply an active period at the server's instant. |
| `unsupported_request` | The request is ambiguous, outside the supported intent vocabulary, or needs a safety abstention. |
| `insufficient_knowledge` | No applicable display-approved passage is available through the final publication check. |
| `grounding_failed` | Structured selection or evidence could not be verified. |
| `restricted_request` | The request or selected material violates a safety rule. |
| `crisis_support` | Localized encouragement to seek immediate human support. |
| `provider_failure`, `provider_timeout` | Local selection could not complete. |

## Ownership, publication and selection

Snapshot lookup joins the current birth profile by the authenticated
owner before loading and decrypting the persisted facts. General and blocked
requests with a supplied UUID check ownership without decryption. Chart
answers use the identified immutable snapshot even if the profile has
changed. The API verifies ownership and the profile revision again before
responding. Active Dasha uses one server-controlled UTC instant for lookup,
grounding and response metadata. Unknown-time snapshots cannot ground natal
placements or Dasha claims.

Direct questions about supported calculated placements or active Dasha use
the fact path. General concepts and chart questions asking for an explanation
use the knowledge path. Retrieval intersects typed applicability with enabled,
editorially approved and rights-cleared production rows. Before ranking,
candidates must also match the server's exact-text display approval for that
citation ID, language and content SHA-256. There are no production display
approvals. Drafts and pending classical candidates remain unpublished.

The local selector verifies that options match the resolved target and
retrieved evidence. It prefers the requested language, then a rule specific
to the verified target, then canonical keyword rank. It abstains when it
cannot defend a selection. Grounding and passage safety run before
rendering. The service releases its initial read transaction before
selection, then performs a fresh read of the selected citation and its
source. The fresh read must match the original result, including its
content and metadata, and still satisfy publication and display approval.
This final check uses the runtime's read-only knowledge privileges. A
concurrent change committed after that check applies to later responses.
There is no locking or invalidation of a response already in flight.

## Resource and verification limits

Each request accepts up to 16 stored natal facts for projection. The
retrievable set is scoped to at most 64 approved citation IDs, 1,200
characters per passage and six ranked options. The API selects one claim,
and bounds the serialized response at 12 KiB. The process-local rate
limiter permits ten chat requests per authenticated account per minute.
Workers have independent counters, counters clear on restart, and this
milestone adds no shared quota, per-IP chat gate or ingress timeout. A
production deployment still needs those controls where appropriate.

Offline verification passed 252 focused tests, including 34 chat API
cases. It used real bearer authentication, encrypted snapshots and
publication checks with synthetic in-memory SQLite data.

The live Neon development smoke test passed using the restricted
`kundali_dev_app` role, verified TLS, required channel binding and
Alembic revision `0007_knowledge_embeddings`. It verified snapshot
ownership, historical identity, conditional responses, active Dasha,
bilingual rendering, Romanized Nepali input, safety fallbacks and
account-level rate limiting. All 22 sampled chat responses included
`Cache-Control: no-store`. The external HTTP guard recorded zero AI
requests. No chat messages were persisted.

The 17 HTTP 200 responses had an end-to-end median of 845 ms and a range
of 387–1,305 ms. These sequential timings include localhost HTTP, database
round trips and application work. Local processing was not measured
separately. The live run used the empty display-approval registry.
Approved-passage rendering and publication withdrawal were verified
offline. Deployment concurrency, throughput and real-world multilingual
or safety performance remain unverified.

All four synthetic profiles were deleted and their snapshots returned
HTTP 404. Two synthetic accounts and their audit histories remain. The
localhost backend was stopped after cleanup.
