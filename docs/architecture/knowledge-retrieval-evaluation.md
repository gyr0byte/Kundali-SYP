# Multilingual intent and retrieval evaluation

## Intent and evidence boundary

`app.ai.intent.resolve_intent` uses a bounded local vocabulary for English,
Devanagari Nepali, common Romanized Nepali and mixed phrasing. Unicode
normalization, explicit aliases and a small set of Nepali suffixes support
recognized forms. It returns one typed `EmbeddingQuery` or an explicit
`ambiguous` or `unsupported` outcome. General planet, sign and house
definitions have separate targets from placements. Nakshatra, Pada and
Vimshottari level requests use the existing chart-scoped applicability types.
Requests for unsupported general concepts, multiple subjects, private
identifiers, dates, times or arbitrary language can require clarification or
abstention.

Callers must authorize the snapshot before projecting its evidence. The
projection accepts natal placements from a version 1 snapshot and preserves
approximate-time conditionality. Moon-only version 2 snapshots contribute no
natal placement or Dasha evidence. User-supplied placements are assertions
checked against one calculated fact. Active Dasha evidence must match the
snapshot, chart, certainty and evaluation instant. For questions that say
“current,” the caller must supply the instant it selected as current and the
Dasha lookup must have evaluated that instant. Snapshot identifiers, timestamps,
raw question text, birth information and uncertainty evidence stay local.
The provider input contains only the allowlisted topic and entity fields.
No public question endpoint is introduced here.

## Fixture and metrics

[`multilingual-retrieval-v1.json`](../../backend/tests/fixtures/multilingual-retrieval-v1.json)
is an original, project-owned engineering fixture with 60 hand-labelled cases
across 15 question families and four language forms. It includes 40 labelled
retrieval cases, 16 unsupported cases and four ambiguities. The five synthetic
chart contexts cover exact, approximate, uncertain, unavailable and active
Dasha evidence. Of 18 short original passages, 13 are eligible in the fixture
and five exercise pending, disabled, withdrawn, test and unresolved-rights
filters. Fixture eligibility is solely for evaluation and carries no astrologer
approval. Labels and Nepali phrasing have had no independent human review.
The 35 pending production candidates are outside the evaluation corpus.

Run the offline comparison from the repository root. Use a fresh output file
in an existing ignored D: directory.

