"""Shared synthetic knowledge manifest fixtures."""

from app.knowledge.provenance import canonical_bytes, sha256


def payload(
    source_id="fixture-corpus",
    collection="production",
    version=1,
    revision=1,
    text="Synthetic Moon attention in the fifth house.",
):
    chunks = [
        (
            "moon-general",
            {"topic": "planet_general", "planet": "Moon"},
            "Synthetic Moon attention, general entry.",
        ),
        ("moon-fifth", {"topic": "planet_in_house", "planet": "Moon", "house": 5}, text),
        (
            "venus-period",
            {
                "topic": "dasha",
                "method": "vimshottari-v1",
                "level": "AD",
                "lord": "Venus",
                "parent_lord": "Sun",
            },
            "Synthetic Venus Dasha entry.",
        ),
    ]
    return {
        "manifest_schema_version": 1,
        "source": {
            "source_id": source_id,
            "version": version,
            "supersedes_version": version - 1 or None,
            "title": "Synthetic fixture",
            "collection": collection,
            "tier": 3,
            "author": "Test author",
            "edition": "Test edition",
            "publisher": "Test publisher",
            "publication": "2026",
            "language": "en",
            "tradition": "Test",
            "source_url": "https://example.invalid/corpus",
            "artifact_url": "https://example.invalid/artifact",
            "archive_id": "fixture",
            "artifact_format": "text",
            "artifact_sha256": sha256(b"artifact"),
            "retrieved_on": "2026-11-27",
            "selection": "Test only",
            "transcription": "Original",
            "content_sha256": sha256(
                canonical_bytes([[key, body] for key, _, body in sorted(chunks)])
            ),
            "rights": {
                "status": "project_owned",
                "basis": "Synthetic",
                "holder_or_custodian": "Test",
                "evidence": ["https://example.invalid/rights"],
                "attribution": "Test fixture",
                "jurisdictions": ["test"],
                "permitted_uses": ["reproduce", "redistribute", "adapt"],
                "reviewed_on": "2026-11-27",
                "review_reference": "Test-only reference",
            },
        },
        "chunks": [
            {
                "key": key,
                "revision": revision,
                "language": "en",
                "text": body,
                "locator": {
                    "chapter": "1",
                    "page": "1",
                    "canvas": "fixture",
                    "image_sha256": sha256(b""),
                },
                "applicability": rule,
                "content_sha256": sha256(body.encode()),
            }
            for key, rule, body in chunks
        ],
    }
