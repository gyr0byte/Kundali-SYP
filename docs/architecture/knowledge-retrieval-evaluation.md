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
Vertex authentication, hosted latency and actual cost remain unverified.

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