```powershell
. .\scripts\env.ps1
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location .\backend
try {
    .\.venv\Scripts\python.exe -B -m app.ai.evaluate_retrieval `
      --output 'D:\DevCache\tmp\kundali-keyword-eval-v1.json'
} finally { Pop-Location }
```

Both keyword variants use the same typed intent, eligible pool, and applicability
checks. The original variant scores the local question text. The canonical
variant scores its allowlisted entity names and values. Metrics include exact
intent classification (status, scope and target), topic and full-entity
accuracy on labelled targets, Recall@1 and Recall@5 averaged over queries with
positive judgments, nDCG@5, MRR@5, abstention, and publication and applicability
violations. Results include case IDs and per-language breakdowns. For this
fixture an unjudged eligible result counts as an applicability violation. A
grade-zero result is applicable but irrelevant.

| Metric | Original question | Canonical terms |
| --- | ---: | ---: |
| Recall@1 | 58.75% | 95.00% |
| Recall@5 | 60.00% | 100.00% |
| nDCG@5 | 0.60365 | 0.99197 |
| MRR@5 | 0.625 | 1.000 |
| Applicability violations | 0 | 0 |
| Publication leaks | 0 | 0 |
| Local retrieval p50 / p95 | 1.11 / 2.80 ms | 1.18 / 2.61 ms |

Intent and topic/entity extraction matched all 60 and 40 applicable labels,
respectively. The resolver withheld retrieval for all 16 unsupported and four
ambiguous cases. Original-query Recall@5 was 90% English, 35% Nepali, 20%
Romanized Nepali and 95% mixed. Canonical Recall@5 reached 100% in each group.
The timing values include local SQLite candidate filtering and ranking only.
The questions share subjects and several use parallel wording. These results
measure fixture coverage and cannot establish general Nepali or multilingual
retrieval quality. The canonical baseline's 100% Recall@5 leaves no headroom
for a hosted model to improve that metric on this fixture. Offline verification
passed 55 focused tests.

The hosted comparison sends each canonical intent once and uses the returned
normalized vectors for local exact cosine scoring with and without the
experimental 0.01 Tier 2 bonus. Both variants reuse the serving eligibility,
single-fact applicability, third-party-processing and checksum checks. Ranking
uses the same distance, tier and citation tie-break order as pgvector. The
pilot uses in-memory scores and does not benchmark PostgreSQL execution or
pgvector float32 effects. Controlled vectors and mock HTTP tests verify
pipeline behavior. No model-quality result is available yet.
Vertex authentication, latency and actual cost remain unverified.

## Future Vertex pilot

1. Review the fixture and executable revision, including each outbound passage
   and canonical target. Record the fixture SHA-256 from the offline export
   and supply it explicitly. The runner accepts only the repository evaluation
   fixture. Its document allowlist excludes all five negative-control passages.
2. Use a dedicated Google Cloud project with active billing, the Vertex AI API
   enabled (`aiplatform.googleapis.com`), and quota for the supported regional
   `gemini-embedding-001` publisher model. Check regional availability and the
   provider’s retention terms before approving processing.
   [API and regional request](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/text-embeddings-api) ·
   [Quotas](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/quotas)
3. Give the pilot identity `aiplatform.endpoints.predict` on the pilot project,
   for example through a scoped custom role. Use a short-lived OAuth access
   token with the `cloud-platform` scope from the authorized Google Cloud
   identity. Prefer an existing keyless identity or authorized impersonation.
   An operator supplies the token to the child process via
   `KUNDALI_VERTEX_ACCESS_TOKEN`. A Gemini Developer API key uses different
   authentication. The runner does not acquire credentials or use ADC directly.
   [Google Cloud authentication](https://docs.cloud.google.com/docs/authentication) ·
   [Vertex IAM permission](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/projects.locations.endpoints/predict)
4. The current plan has 13 documents and nine unique queries, so it needs
   22 successful requests. Allow at most 44 attempts including retries. At the
   published online price of $0.00015 per 1,000 input characters, the runner’s
   conservative estimate is at most $0.0066. It rounds each attempted request’s
   UTF-8 byte count up to a block of 1,000, including failed attempts. A
   7,000-microdollar cap ($0.007) covers this plan at that rate. Confirm the
   project’s current rate before running. The estimate controls this runner’s
   requests and does not cap the Cloud invoice.
   [Google Cloud pricing](https://cloud.google.com/model-garden/pricing)

The following assumes future authorization and an existing Google Cloud CLI
session for the pilot identity. Keep its profile on D: by pointing
`CLOUDSDK_CONFIG` to the existing D: configuration before invoking `gcloud`.
From the repository root, use the approved digest and project identifier.
The example uses the documented `us-central1` endpoint.

```powershell
. .\scripts\env.ps1
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:CLOUDSDK_CONFIG = '<existing gcloud configuration directory on D:>'
Push-Location .\backend
try {
    $env:KUNDALI_VERTEX_ACCESS_TOKEN = gcloud auth print-access-token --quiet
    if ($LASTEXITCODE -ne 0 -or -not $env:KUNDALI_VERTEX_ACCESS_TOKEN) {
        throw 'Pilot authentication unavailable'
    }
    .\.venv\Scripts\python.exe -B -m app.ai.evaluate_retrieval `
      --authorize-hosted --approved-dataset-sha256 '<reviewed fixture SHA-256>' `
      --project '<pilot project ID>' --location us-central1 `
      --max-attempts 44 --max-spend-microusd 7000 --price-per-1000-microusd 150 `
      --output 'D:\DevCache\tmp\kundali-vertex-eval-v1.json'
    if ($LASTEXITCODE -ne 0) { throw 'Pilot did not complete' }
} finally {
    Remove-Item Env:KUNDALI_VERTEX_ACCESS_TOKEN -ErrorAction SilentlyContinue
    Pop-Location
}
```

The runner is offline by default. For a hosted run it checks authorization,
the fixture digest and worst-case budgets before reading the operator’s token.
Its JSON report records the dataset checksum and version, model, region,
requested dimensions and task types, preprocessing and normalization versions,
project fingerprint, per-attempt latency and outcome, and token counts where
reported. A failure stops the run and withholds scores for the partial vector
pool. The run holds vectors in memory and creates no database build or corpus
release. The model revision remains unset because the provider has not exposed
one through this adapter. Future reruns can detect differences in results
with the same inputs but cannot pin changes behind the hosted model identifier.

## Free Gemini Developer API pilot

Use an AI Studio key from a project that remains on the Gemini API free tier
with billing disabled. Confirm the project's tier and available quota before
authorizing a run. The runner sets the cost budget and unit price to zero,
caps attempts at 44, and stops on HTTP 429 without trying another provider or
tier. The API response does not attest to the project's billing tier, so the
operator must verify it in AI Studio.
[Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-embedding) ·
[Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)

Google can use unpaid submissions to improve its products, and human
reviewers may process them. The Developer pilot accepts only the pinned
fixture's 13 project-owned passages and nine canonical queries. Raw prompts,
personal chart data and the 35 unpublished candidates are outside that
allowlist. Vectors stay in memory, and the Developer provider identity is
distinct from Vertex in build compatibility checks.
[Gemini API unpaid-service terms](https://ai.google.dev/gemini-api/terms#unpaid-services)

The adapter calls the text `embedContent` method for `gemini-embedding-001`
using the `x-goog-api-key` header, requests 384 dimensions and normalizes
the result. It uses separate retrieval task types for queries and documents.
The report records each attempt's outcome and latency, plus prompt token counts
when Google returns usage metadata.
[Gemini embeddings guide](https://ai.google.dev/gemini-api/docs/embeddings) ·
[REST reference](https://ai.google.dev/api/embeddings)

Once the run is authorized, use the Windows account that stored the
DPAPI-encrypted key at `D:\DevSecrets\Kundali\gemini-api-key.dpapi`.
Run from the repository root in Windows PowerShell and choose a fresh JSON
output path in an existing D: directory. The script gives the key only to
the evaluation child process and clears its own launch copy after startup.

```powershell
& .\scripts\run-gemini-free-evaluation.ps1 -AuthorizeHosted -ConfirmFreeTier `
  -ApprovedDatasetSha256 '7f35fe79f71e8f9c07f757a5f3523f7cfd8632e688405df3724c9e2303d10b66' `
  -Output 'D:\DevCache\tmp\kundali-gemini-free-eval-v1.json'
