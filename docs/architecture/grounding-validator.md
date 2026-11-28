# Structured grounding validator

## Trust boundary

`app.ai.validator.validate_reading` accepts untrusted UTF-8 JSON and a
server-only `GroundingEvidence` bundle. The caller supplies the request locale,
resolved or abstaining intent, any owner-authorized snapshot, and the exact
matches returned for this request by current production retrieval. Active
Dasha requests also supply the expected snapshot and evaluation instant
independently of the derived Dasha response. The validator checks that these
identities agree. The caller remains responsible for authenticating the account,
checking snapshot ownership, and using current publication state when retrieving
and assembling the evidence. The validator performs no I/O.

Retrieval matches carry their original typed applicability metadata. Current
retrieval verifies enabled, approved, cleared production records before
constructing a match. A historical citation record cannot serve as a current
match. Do not deserialize model-provided citations, facts, or intent into the
server evidence bundle. A future serving endpoint must decide how to handle
rights withdrawal between retrieval and display.

## Response version 1

A reading has `schema_version`, `language` (`en` or `ne`), an optional
`snapshot_id`, and one to twelve claims. The JSON limit is 24 KiB. Unknown
fields, duplicate keys, non-JSON constants, malformed references and type
coercions are rejected.

| Claim | Required support |
| --- | --- |
| `chart_fact` | One authorized placement fact and a matching house, sign, Nakshatra, or Pada target. |
| `dasha_fact` | One active MD, AD, or PD fact with the same period ID, lord, immediate parent lord, certainty, and evaluation instant. The instant must fall inside the nested half-open periods. |
| `general_explanation` | A current retrieved citation that matches the requested planet, sign, or house concept. |
| `interpretation` | A valid exact-time fact claim and a current retrieved citation whose rule applies to that single fact. |
| `conditional_interpretation` | An approximate-time fact claim and a current retrieved citation that remains conditional for that fact. |
| `abstention` | One reason from the fixed vocabulary, consistent with the request's intent state. A reading with an abstention contains no other claims. |

Chart claims are bound to the enclosing snapshot UUID even when different
charts reuse an ID such as `f_moon`. The requested concept must match a
resolved intent target. Unknown-time Moon-only snapshots supply no natal or
active Dasha facts to this contract. Version 1 does not cover Lagna, raw
longitudes, initial Dasha balance, or standalone unknown-time lunar facts.

## Diagnostics

A successful result includes the validated reading. A failure supplies a stable
code and a zero-based claim index when it can identify a specific claim. No
partial reading or input values are included on failure.

| Code | Meaning |
| --- | --- |
| `response_too_large` | UTF-8 payload exceeds the byte budget. |
| `malformed_response` | Invalid JSON, invalid response structure, or a mixed abstention. |
| `language_mismatch` | Response language differs from the request. |
| `scope_mismatch` | Claim or abstention conflicts with the request scope or intent state. |
| `snapshot_mismatch` | The reading or Dasha evidence points to a different snapshot. |
| `birth_time_unsupported` | The snapshot is ineligible for natal or Dasha claims. |
| `fact_not_authorized` | The referenced fact is missing from this request's evidence. |
| `fact_mismatch` | The structured assertion differs from the cited fact. |
| `dasha_evaluation_mismatch` | The expected instant differs from the lookup, claim, or fact instant. |
| `target_mismatch` | An otherwise valid assertion falls outside the resolved intent. |
| `certainty_mismatch` | The claim presents the wrong birth-time certainty or interpretation type. |
| `citation_not_authorized` | The cited ID is absent from the current retrieval results. |
| `citation_inapplicable` | The retrieved rule or conditionality differs from the requested concept or its cited fact. |
| `invalid_evidence` | The supplied evidence is malformed, duplicated, or internally inconsistent. |

## What validation establishes

Validation establishes deterministic fact consistency and that a selected
reviewed passage has applicable metadata. It cannot establish that a passage
semantically entails arbitrary prose, that an astrological interpretation is
true, or that a translation preserves its meaning. The schema therefore has
no model-authored text fields for claims, summaries, caveats or abstentions.
A future renderer must use server-authored English or Nepali templates and
trusted passages. A retrieved passage may be in a different language from
the reading locale. This work adds no rendering, generation, translation,
correction calls or knowledge publication.
