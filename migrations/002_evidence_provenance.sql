-- WikiGuardian migration 002
-- Preserve source-specific evidence provenance.

ALTER TABLE evidence_sources
    ADD COLUMN provenance JSON DEFAULT NULL
    AFTER source_type;