```

### Completed pilot and serving decision

The authorized Developer API pilot used `gemini-embedding-001` at 384
dimensions with the fixture SHA-256
`7f35fe79f71e8f9c07f757a5f3523f7cfd8632e688405df3724c9e2303d10b66`.
All 22 requests (13 documents and nine canonical queries) succeeded on the
first attempt. Estimated API cost was $0 under the confirmed free-tier
configuration. The export contained no provider usage reports and the estimate
does not verify an invoice.

| Metric | Canonical keyword | Gemini semantic |
| --- | ---: | ---: |
| Recall@1 | 0.95 | 0.90 |
| Recall@5 | 1.00 | 1.00 |
| nDCG@5 | 0.991972 | 0.969343 |
| MRR@5 | 1.00 | 0.95 |
| Applicability violations / publication leaks | 0 / 0 | 0 / 0 |
| Local ranking p50 / p95 | 0.80 / 1.07 ms | 0.87 / 1.16 ms |

Median hosted request duration was 893.33 ms across all requests and
1,136.55 ms for query encoding. The local rankings used precomputed vectors
and exclude hosted encoding time. The sequential run does not establish
production or concurrent latency.

The 0.01 Tier 2 bonus changed no rankings. Gemini ranked the irrelevant
`moon-index` passage first for all four Moon-general language variants.
Those four cases share one canonical intent. The 60 cases span only 15
question families, with 40 cases contributing ranking judgments and a search
pool of 13 eligible passages. The high canonical baseline leaves no headroom
at Recall@5. Labels and Nepali phrasing lack independent review, so this
pilot cannot establish real-world multilingual retrieval quality.

Use canonical keyword retrieval as the initial serving strategy. It led on
early ranking metrics in this pilot and keeps retrieval local. Retain Gemini
Developer API, Vertex AI, pgvector storage and semantic retrieval as optional
capabilities. Keep the free-tier adapter restricted to the synthetic evaluation
fixture. Production user data remains outside its scope.

Offline verification passed 56 focused implementation tests and 21 focused
credential-format tests. The two runs overlap.
