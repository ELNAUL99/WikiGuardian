-- WikiGuardian migration 001
-- Add claim-level decision traceability and critique audit history.
-- This file is intentionally not executed automatically.

ALTER TABLE verification_decisions
    ADD COLUMN claim_id BIGINT UNSIGNED NULL AFTER run_id,
    ADD COLUMN requires_human_review BOOLEAN NOT NULL DEFAULT TRUE,
    ADD INDEX idx_decision_claim (claim_id),
    ADD CONSTRAINT fk_decision_claim
        FOREIGN KEY (claim_id)
        REFERENCES claims (claim_id)
        ON DELETE CASCADE;

CREATE TABLE critique_findings (
    finding_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id BIGINT UNSIGNED NOT NULL,
    claim_id BIGINT UNSIGNED NOT NULL,
    objection_id VARCHAR(100) NOT NULL,
    round_number TINYINT UNSIGNED NOT NULL,
    issue_type VARCHAR(100) NOT NULL,
    severity VARCHAR(30) NOT NULL,
    objection TEXT NOT NULL,
    source_ids JSON DEFAULT NULL,
    requires_reassessment BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (finding_id),
    UNIQUE KEY uq_critique_objection (
        run_id,
        claim_id,
        objection_id
    ),
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

    CONSTRAINT chk_critique_round
        CHECK (round_number BETWEEN 1 AND 2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
