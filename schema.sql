-- ============================================================================
-- WikiGuardian base schema (source of truth)
-- ============================================================================
-- Reconstructed from the application code, because no schema file was ever
-- committed: the live `wikiguardian` database was built by hand in the mysql
-- client and only ALTERed afterwards by migrations 001-004. This file folds
-- those four migrations in and is self-contained: it creates every table the
-- app reads or writes, in dependency order, for a reproducible fresh install.
--
-- Column names match the SQL embedded in app/** and import_dataset_s.py
-- verbatim. Column *types* are inferred from how each value is produced/used
-- and are marked where a judgement call was made; verify against the live
-- database before trusting them as exact.
--
-- NEW in this file: `article_state` is a genuine MariaDB System-Versioned
-- Table (SVT). It was listed in the project handoff as WikiGuardian's own
-- system-versioned state/history but did not exist in code anywhere. No app
-- code reads or writes it yet -- it is schema-only groundwork.
--
-- Requires MariaDB 11.7+ (VECTOR type + VECTOR INDEX). Developed against 11.8.
--
-- Fresh install (PowerShell). Copy the command only, not this prompt:
--   & "C:\Program Files\MariaDB 11.8\bin\mysql.exe" -u root -p < schema.sql
--
-- Every table uses CREATE TABLE IF NOT EXISTS, so running this against the
-- existing database leaves current tables untouched and only creates what is
-- missing (in practice: article_state). It never drops or rewrites data.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS wikiguardian
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE wikiguardian;


-- ----------------------------------------------------------------------------
-- Wikipedia corpus (populated by import_dataset_s.py)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS articles (
    article_id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    wikipedia_page_id   BIGINT UNSIGNED NOT NULL,
    language_code       VARCHAR(8)      NOT NULL,          -- en, fi, sv
    title               VARCHAR(255)    NOT NULL,
    article_url         VARCHAR(500)    NOT NULL,
    created_at          TIMESTAMP       NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (article_id),
    -- Drives the ON DUPLICATE KEY UPDATE path in import_dataset_s.py.
    UNIQUE KEY uq_article_page (language_code, wikipedia_page_id),
    KEY idx_article_title (language_code, title)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS article_revisions (
    revision_id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    article_id              BIGINT UNSIGNED NOT NULL,
    wikipedia_revision_id   BIGINT UNSIGNED NOT NULL,      -- original Wikipedia rev_id
    wikipedia_timestamp     DATETIME        NULL,          -- original Wikipedia revision time
    article_content         MEDIUMTEXT      NOT NULL,
    content_hash            CHAR(64)        NOT NULL,       -- sha256 hex

    PRIMARY KEY (revision_id),
    UNIQUE KEY uq_revision (article_id, wikipedia_revision_id),

    CONSTRAINT fk_revision_article
        FOREIGN KEY (article_id)
        REFERENCES articles (article_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS article_chunks (
    chunk_id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    article_id              BIGINT UNSIGNED NOT NULL,
    wikipedia_revision_id   BIGINT UNSIGNED NOT NULL,
    chunk_index             INT UNSIGNED    NOT NULL DEFAULT 0,
    section_title           VARCHAR(255)    NULL,
    chunk_text              MEDIUMTEXT      NOT NULL,
    content_hash            CHAR(64)        NOT NULL,

    PRIMARY KEY (chunk_id),
    UNIQUE KEY uq_chunk (article_id, wikipedia_revision_id, chunk_index),
    -- Supports the retriever's join on (article_id, wikipedia_revision_id).
    KEY idx_chunk_revision (article_id, wikipedia_revision_id),

    CONSTRAINT fk_chunk_article
        FOREIGN KEY (article_id)
        REFERENCES articles (article_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id            BIGINT UNSIGNED NOT NULL,
    embedding           VECTOR(1024)    NOT NULL,          -- BGE-M3, 1024 dims
    embedding_model     VARCHAR(100)    NOT NULL,
    embedding_truncated TINYINT         NOT NULL DEFAULT 0,

    PRIMARY KEY (chunk_id),
    -- idx_chunk_embedding is the index confirmed in use by EXPLAIN (handoff s.5).
    -- M=16 (not the default 6) for recall at 1024 dims; see the vector-rag README.
    VECTOR INDEX idx_chunk_embedding (embedding) M=16 DISTANCE=cosine,

    CONSTRAINT fk_embedding_chunk
        FOREIGN KEY (chunk_id)
        REFERENCES article_chunks (chunk_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ----------------------------------------------------------------------------
-- Edit proposals and extracted claims
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS edit_proposals (
    proposal_id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    article_id      BIGINT UNSIGNED NOT NULL,
    editor_name     VARCHAR(255)    NULL,
    edit_summary    VARCHAR(1000)   NULL,                  -- migration 004
    original_text   MEDIUMTEXT      NOT NULL,
    proposed_text   MEDIUMTEXT      NOT NULL,
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending',
    submitted_at    TIMESTAMP       NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (proposal_id),
    KEY idx_proposal_status (status),
    KEY idx_proposal_article (article_id),

    CONSTRAINT fk_proposal_article
        FOREIGN KEY (article_id)
        REFERENCES articles (article_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_proposal_status CHECK (
        status IN (
            'pending', 'running', 'completed',
            'failed', 'approved', 'rejected'
        )
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS claims (
    claim_id        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    proposal_id     BIGINT UNSIGNED NOT NULL,
    claim_text      TEXT            NOT NULL,
    subject         TEXT            NULL,
    predicate       TEXT            NULL,
    object_value    TEXT            NULL,
    created_at      TIMESTAMP       NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (claim_id),
    KEY idx_claim_proposal (proposal_id),

    CONSTRAINT fk_claim_proposal
        FOREIGN KEY (proposal_id)
        REFERENCES edit_proposals (proposal_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ----------------------------------------------------------------------------
-- Verification runs, evidence, decisions, critique
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS verification_runs (
    run_id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    proposal_id     BIGINT UNSIGNED NOT NULL,
    llm_model       VARCHAR(255)    NULL,
    embedding_model VARCHAR(255)    NULL,
    status          VARCHAR(20)     NOT NULL DEFAULT 'running',
    started_at      TIMESTAMP       NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP       NULL,
    error_message   TEXT            NULL,

    PRIMARY KEY (run_id),
    KEY idx_run_proposal (proposal_id),
    KEY idx_run_status (status),

    CONSTRAINT fk_run_proposal
        FOREIGN KEY (proposal_id)
        REFERENCES edit_proposals (proposal_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_run_status CHECK (
        status IN ('running', 'completed', 'failed')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS evidence_sources (
    evidence_id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_url      VARCHAR(2048)   NOT NULL,
    source_title    VARCHAR(1000)   NULL,
    publisher       VARCHAR(500)    NULL,
    published_at    DATETIME        NULL,
    source_content  LONGTEXT        NULL,
    content_hash    CHAR(64)        NOT NULL,
    source_type     VARCHAR(50)     NOT NULL,              -- internal_wikipedia | external_source
    provenance      JSON            NULL,                  -- migration 002
    retrieved_at    TIMESTAMP       NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (evidence_id),
    -- Backs the external-source dedupe lookup (url + hash + type).
    KEY idx_evidence_dedupe (content_hash, source_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS claim_evidence (
    claim_id            BIGINT UNSIGNED NOT NULL,
    evidence_id         BIGINT UNSIGNED NOT NULL,
    evidence_relation   VARCHAR(20)     NOT NULL,          -- supports | contradicts | neutral
    relevant_excerpt    TEXT            NULL,
    relevance_score     FLOAT           NULL,
    explanation         TEXT            NULL,

    -- Composite PK backs the ON DUPLICATE KEY UPDATE in persistence_service.
    PRIMARY KEY (claim_id, evidence_id),
    KEY idx_claim_evidence_evidence (evidence_id),

    CONSTRAINT fk_claim_evidence_claim
        FOREIGN KEY (claim_id)
        REFERENCES claims (claim_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_claim_evidence_source
        FOREIGN KEY (evidence_id)
        REFERENCES evidence_sources (evidence_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS verification_decisions (
    decision_id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id                  BIGINT UNSIGNED NOT NULL,
    claim_id                BIGINT UNSIGNED NULL,          -- migration 001
    verdict                 VARCHAR(30)     NOT NULL,      -- supported | contradicted | insufficient_evidence
    confidence              FLOAT           NULL,
    explanation             TEXT            NULL,
    verification_history    JSON            NULL,          -- migration 003
    recommendation          JSON            NULL,
    requires_human_review   BOOLEAN         NOT NULL DEFAULT TRUE,  -- migration 001
    decided_at              TIMESTAMP       NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (decision_id),
    KEY idx_decision_run (run_id),
    KEY idx_decision_claim (claim_id),

    CONSTRAINT fk_decision_run
        FOREIGN KEY (run_id)
        REFERENCES verification_runs (run_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_decision_claim
        FOREIGN KEY (claim_id)
        REFERENCES claims (claim_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- Verbatim from migration 001.
CREATE TABLE IF NOT EXISTS critique_findings (
    finding_id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id                  BIGINT UNSIGNED NOT NULL,
    claim_id                BIGINT UNSIGNED NOT NULL,
    objection_id            VARCHAR(100)    NOT NULL,
    round_number            TINYINT UNSIGNED NOT NULL,
    issue_type              VARCHAR(100)    NOT NULL,
    severity                VARCHAR(30)     NOT NULL,
    objection               TEXT            NOT NULL,
    source_ids              JSON            DEFAULT NULL,
    requires_reassessment   BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMP       NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (finding_id),
    UNIQUE KEY uq_critique_objection (run_id, claim_id, objection_id),
    KEY idx_critique_run (run_id),
    KEY idx_critique_claim (claim_id),

    CONSTRAINT fk_critique_run
        FOREIGN KEY (run_id)
        REFERENCES verification_runs (run_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_critique_claim
        FOREIGN KEY (claim_id)
        REFERENCES claims (claim_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_critique_round CHECK (round_number BETWEEN 1 AND 2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ----------------------------------------------------------------------------
-- Human review audit trail
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS review_actions (
    review_id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    proposal_id         BIGINT UNSIGNED NOT NULL,
    reviewer_name       VARCHAR(255)    NOT NULL,
    action              VARCHAR(20)     NOT NULL,          -- approved | rejected
    reviewer_comment    TEXT            NOT NULL,
    reviewed_at         TIMESTAMP       NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (review_id),
    KEY idx_review_proposal (proposal_id),

    CONSTRAINT fk_review_proposal
        FOREIGN KEY (proposal_id)
        REFERENCES edit_proposals (proposal_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_review_action CHECK (action IN ('approved', 'rejected'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ----------------------------------------------------------------------------
-- article_state  --  System-Versioned Table (SVT), pre-existing
-- ----------------------------------------------------------------------------
-- Reverse-engineered from the live database via SHOW CREATE TABLE. This table
-- already existed (created by hand, already WITH SYSTEM VERSIONING) and was
-- never referenced by application code. It is a content-snapshot history: a
-- record of article *content* over time. Left here as-is to document reality;
-- the app does not read or write it. The editorial-status timeline the app
-- actually uses is guardian_article_state, below.

CREATE TABLE IF NOT EXISTS article_state (
    state_id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    article_id              BIGINT UNSIGNED NOT NULL,
    article_content         LONGTEXT        NOT NULL,
    wikipedia_revision_id   BIGINT UNSIGNED NULL,
    state_description       VARCHAR(500)    NULL,
    recorded_by             VARCHAR(100)    NULL DEFAULT 'WikiGuardian',

    PRIMARY KEY (state_id),
    KEY idx_state_article (article_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  WITH SYSTEM VERSIONING;


-- ----------------------------------------------------------------------------
-- guardian_article_state  --  System-Versioned Table (SVT), app-owned
-- ----------------------------------------------------------------------------
-- WikiGuardian's own editorial view of each article: its verification status
-- and confidence. One current row per article (PRIMARY KEY article_id), updated
-- in place, so MariaDB archives every past status automatically and you can ask
-- what WikiGuardian believed at any point in time, e.g.:
--
--   SELECT * FROM guardian_article_state
--   FOR SYSTEM_TIME AS OF TIMESTAMP '2026-11-01 00:00:00'
--   WHERE article_id = 42;
--
-- This is WikiGuardian's internal temporal record and is deliberately distinct
-- from article_revisions.wikipedia_timestamp (Wikipedia's own edit chronology).
-- row_start/row_end are generated and INVISIBLE, so ordinary INSERT/SELECT and
-- SELECT * ignore them; only explicit FOR SYSTEM_TIME queries see history.
-- Written by app/services/article_state_service.py.

CREATE TABLE IF NOT EXISTS guardian_article_state (
    article_id          BIGINT UNSIGNED NOT NULL,
    guardian_status     VARCHAR(30)     NOT NULL DEFAULT 'unverified',
                                        -- unverified | under_review | verified | disputed
    current_revision_id BIGINT UNSIGNED NULL,     -- article_revisions this state trusts
    last_proposal_id    BIGINT UNSIGNED NULL,     -- proposal that last moved the state
    last_run_id         BIGINT UNSIGNED NULL,     -- verification run behind the state
    confidence          FLOAT           NULL,
    note                VARCHAR(1000)   NULL,
    updated_by          VARCHAR(255)    NULL,      -- reviewer name, or 'system'

    row_start TIMESTAMP(6) GENERATED ALWAYS AS ROW START INVISIBLE,
    row_end   TIMESTAMP(6) GENERATED ALWAYS AS ROW END   INVISIBLE,
    PERIOD FOR SYSTEM_TIME (row_start, row_end),

    PRIMARY KEY (article_id),
    KEY idx_gstate_status (guardian_status),

    CONSTRAINT fk_gstate_article
        FOREIGN KEY (article_id)
        REFERENCES articles (article_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_gstate_revision
        FOREIGN KEY (current_revision_id)
        REFERENCES article_revisions (revision_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_gstate_proposal
        FOREIGN KEY (last_proposal_id)
        REFERENCES edit_proposals (proposal_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_gstate_run
        FOREIGN KEY (last_run_id)
        REFERENCES verification_runs (run_id)
        ON DELETE SET NULL,

    CONSTRAINT chk_gstate_status CHECK (
        guardian_status IN (
            'unverified', 'under_review', 'verified', 'disputed'
        )
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  WITH SYSTEM VERSIONING;


-- ----------------------------------------------------------------------------
-- article_history  --  System-Versioned Table (SVT), Wikipedia revision history
-- ----------------------------------------------------------------------------
-- Wikipedia's own edit history over time (MariaDB Dataset M), the foundation of
-- the "Wikipedia through time" features: point-in-time views, change timelines,
-- and revert / edit-war detection. Loaded by import_dataset_m.py with
-- system_versioning_insert_history so each row carries Wikipedia's real edit
-- times. Links to articles logically by page_id = articles.wikipedia_page_id
-- (language_code = 'fi'); no FOREIGN KEY, because InnoDB forbids foreign keys on
-- a PARTITIONed table and the yearly SYSTEM_TIME partitioning keeps "as of
-- <date>" fast. Text is raw wikitext, COMPRESSED. See migration 006.

CREATE TABLE IF NOT EXISTS article_history (
    page_id     BIGINT UNSIGNED NOT NULL,            -- Wikipedia page id (= articles.wikipedia_page_id)
    title       VARCHAR(255)    NOT NULL,            -- can change over time (pages get renamed)
    rev_id      BIGINT UNSIGNED NOT NULL,            -- Wikipedia revision id of this version
    parent_id   BIGINT UNSIGNED NULL,                -- previous rev_id, as given by the dump
    editor      VARCHAR(255)    NULL,                 -- username or IP / temp account
    anonymous   BOOLEAN         NOT NULL DEFAULT FALSE,
    comment     TEXT            NULL,                 -- edit summary
    minor       BOOLEAN         NOT NULL DEFAULT FALSE,
    sha1        CHAR(31)        NULL,                 -- same hash = same text: how reverts are found
    bytes       INT UNSIGNED    NULL,                 -- length of the text in bytes

    text        MEDIUMTEXT COMPRESSED NOT NULL,       -- raw wikitext, compressed value-by-value

    row_start TIMESTAMP(6) GENERATED ALWAYS AS ROW START INVISIBLE,
    row_end   TIMESTAMP(6) GENERATED ALWAYS AS ROW END   INVISIBLE,
    PERIOD FOR SYSTEM_TIME (row_start, row_end),

    PRIMARY KEY (page_id),
    KEY idx_history_sha1 (sha1),                      -- revert detection
    KEY idx_history_start (page_id, row_start)        -- "as of <date>" start key
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
  ENGINE=InnoDB
  WITH SYSTEM VERSIONING
  PARTITION BY SYSTEM_TIME INTERVAL 1 YEAR STARTS '2002-01-01 00:00:00' AUTO PARTITIONS 26;
