"""
Engineering Memory domain.

Responsible for synthesizing institutional knowledge from ingested chunks:
  - Architecture map and design decisions
  - Risk register and fragility notes
  - Change intelligence from git commit history
  - Project Memory Brief generation

All work in this domain runs AFTER normal ingestion completes — never
blocking the ingestion pipeline. The extract job is an independent ARQ task.

Generated chunks use source_ref = "__memory__/{twin_id}" to distinguish them
from file-derived chunks, enabling targeted deletion on re-extraction.
"""
