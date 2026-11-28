# Knowledge ingestion and baseline retrieval

Commit 12.2 implements the offline foundation in the
[corpus research and design](knowledge-corpus-design.md). There is no
public knowledge API, and no retrieval or embedding is invoked by chart
calculation.

## Candidate releases

The two [draft manifests](knowledge-candidates/) contain 35 original
English paraphrases. They contain neither complete translations nor
scan copies. Their edition-specific provenance is:

| Candidate | Pages checked and included |
| --- | --- |
| 19 from the English Iyer *Bṛhat Jātaka* (1885) | Printed pages 10, 12, 14 and 15. Ch. I's exaltation table distinguishes the sign from the principal degree. House descriptions are tied to the ascendant. Ch. II supplies planetary symbolism and Iyer's lunar-node terminology. [Wellcome item](https://wellcomecollection.org/works/afmgm695) |
| 16 from the English Iyer *Bṛhat Saṃhitā* (1884–1885) | Part II printed pp. 235–239. Ch. LIV (101) supplies four screened historical Moon–Nakshatra motifs, with the strength qualification at the end of that chapter on p. 238. Ch. LV (102) supplies sign subdivisions, with no Pada interpretations. The running headers on the latter leaves start naming the next chapter. The body headings and numbered entries identify the actual passages. [Wellcome item](https://wellcomecollection.org/works/hzaaf9ak) |

The entries were checked against Wellcome IIIF JPEG page images. The
source artifact checksum identifies the raw IIIF Presentation 2 manifest
and each locator pins the exact JPEG bytes and URL used. If Wellcome
regenerates an artifact, review the differences and issue a new version as
appropriate. No bulk OCR was ingested. The manifests carry Wellcome credit
and the edition-specific Public Domain Mark. Intended-redistribution
jurisdiction review and human editorial review remain open. Historical
motifs are descriptions of selected source imagery, without a claim that
the person has the traits or that a strength threshold has been measured.
Pada and Vimshottari interpretation remain out of the corpus.

## Schema and import

Revision `0006_knowledge_corpus` follows `0005_resolved_bs_profiles`. It
adds `knowledge_sources` keyed by source ID and version and
`knowledge_chunks` keyed by `source@version/key@revision`. PostgreSQL
uses JSONB for provenance, rights, locators and validated applicability.
There is no embedding column. The partial unique index permits a single
enabled release per source lineage. The foreign keys require existing
source versions, and revision supersession links to the prior release.
Downgrade drops the two corpus tables and their contents.

With the project environment loaded, run from `backend`:

```powershell
.\.venv\Scripts\python.exe -B -m app.knowledge.ingestion ..\docs\architecture\knowledge-candidates\brihat-jataka-iyer-1885.json
```

Use `--artifact <local IIIF manifest>` to verify the optional pin against
locally acquired bytes. Page-image pins support manual reproduction of
editorial verification. The CLI always runs a dry validation. An authorized
operator workflow can call `parse_manifest(bytes)` followed by
`import_manifest(session, manifest)` with a fresh session and the approved
database target. The import owns one transaction and validates digests,
revision conflicts and test isolation. An identical re-import leaves
existing review and publication state intact. Source and chunk content
are immutable at the importer boundary. Corrections use new versions
and changing a conceptual chunk requires a new logical revision.

All imports create disabled releases and pending chunks. A separate
editorial workflow must record approval before enabling production results.
The database enforces required review references and publication checks.
No application route grants publishing privileges. Tier 1 is reserved
until real contributor and approval records can be enforced. Test sources
are isolated by collection and namespace.

## Retrieval contract

`retrieve(session, Search(...))` takes selected topics, languages and
keywords plus trusted, typed evidence projections from the caller.
Chart facts stay outside the shared database. Applicability is a tagged
union whose topic distinguishes general descriptions from placement rules.
Specific rules require one fact to satisfy all fields. Missing and
uncertain fields cannot make a definite claim. Approximate-time matches
carry a conditional flag. Dasha matching also checks the requested
snapshot and evaluation instant against each candidate fact. No chart API
or interpretation caller is wired to this function yet.

SQL filters publication, rights, collection, topic and language first.
The service checks rights and applicability before scoring overlap of
normalized Unicode tokens in the text and typed entity labels. Positive
matches sort by score, then tier, then immutable citation ID. Results are
bounded, and unsupported queries return an empty tuple. Historical
`resolve_citation` can resolve an approved citation from a disabled release
while the stored rights allow it. A withdrawal must mark every affected
release excluded and disabled. The resolver then returns no text.

Offline fixtures exercise English lexical and applicability cases.
They do not establish meaningful Nepali or cross-language quality.

## PostgreSQL verification

Development migration `0006_knowledge_corpus` completed with exit code
0. The focused disposable PostgreSQL suite passed all four tests in
39.97 seconds. It covered migration/ORM consistency, ingestion rollback,
idempotency, conflicting revisions, competing enablement attempts,
retrieval gates, and historical citations. The corrected readiness
checker passed five focused offline tests.

On 28 November 2026, the read-only runtime check confirmed that
`kundali_dev_app` connected with TLS `verify-full` and required channel
binding. The readiness checker returned 0 at `0006_knowledge_corpus`
with pgvector installed. Both `public.knowledge_sources` and
`public.knowledge_chunks` were readable and contained zero rows.
Effective `SELECT` was true on both tables. Effective `INSERT`,
`UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`, and `TRIGGER` were false,
as measured by privilege inspection. The production retrieval function
returned zero matches. The local backend started, returned HTTP 200
from `GET /health`, and was stopped after verification.

Publication filtering is enforced by the application's retrieval queries.
PostgreSQL row-level security is disabled on both knowledge tables, so a
role with direct table-level `SELECT` can read draft rows if they are
later imported. The live runtime check used empty tables. Exclusion of
populated but ineligible records was exercised by the disposable suite.
No development corpus has been imported or published. Editorial approval
and launch-jurisdiction review remain pending. Tier 1, hosted embeddings,
and a public retrieval API remain outside this milestone.
