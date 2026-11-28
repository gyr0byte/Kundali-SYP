# Embedding builds and exact pgvector retrieval

Commit 12.3 adds embedding infrastructure without publishing the [draft
corpus](knowledge-ingestion.md) or enabling an external provider in the
application. It adds no frontend, public endpoint or generation pipeline.

## Provider and data boundaries

`EmbeddingProvider` exposes an immutable `EmbeddingConfig` and separate
`embed_query(EmbeddingQuery)` and `embed_document(text)` operations.
Queries contain only allowlisted topic/entity combinations. They are
serialized in deterministic order, deduplicated and length-bounded.
The question text, chart facts, birth data, identities, and Dasha evaluation
instants stay local. Document encoding receives the exact checked chunk
text and no associated chart or account data. Output vectors must contain
384 finite numeric components and have a nonzero norm. Providers and
pipeline boundaries normalize to unit L2 length. The hash-based synthetic
provider supports deterministic offline checks and uses distinct encoding
domains for query and document.

`VertexGeminiEmbeddings` prepares the Google Cloud regional publisher
model `gemini-embedding-001:predict` with one input per request,
`RETRIEVAL_QUERY` or `RETRIEVAL_DOCUMENT`, `outputDimensionality: 384`,
and `autoTruncate: false`. The adapter uses HTTPS and an injected
server-side OAuth access-token supplier. It limits requests to two
attempts on transport errors or selected transient HTTP responses, bounds
individual HTTP phases and successful response size, and uses an eight-second
retry and streaming budget. A blocking HTTP phase can extend past that
budget up to its remaining phase timeout. The caller must bound token
acquisition separately. Redirects are disabled. Provider bodies and
credentials are omitted from diagnostic errors. [Vertex embedding API](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/text-embeddings-api)

The future Vertex pilot requires a billing-enabled Google Cloud project
with the Vertex AI API enabled, a supported regional publisher endpoint,
quota approval, and a workload identity or Application Default Credentials
flow that yields an OAuth access token with a suitable scope such as
`cloud-platform`. The caller needs `aiplatform.endpoints.predict` on the
authorized project or resource. Setup administrators may need separate
permission to enable the API or attach billing. Confirm project-specific
budget, region, processing terms and retention settings. The Gemini
Developer API uses a different endpoint and a Google AI Studio project
API key sent as `x-goog-api-key`. Its billing, quota and data handling
terms are separate. This adapter implements regional Vertex REST only.
[Cloud authentication](https://docs.cloud.google.com/docs/authentication)
· [Vertex IAM](https://docs.cloud.google.com/iam/docs/roles-permissions/aiplatform)
· [Developer API keys](https://ai.google.dev/gemini-api/docs/api-key)
· [Vertex pricing](https://cloud.google.com/model-garden/pricing)
· [Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing/)

## Storage and eligibility

Revision `0007_knowledge_embeddings` follows `0006_knowledge_corpus`.
It uses the existing pgvector extension. `embedding_builds` stores
provider, model, revision when published, location, dimension, encoding
modes, preprocessing and normalization versions. The build ID hashes
that configuration with its purpose and explicit generation. Register
another generation to rebuild after observed drift even when the hosted
model identifier is unchanged. `knowledge_chunk_vectors` has one
`VECTOR(384)` per build and citation ID. A composite foreign key pins the
content checksum to the corresponding chunk. No existing citation IDs or
corpus rows are rewritten. Downgrade removes the vector/build tables and
the supporting checksum index. SQLite's JSON variant supports offline
schema and storage tests.

Use `register_build` and `embed_chunk` in fresh writer sessions. Each call
owns its transaction. Repeated writes preserve the first committed vector
for the same build and checksum. PostgreSQL document encoding uses a
shared row lock on the source and chunk to serialize publication or
content changes with encoding. The row lock lasts through one bounded
provider call. Use an authorized corpus-operator workflow for build writes.
It needs vector/build read and insert privileges and permission to take
the source and chunk row locks. The runtime role needs only read access
to the two additional tables for semantic serving. The development role
grants are documented below. The source and chunk publication filters are
application-level.

A production vector requires a current, enabled, approved, rights-cleared
production chunk with explicit third-party processing permission. The
35 draft candidates fail the publication gate and their manifests do
not grant hosted processing. Synthetic providers and test collections
are confined to test builds and are ineligible for production serving.

## Ranking and fallback

Provide the build ID and compatible provider explicitly. An incompatible
build raises a configuration error. Apply the same topic, language,
publication, rights and individual-fact checks used by keyword retrieval.
Rank only the eligible citation IDs with matching checksums from the
selected build. Exact pgvector cosine distance is adjusted by a 0.01
experimental bonus for Tier 2. Lower adjusted scores rank first, followed by tier
and citation ID under PostgreSQL's C collation. No approximate index
is needed. Positive lexical overlap is unnecessary. The final read
rechecks eligibility and returns existing provenance and conditionality.
[pgvector distance operators](https://github.com/pgvector/pgvector#distances)

If all eligible vectors are missing, the selected build is unavailable,
or provider encoding fails, the result explicitly identifies the keyword
fallback and reason. An empty eligible set returns an empty semantic
result without calling the provider. With partial vector coverage, only
eligible vector matches are ranked. Stored vectors cannot serve disabled
or withdrawn releases, and a draft replacement does not change the
currently enabled release by itself. Retrieval checks permissions at read
time. Physical removal of retired or withdrawn vectors is a separate
operator responsibility. No provider is selected automatically.

## Verification and remaining limits

The 53 focused offline tests passed. Five opt-in native PostgreSQL
integration tests passed in 38.39 seconds using synthetic data. The
development migration `0007_knowledge_embeddings` applied successfully.
The disposable suite covers migration and ORM consistency, corpus
preservation, exact vector rank and ties, transactional writes and
checksum constraints, and the semantic retrieval filters.

Read-only development verification on 28 November 2026 confirmed
`kundali_dev_app` with verified TLS and required channel binding.
The readiness checker returned 0 at `0007_knowledge_embeddings` with
pgvector installed. `SELECT` succeeded on all four tables. The source,
chunk, build and vector counts were all zero. Privilege inspection
confirmed that `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`
and `TRIGGER` were denied on both new tables.

With no registered build and no published knowledge, semantic lookup
returned the labeled keyword fallback `build_unavailable` with zero
matches. With no provider supplied, it returned the labeled keyword
fallback `provider_unavailable` with zero matches. Neither path
invoked an encoder. The local backend started, returned HTTP 200
from `GET /health`, and was stopped.

No production corpus or embedding build exists in development. Held
sources still require editorial and hosted-processing clearance.
The runtime check exercised empty-table behavior. The populated synthetic
tests exercised ranking and filtering. Vertex authentication, hosted
throughput, and multilingual and cross-language retrieval quality remain
unverified.
