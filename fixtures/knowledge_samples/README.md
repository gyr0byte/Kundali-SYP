# Knowledge Base Test Samples

This directory is designated for sample classical astrological texts and verified commentary chunks used to test the planned knowledge ingestion and retrieval pipeline (`backend/app/knowledge/`).

---

## Status

Currently, this directory contains no sample files. Ingestion modules and vector database schemas are currently stubs.

---

## Planned Format

When populated, knowledge samples will be stored as structured JSON or Markdown documents with metadata attributes:
* `source`: Title of classical or modern treatise (e.g., *Brihat Parashara Hora Shastra*, *Phaladeepika*).
* `chapter`: Chapter number and Sanskrit/English title.
* `verse`: Shloka or verse reference number.
* `text`: English translation and commentary.
* `tags`: Conceptual unit tags (e.g., planet, sign, house, yoga).
* `provenance`: Trust layer indicator (classical text, commentary, or verified astrologer annotation).
