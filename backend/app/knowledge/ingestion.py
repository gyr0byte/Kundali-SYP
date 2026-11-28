"""Offline manifest validation and atomic, draft-only imports."""

from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, field_serializer, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.knowledge.chunking import Chunk
from app.knowledge.provenance import Record, Source, canonical_bytes, sha256


class ManifestConflict(ValueError):
    """An immutable release differs from the previously imported revision."""


class Manifest(Record):
    manifest_schema_version: Literal[1]
    source: Source
    chunks: tuple[Chunk, ...] = Field(min_length=1, max_length=1000)

    @field_validator("manifest_schema_version", mode="before")
    @classmethod
    def integer_schema_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Manifest schema version must be an integer")
        return value

    @field_serializer("chunks")
    def serialize_chunks(self, value: tuple[Chunk, ...]) -> list[Chunk]:
        return sorted(value, key=lambda chunk: chunk.key)

    @model_validator(mode="after")
    def verify_chunks(self) -> "Manifest":
        if len({chunk.key for chunk in self.chunks}) != len(self.chunks):
            raise ValueError("A source release may contain only one revision per logical chunk")
        for chunk in self.chunks:
            if chunk.language != self.source.language:
                raise ValueError("Chunk language must match the source artifact")
            if chunk.content_sha256 != sha256(chunk.text.encode("utf-8")):
                raise ValueError("Chunk checksum mismatch")
        if content_digest(self.chunks) != self.source.content_sha256:
            raise ValueError("Source content checksum mismatch")
        return self


def content_digest(chunks: tuple[Chunk, ...]) -> str:
    entries = [[chunk.key, chunk.text] for chunk in sorted(chunks, key=lambda item: item.key)]
    return sha256(canonical_bytes(entries))


def citation_id(source: Source, chunk: Chunk) -> str:
    return f"{source.source_id}@{source.version}/{chunk.key}@{chunk.revision}"


def parse_manifest(payload: bytes, *, artifact: bytes | None = None) -> Manifest:
    if len(payload) > 10_000_000:
        raise ValueError("Manifest is too large")
    # JSON decoders otherwise silently accept duplicate keys.
    import json

    def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("Duplicate JSON keys in manifest")
        return result

    manifest = Manifest.model_validate(json.loads(payload, object_pairs_hook=unique_keys))
    if artifact is not None and sha256(artifact) != manifest.source.artifact_sha256:
        raise ValueError("Source artifact checksum mismatch")
    return manifest


@dataclass(frozen=True)
class ImportResult:
    source_id: str
    version: int
    chunk_count: int
    inserted: bool


def import_manifest(
    session: Session, manifest: Manifest, *, allow_test: bool = False
) -> ImportResult:
    """Own one transaction on a fresh session. Never change publication state."""
    source = manifest.source
    if source.collection == "test" and not allow_test:
        raise ValueError("Test manifests require explicit test-mode import")
    serialized = manifest.model_dump(mode="json")
    serialized["source"]["rights"]["permitted_uses"].sort()
    digest = sha256(canonical_bytes(serialized))
    # A racing identical import can win the INSERT. Retry after its commit.
    for attempt in range(2):
        try:
            with session.begin():
                return _insert_release(session, manifest, digest)
        except IntegrityError:
            if attempt:
                raise
    raise AssertionError("Import retry exhausted")


def _insert_release(session: Session, manifest: Manifest, digest: str) -> ImportResult:
    source = manifest.source
    result = ImportResult(source.source_id, source.version, len(manifest.chunks), False)
    existing = session.get(KnowledgeSource, (source.source_id, source.version))
    if existing is not None:
        if existing.manifest_sha256 != digest:
            raise ManifestConflict("Release already exists with different immutable content")
        return result
    earlier = None
    if source.supersedes_version is not None:
        earlier = session.get(KnowledgeSource, (source.source_id, source.supersedes_version))
        if earlier is None:
            raise ManifestConflict("Superseded release does not exist")
    if earlier is not None:
        previous: dict[str, KnowledgeChunk] = {}
        for previous_chunk in session.scalars(
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.source_id == source.source_id,
                KnowledgeChunk.source_version < source.version,
            )
            .order_by(KnowledgeChunk.source_version.desc())
        ):
            previous.setdefault(previous_chunk.chunk_key, previous_chunk)
        for chunk in manifest.chunks:
            prior = previous.get(chunk.key)
            if prior is not None and (
                chunk.revision < prior.revision
                or (
                    chunk.revision == prior.revision
                    and (
                        chunk.content_sha256 != prior.content_sha256
                        or chunk.locator.model_dump(mode="json", exclude_none=True) != prior.locator
                        or chunk.applicability.model_dump(mode="json", exclude_none=True)
                        != prior.applicability
                    )
                )
            ):
                raise ManifestConflict("Changed chunk requires a new logical revision")
    bibliography = source.model_dump(mode="json", exclude={"rights"})
    rights = source.rights.model_dump(mode="json")
    rights["permitted_uses"].sort()
    session.add(
        KnowledgeSource(
            source_id=source.source_id,
            version=source.version,
            supersedes_version=source.supersedes_version,
            tier=source.tier,
            collection=source.collection,
            rights_status=source.rights.status,
            bibliography=bibliography,
            rights=rights,
            artifact_sha256=source.artifact_sha256,
            content_sha256=source.content_sha256,
            manifest_sha256=digest,
        )
    )
    session.flush()
    session.add_all(
        [
            KnowledgeChunk(
                citation_id=citation_id(source, chunk),
                source_id=source.source_id,
                source_version=source.version,
                chunk_key=chunk.key,
                revision=chunk.revision,
                language=chunk.language,
                topic=chunk.applicability.topic,
                tradition=source.tradition,
                locator=chunk.locator.model_dump(mode="json", exclude_none=True),
                applicability=chunk.applicability.model_dump(mode="json", exclude_none=True),
                content=chunk.text,
                content_sha256=chunk.content_sha256,
            )
            for chunk in manifest.chunks
        ]
    )
    return ImportResult(source.source_id, source.version, len(manifest.chunks), True)


if __name__ == "__main__":
    parser = ArgumentParser(description="Dry-run a knowledge manifest without a database")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--artifact", type=Path)
    args = parser.parse_args()
    validated = parse_manifest(
        args.manifest.read_bytes(),
        artifact=args.artifact.read_bytes() if args.artifact else None,
    )
    print(
        f"Validated {validated.source.source_id}@{validated.source.version}: "
        f"{len(validated.chunks)} chunks. No writes."
    )
