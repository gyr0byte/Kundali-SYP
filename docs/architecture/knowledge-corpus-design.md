# Kundali knowledge corpus and embedding design

Research cut-off: 27 November 2026. This design implements the boundaries in
[project plan §§9 and 11](../Kundali_Project_Plan.md) and builds on
[ADR 0003](../adr/0003-hosted-postgres-instead-of-docker.md) and
[ADR 0006](../adr/0006-import-linter-boundary-calc-ai.md). The existing
`app/knowledge` ingestion, chunking and provenance modules, the knowledge
model, and the embedding and retrieval modules are scaffolding. This phase
adds no corpus, vectors, database objects, or runtime behavior.

## Source decisions

Clearance attaches to the exact edition **and digital artifact**. The original
work, translation, editorial notes, scans, OCR, and website markup can have
different rights. An institutional Public Domain Mark is evidence of the
item's status, rather than a license granted by the library. Preserve its
credit. Record the launch jurisdictions and any narrower artifact terms
before publication. For new material require documented rights to reproduce,
redistribute, adapt or translate, and process through the selected embedding
service. [Public Domain Mark](https://creativecommons.org/publicdomain/mark/1.0/)
· [Nepal Copyright Act](https://www.nepalcopyright.gov.np/downloadsdetail/9/2019/5916521)
· [U.S. Copyright Office on foreign-work restoration](https://www.copyright.gov/circs/circ38b.pdf)

| Candidate and exact edition | Rights decision and digital format | Editorial use |
| --- | --- | --- |
| **Bṛhat Jātaka**, Varāhamihira, English translation by N. Chidambaram Iyer, Foster Press, Madras, 1885, Aryan Miscellany | **Approved candidate for Tier 2.** Wellcome explicitly marks its item public domain and permits unrestricted copyright reuse. Page images and PDF are available. Use a checked transcription from this scan. The matching Archive OCR can assist alignment after artifact review. [Wellcome edition and rights](https://wellcomecollection.org/works/afmgm695) · [Archive scan and OCR](https://archive.org/details/brihatjatakavar00iyergoog) | Classical natal Jyotish. Start with signs and planetary descriptions in I–II, birth Nakshatras in XVI, and explicit sign/house placements in XVII–XVIII and XX. Verify passages against the 1885 pages before assigning verse numbers. Chapter VIII's period system is out of scope for Vimshottari retrieval. |
| **Bṛhat Saṃhitā**, Varāhamihira, English translation by N. Chidambaram Iyer, South Indian Press, Madura, 1884 and Foster Press, Madras, 1885 (part II) | **Approved candidate for Tier 2.** Wellcome applies the Public Domain Mark to its digitized two-part item. Use its scans as authority. The Harvard/Google-derived Archive item provides OCR and lists U.S. `NOT_IN_COPYRIGHT` as its possible status. Use Wellcome for redistribution evidence. Exclude separately bound material from the selected text. [Wellcome edition and rights](https://wellcomecollection.org/works/hzaaf9ak) · [Archive OCR and provenance](https://archive.org/details/bihatsahitvarah00iyergoog) | Encyclopedic saṃhitā with distinct contexts. Consider chapter 101 for carefully screened natal Nakshatra passages. Chapter 98 covers classification and electional usage, including Abhijit. Preserve that context and exclude it from natal placement matching. Neither chapter establishes Pada coverage. [Chapter navigation for cross-checking](https://www.wisdomlib.org/hinduism/book/brihat-samhita) |
| **Bṛhat Jātaka**, Sanskrit e-text, Varāhamihira, Oriental Books Reprint Corporation second edition (1979), keyed by Mizue Sugita, GRETIL TEI release 2020 | **Rejected for the initial corpus.** TEI and HTML are available under CC BY-NC-SA 4.0, with attribution, noncommercial and share-alike conditions. This is a different artifact from the Wellcome scan. [GRETIL edition and license](https://gretil.sub.uni-goettingen.de/gretil/corpustei/transformations/html/sa_varAhamihira-bRhajjAtaka.htm) | Useful Sanskrit comparison for chapter and verse boundaries. Keep this transcription outside the production corpus and hosted processing. |
| **Bṛhat Parāśara Horā Śāstra**, attributed to Parāśara, R. Santhanam, first edition, Ranjan Publications, New Delhi, 1984, Sanskrit and English | **Excluded.** The edition and translation are identifiable. No affirmative redistribution, adaptation or embedding grant was found for the modern English translation. Scanned PDF availability does not confer these rights. [Library edition](https://opac.duls.du.ac.in/cgi-bin/koha/opac-MARCdetail.pl?biblionumber=419430) · [Catalogue record](https://openlibrary.org/books/OL2691515M/Brihat_Parasara_hora_sastra_of_Maharshi_Parasara) | Parāśarī reference for natal rules and Vimshottari, conceptually suited to verse-level chunks. Numbering and text must be tied to a specific recension. Existing calculation citations can remain external references. |
| **Bṛhat Parāśara Horā Śāstram, Uttara Khaṇḍa**, attributed to Parāśara, Sanskrit Khemraj edition | **Unresolved.** Source Library supplies scans and digital transcription and labels its item CC0. It gives only an estimated 20th-century edition. Exact edition date, imprint, editorial contributions, and the rights scope behind the platform's label still need confirmation. [Source Library edition record](https://kloss.sourcelibrary.org/book/the-great-compendium-of-astrology-by-parashara-latter-ed) | A route to a clearance-backed Sanskrit source and a commissioned translation. Verify the intended Vimshottari passages against the actual witness before commissioning or cataloguing. |
| **Phaladīpikā**, Mantreśvara, V. Subrahmanya Sastri's Sanskrit edition with English translation, V. B. Soobiah & Sons, Bangalore, 1937 | **Unresolved.** The catalogue identifies the edition and a scan is available. No permission grant or sufficient translation-rights evidence was established. Confirm translator term, source-country status, and launch-jurisdiction status before reuse. Scan/OCR can be assessed after clearance. [Research-library catalogue](https://rmrl.in/ta/onlinecat/40869/mantreswara%27s-phaladeepika) · [1937 edition scan](https://archive.org/details/in.ernet.dli.2015.406048) | Classical natal placements and period interpretations. Good conceptual boundaries by rule and period system once the exact passages and prerequisites are checked. |
| **Vedic Astrology: An Integrated Approach**, P. V. R. Narasimha Rao, first published 2000, original English, author-hosted edition (separate publisher unverified) | **Excluded.** The searchable PDF identifies the author's copyright. No reusable grant was established. [Author's PDF and copyright page](https://www.vedicastrologer.org/articles/vedic_astro_textbook.pdf) | Modern Jyotish textbook with worked Vimshottari examples, useful as an external calculation reference. Its prose, interpretations, tables, and worked examples stay out of corpus ingestion. |

The proposed first release is **24–40 English conceptual chunks** from the
two cleared Wellcome editions, subject to page-by-page verification and
editorial screening. Treat the number as a review budget, with no quota per
topic. Record gaps for Pada-specific interpretation and Vimshottari
interpretation. Dasha calculation and display remain available independently.
For these gaps, commission cleared original material or a fresh translation
from a verified reusable witness. Begin Nepali coverage with human-reviewed
adaptations of cleared passages and authorized original summaries. Sanskrit,
Hindi, transliteration, and English each retain their actual language tags.

## Source manifest and chunk contract

Proposed `manifest_schema_version: 1` with typed entries and published releases.

| Record | Required fields and rules |
| --- | --- |
| Source identity and bibliography | Stable curated `source_id` for one work/edition/language artifact lineage. Record `source_version`, exact title, author or explicit traditional attribution, translator/editor where applicable, edition, publisher or documented absence, publication year or documented range, language (BCP 47), tradition, tier, canonical source/scan URLs, archive identifier, and retrieval date. A different translation or edition receives its own source ID. |
| Artifact provenance | Record artifact format, immutable SHA-256 of acquired bytes, selected page scope, and transcription/OCR method and revision. Record source version and SHA-256 of the reviewed text export separately. Specify printed page and digital image/leaf mapping where they differ. |
| Rights and review | Require rights status (`public_domain_mark`, `licensed`, `project_owned`, `unresolved`, or `excluded`), rights holder or marked artifact custodian, evidence URLs, scope/jurisdictions, permitted uses including third-party processing, obligations/credit, review date and reviewer reference. Tier 1 additionally requires a real credential record, signed contribution permission and approval record. Tier 3 requires an accountable admin, dated approval, original wording and linked cleared references. |
| Chunk | Stable logical `chunk_key` per source and conceptual anchor, plus immutable citation `chunk_id` scoped to source version, key, and chunk revision. Record `text`, SHA-256 of NFC-normalized UTF-8 with LF newlines, language, topic, structured `applies_to`, interpretive school, reference locator(s), editorial status and optional translation/supersession links. Resolve tier and source enablement from the source release. |
| Publication | New releases default disabled. Retrieval requires a cleared, enabled source release, approved chunk and production collection. A correction creates a new revision and retains old citation resolution subject to rights. Replacements switch the active release as a unit after validation. Rights withdrawal removes the older text/vector from serving and leaves a citation tombstone where permitted. Test records are confined to a separate collection and fail production-import validation. |

Use a tagged applicability schema. Filters intersect required attributes of
one matching typed fact. A missing attribute cannot satisfy a rule.

| Topic | Applicability example |
| --- | --- |
| `planet_general`, `sign_general`, `house_general` | Topic entity with `scope: general`, such as `planet: Moon`. A description makes no placement assertion. |
| `planet_in_house` or `planet_in_sign` | `scope: natal_placement`, `planet: Moon`, and `house: 5` or `sign: Leo`. Add only documented prerequisites such as frame or a recognized school-specific convention. |
| `nakshatra` or `pada` | Explicit `body`, canonical `nakshatra`, and `pada: 1..4` for Pada-specific text. Two candidate Padas cannot satisfy a definite placement. General descriptions can still be retrieved as general material. |
| `dasha` | `scope: active_dasha`, `method: vimshottari-v1`, `level: AD`, `lord: Venus`, with `parent_lord` when the passage requires it. Match only an active derived fact scoped to the snapshot and evaluation instant. Propagate approximate-time conditionality. |

Cut one passage per concept or rule. Keep its necessary qualifications with
it. Preserve separate positions when editions or schools disagree. A lengthy
passage can be divided at conceptual boundaries with distinct locators.
Exclude deterministic predictions of death, illness, accidents, or outcomes,
prescriptive medical/legal/financial language, and discriminatory claims from
production selection. Treat traditional interpretations as interpretations.

**Synthetic test fixture example.** One invented source
`test:placement-notes@1` has the title *Synthetic Placement Notes*, project test
fixture authorship, no translator, `collection: test`, `enabled: false`,
and internal fixture locators. Example logical keys and content follow.
Fixture checksums are calculated from the eventual fixture bytes.

| Chunk key and locator | Topic and applicability | Original fixture text |
| --- | --- | --- |
| `moon-general`, fixture §1 | `planet_general`, Moon | “This sample index groups Moon descriptions by subject.” |
| `moon-house-five`, fixture §2 | `planet_in_house`, Moon, house 5 | “This sample paragraph belongs in the fifth-house placement bucket.” |
| `venus-antardasha`, fixture §3 | `dasha`, Vimshottari, AD, Venus | “This sample paragraph is selected for an active Venus subperiod.” |

## Embedding candidates

Pricing and quotas are documentary snapshots. Check the selected account,
region and endpoint before authorizing any calls.

| Candidate | Encoding and deployment | Evidence and operating constraints |
| --- | --- | --- |
| **intfloat/multilingual-e5-small** | 384 dimensions, 512-token input, English `query: ` and `passage: ` prefixes for every language, masked mean pooling and L2 normalization. MIT model release. About 118M parameters and 471 MB for the pinned safetensors artifact. That is roughly 0.44 GiB for FP32 weights alone. CPU inference adds the runtime, tokenizer and working memory. Windows peak RAM and latency are unmeasured. Local execution has no vendor quota, per-call fee, or external query transfer. The training report describes mixed datasets. The weights license does not grant rights to those datasets. [Model card](https://huggingface.co/intfloat/multilingual-e5-small) · [Pinned files](https://huggingface.co/intfloat/multilingual-e5-small/tree/0a68dcd3dad5b4962a78daa930087728292b241d) · [Training report](https://arxiv.org/abs/2402.05672) | The card reports English and multilingual evaluations. An independent Nepali study's Table V reports Recall@1 of **77.5%** for Nepali queries over Nepali text and **79.0%** for English queries over Nepali text (488 passages, 200 queries). This small parallel-text study does not establish Nepali-to-English retrieval or Jyotish quality. [Study](https://www.researchgate.net/publication/408986977_How_Well_Does_AI_Understand_Nepali_A_Multi-Task_Benchmark_of_Large_Language_Models_and_Embedding_Models_on_a_Low-Resource_Language) |
| **Google Cloud `gemini-embedding-001`** | Hosted proprietary model, up to 3072 dimensions, 2048 input tokens. Test requested 384 dimensions with `RETRIEVAL_QUERY` and `RETRIEVAL_DOCUMENT`, fixed title handling and normalization. One text per online prediction request. Requires a billing-enabled cloud project, authorized endpoint and server-side IAM. Weight size and server RAM/CPU are not disclosed, with no local model requirement. Training methodology is described, without a redistributable training-corpus grant. [API](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/text-embeddings-api) · [Lifecycle](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions) | Google explicitly lists Nepali. Its report covers English, multilingual and cross-language benchmarks. No independent Nepali retrieval result was established for the proposed dimensions. Published global online pricing lists **$0.00015 per 1,000 billable input characters** (batch $0.00012). Global embedding request/token quotas and a separate prediction quota apply. Google Cloud's training restriction and retention rules are separate. Confirm applicable retention and location controls in the chosen project. [Technical report](https://arxiv.org/abs/2503.07891) · [Pricing](https://cloud.google.com/model-garden/pricing) · [Quotas](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/quotas) · [Data controls](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/zero-data-retention) |
| **OpenAI `text-embedding-3-small`** | Hosted proprietary model, 1536 dimensions by default, configurable to 384 for comparison, up to 8192 input tokens. Same endpoint and model for query and document, with no required role prefixes. Uses a server-side API project, with no local weights or inference RAM requirement. Weight size, server CPU/RAM and a redistributable training-data license were not established. [Embedding guide](https://developers.openai.com/api/docs/guides/embeddings) | Provider reports 62.3% on English MTEB and 44.0% on MIRACL. MIRACL is monolingual within each language, and its aggregate supplies neither a Nepali-specific score nor a cross-language result. No official per-language Nepali support claim or independent Nepali result for this exact model was established. Online input costs **$0.02 per million tokens**. RPM/TPM and access depend on account tier. API data is excluded from training by default, with abuse monitoring normally up to 30 days. Embeddings are eligible for approved retention controls. [Quality evidence](https://openai.com/index/new-embedding-models-and-api-updates/) · [MIRACL](https://github.com/project-miracl/miracl) · [Price and rates](https://developers.openai.com/api/docs/models/text-embedding-3-small) · [Data controls](https://developers.openai.com/api/docs/guides/your-data) |

**Recommendation.** Pilot Gemini at 384 dimensions after approval for hosted
use and spend. Its explicit Nepali support, separate retrieval encoding and
fit with the planned `VECTOR(384)` make it the first candidate, subject to
evaluation at that exact dimensionality. Keep E5 as the reference candidate
for a later approved CPU evaluation, and OpenAI as a hosted comparison.
Use a deterministic metadata/keyword baseline now. No benchmark score
from these sources establishes relevance for Kundali's corpus.

Pin provider, exact model or local artifact revision, endpoint/region,
dimension, input role and prefix, tokenizer/runtime where applicable,
normalization and preprocessing versions. Record these with each vector
build and retain a vector build ID. A hosted model name is weaker than
an artifact checksum. Check fixed synthetic probes for drift. Re-embed
in a separate build before switching. Never compare vectors across builds
with different encoding configurations even if dimensions agree.

## Privacy boundary and Commit 12.2

Only cleared corpus text and allowlisted topic/entity query strings may
reach an approved embedding service. Keep natal facts, active period
timestamps, birth date/time/place, coordinates, account or snapshot IDs,
and raw user questions out of provider input and logs. Apply ownership and
typed fact filters locally before vector ranking. Keep provider credentials
server-side and verify repository, storage, and hosted-use permissions
separately. Revocation disables serving and removes affected embeddings
from the next index/build as well as any live serving cache.

1. Implement the manifest and applicability validators in
   `app/knowledge`, with deterministic IDs and test-only fixtures.
2. Select a few page-confirmed passages from each cleared Wellcome item.
   Pin exact artifacts and locators, preserve notices, and require editorial
   sign-off before publishing. Keep Tier 1 empty until approved contributors
   exist. Keep unresolved translations and unreviewed topics disabled.
3. Test metadata-first retrieval with a deterministic baseline. Use synthetic
   charts and human-labelled EN→EN, NE→NE, EN→NE and NE→EN cases, including
   Romanized Nepali, ambiguous terms and hard negatives. Track Recall@5 and
   nDCG@5 by direction and topic. Require zero applicability and publication
   leaks. Evaluate exact dimensions and compare with the baseline before
   committing to a hosted provider.
4. Once hosted processing is separately authorized, use a small provider
   adapter with bounded retries and request budgets. Start with exact cosine
   ranking after metadata filters in PostgreSQL/pgvector when storage is
   approved. At this corpus size, defer approximate indexing until measured
   need. Keep the calculation engine independent of the knowledge layer.
   Leave generation and automatic Tier 1 promotion outside this step.
