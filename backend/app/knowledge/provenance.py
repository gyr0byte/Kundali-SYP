"""Validated source specifications and canonical fingerprints."""

import hashlib
import json
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

Key = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Language = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$")]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]
Version = Annotated[int, Field(strict=True, ge=1, le=2147483647)]

CLEARED = ("public_domain_mark", "licensed", "project_owned")
SERVING_USES = frozenset(("reproduce", "redistribute", "adapt"))


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rights(Record):
    status: Literal["public_domain_mark", "licensed", "project_owned", "unresolved", "excluded"]
    basis: Label
    holder_or_custodian: Label
    evidence: tuple[HttpUrl, ...] = Field(min_length=1)
    attribution: Label
    jurisdictions: tuple[Label, ...] = Field(min_length=1)
    permitted_uses: frozenset[
        Literal["reproduce", "redistribute", "adapt", "third_party_processing"]
    ]
    reviewed_on: date
    review_reference: Label

    @model_validator(mode="after")
    def verify_clearance(self) -> "Rights":
        if self.status in CLEARED and not SERVING_USES <= self.permitted_uses:
            raise ValueError(
                "Cleared rights must cover reproduction, redistribution and adaptation"
            )
        if self.status not in CLEARED and self.permitted_uses:
            raise ValueError("Uncleared rights cannot grant permitted uses")
        return self


class Source(Record):
    source_id: Key
    version: Version
    supersedes_version: Version | None = None
    tier: Literal[2, 3]
    collection: Literal["production", "test"]
    title: Label
    author: Label
    translator: Label | None = None
    editor: Label | None = None
    edition: Label
    publisher: Label
    publication: Label
    language: Language
    tradition: Label = Field(max_length=100)
    source_url: HttpUrl
    artifact_url: HttpUrl
    archive_id: Label
    retrieved_on: date
    artifact_format: Label
    artifact_sha256: Digest
    content_sha256: Digest
    selection: Label
    transcription: Label
    rights: Rights

    @model_validator(mode="after")
    def verify_lineage(self) -> "Source":
        if self.source_id.startswith("test-") != (self.collection == "test"):
            raise ValueError("Test sources must use the test- namespace")
        if self.supersedes_version != (self.version - 1 if self.version > 1 else None):
            raise ValueError("Each new release must supersede its immediate predecessor")
        if (
            self.tier == 2
            and self.rights.status == "project_owned"
            and self.collection == "production"
        ):
            raise ValueError("Project-owned reference material belongs in Tier 3")
        return self


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
