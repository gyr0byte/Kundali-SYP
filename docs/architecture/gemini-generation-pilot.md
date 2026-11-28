# Synthetic Gemini Developer API generation pilot

## Model and transport

The pilot uses the fixed `gemini-3.5-flash-lite` model with
`POST /v1beta/models/gemini-3.5-flash-lite:generateContent` on
`generativelanguage.googleapis.com`. Google documents structured output and
`MINIMAL` thinking for this model. The request asks for one candidate and
at most 256 output tokens. Its JSON schema permits only a `choices` array
with integers within the offered range. The local selection validator still
checks distinctness, scope, grounding and safety.
[Model](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite) ·
[REST contract](https://aistudio.google.com/api-reference/generate-content/generate-content) ·
[Structured output](https://aistudio.google.com/docs/structured-output) ·
[Thinking levels](https://aistudio.google.com/docs/thinking)

The pilot uses one async HTTP client and at most one active request. The
transport uses TLS, disables redirects and environment proxies, and makes
one POST per adapter invocation with zero transport retries. It authenticates
through the `x-goog-api-key` header and uses the existing AIza and AQ. key
format checks. The server clips connect, read, write and pool timeouts
to the time left on the shared monotonic deadline used by both orchestration
attempts. It propagates task cancellation to httpx.

The request body is capped at 1,536 bytes, the streamed JSON envelope
at 16 KiB, and candidate text at 1 KiB. A successful envelope must provide
one model candidate with a single text part and finish reason `STOP`.
Blocked, truncated, empty, oversized or mismatched envelopes fail closed.
Malformed numeric selections inside an otherwise valid envelope still go
through the [existing correction policy](safety-and-generation.md). A
401, 403 or 429 halts the entire pilot. Server errors and transport failures
fail that case without an automatic retry. The adapter has no paid tier,
fallback model or alternate provider.

## Outbound privacy

The hosted runner only accepts authorization settings and a credential
callback. It loads the repository fixture and verifies both its pinned
SHA-256 and the operator's reviewed checksum. Each case gets a local
authorization scope, and the adapter verifies the orchestrator's choices
against that case before dispatch. It builds the outbound prompt from the
pinned fixture. Matching a fixture's typed concepts from an ordinary
request does not grant authorization.

Only a fixed instruction, locale, numbered choices, claim kinds, typed
synthetic concepts and an optional fixed correction code are transmitted.
Raw questions, passage text, model history, account and snapshot IDs,
timestamps and birth data remain local. The transport sends no search,
retrieval, executable tools, cache references or persistent conversation
state. Google documents implicit caching as provider-managed and gives no
per-request off switch. The pilot uses short inputs, requests no explicit
caching, and halts if the API reports cached tokens. This cannot guarantee
that Google did not process or retain the synthetic input. Google can use
unpaid submissions to improve its services.
[Caching](https://aistudio.google.com/docs/caching?generate-content=true#implicit-caching) ·
[Unpaid-service terms](https://aistudio.google.com/docs/terms#unpaid-services)

## Fixture and offline baseline

[`synthetic-generation-v1.json`](../../backend/tests/fixtures/synthetic-generation-v1.json)
has SHA-256 `b76b874f899151f2b03812b050ed9e7380e7f14f76ee53f4688d55785565c3db`.
It contains seven cases and four original synthetic passages. Four cases
reach selection and cover one exact natal fact, English and Nepali general
explanations, and a Nepali conditional interpretation. Two blocked cases
and one insufficient-evidence case make zero provider calls.

The offline first-choice baseline matched all seven labelled dispositions.
It selected an acceptable option in all four eligible cases, rendered four
grounding- and safety-accepted readings, and abstained in the other three.
It made zero HTTP attempts. Malformed output, budget exhaustion and
transport failure are exercised with fake providers or mocked transport.
The two options in the English general case are equivalent to the provider.
The small fixture checks integration and dispositions. It provides neither
an independent quality benchmark nor evidence for production deployment.

The hosted report compares against that same baseline and records per-case
selection, expected disposition, local decision codes, full pipeline
latency, grounding and safety acceptance, abstentions and correction
attempts. It separately records HTTP attempt outcomes, request latency and
token counts where available, including cache counts. Skipped eligible cases
remain in the selection-accuracy denominator. Exports contain no key,
provider response body, question or passage text.
[Model pricing](https://aistudio.google.com/docs/pricing#gemini-3.5-flash-lite)

## Completed pilot and serving recommendation

The authorized run used `google-gemini-developer` with
`gemini-3.5-flash-lite` and the approved fixture checksum above.

| Metric | Deterministic local selector | Gemini |
| --- | ---: | ---: |
| Expected outcomes matched | 7 of 7 | 7 of 7 |
| Accepted selections | 4 | 4 |
| Selection accuracy | 100% | 100% |
| Expected abstentions with zero provider calls | 3 | 3 |
| Correction attempts | 0 | 0 |
| Median pipeline latency for accepted responses | 4.3435 ms | 1,105.7225 ms |

Gemini used four of eight HTTP attempts. All four returned HTTP 200.
Median HTTP latency was 1,101.9245 ms and total HTTP duration was
4,689.252 ms. Google reported 288 input tokens, 52 output tokens and
340 total tokens. Estimated API cost was $0 under the confirmed
free-tier configuration. Billing was not independently verified.

Both providers selected option one in all four accepted cases. Option one
was an expected answer in every case, and the English general case also
accepted option two. The pilot establishes live integration compatibility.
Its small fixture cannot establish model superiority, broad multilingual
quality or production safety performance. Offline verification passed 177
focused tests.

Use deterministic local selection and canonical keyword retrieval for
initial serving. Retain Gemini generation and embedding capabilities for
future authorized evaluation. Free-tier hosted generation remains
synthetic-only. No production passage display approvals are configured.

## Authorized future command

Use the Windows account that owns the existing
`D:\DevSecrets\Kundali\gemini-api-key.dpapi` file. From the repository root,
confirm in AI Studio that billing is disabled and that free quota is
available. Then run the following in Windows PowerShell with a fresh output
file path. The launcher validates the raw fixture checksum before loading
the key and puts it only in the evaluation child process's environment.

```powershell
& .\scripts\run-gemini-generation-pilot.ps1 -AuthorizeHosted -ConfirmFreeTier `
  -ApprovedFixtureSha256 'b76b874f899151f2b03812b050ed9e7380e7f14f76ee53f4688d55785565c3db' `
  -MaxHttpAttempts 8 -Output 'D:\DevCache\tmp\kundali-gemini-generation-pilot-v1.json'
```

Eight attempts cover the four eligible cases and one permitted correction
per case. The pilot enforces its configured limit at dispatch and accepts
no limit above 20. If quota, authentication or the attempt limit interrupts
the run, the report records the partial results and reason. A hosted run
with missing or unexpected case outcomes returns a nonzero exit status
after writing the report. The free-tier adapter has no production entry point.
