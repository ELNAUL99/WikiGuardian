-- WikiGuardian migration 005
-- Add guardian_article_state as a MariaDB System-Versioned Table (SVT).
--
-- Context: the live database already has a table literally named article_state,
-- but it is a content-snapshot history with a different structure and no code
-- references it. Rather than disturb it, WikiGuardian's editorial-status
-- timeline lives in its own table, guardian_article_state, written by
-- app/services/article_state_service.py.
--
-- One current row per article (PRIMARY KEY article_id), updated in place, so
-- system versioning records every status transition and FOR SYSTEM_TIME AS OF
-- can report what WikiGuardian believed about an article at any past time.
--
-- This file is intentionally not executed automatically.
-- Requires MariaDB 11.7+ (system versioning; 11.8 in use).
--
-- Apply (PowerShell). Copy the command only:
--   & "C:\Program Files\MariaDB 11.8\bin\mysql.exe" -u root -p wikiguardian -e "source migrations/005_guardian_article_state_svt.sql"

CREATE TABLE IF NOT EXISTS guardian_article_state (
    article_id          BIGINT UNSIGNED NOT NULL,
    guardian_status     VARCHAR(30)     NOT NULL DEFAULT 'unverified',
                                        -- unverified | under_review | verified | disputed
    current_revision_id BIGINT UNSIGNED NULL,
    last_proposal_id    BIGINT UNSIGNED NULL,
    last_run_id         BIGINT UNSIGNED NULL,
    confidence          FLOAT           NULL,
    note                VARCHAR(1000)   NULL,
    updated_by          VARCHAR(255)    NULL,

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
