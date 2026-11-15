-- Preserve every Agent 5 assessment, including critique-triggered reassessments.

ALTER TABLE verification_decisions
    ADD COLUMN verification_history JSON NULL
    AFTER explanation;
