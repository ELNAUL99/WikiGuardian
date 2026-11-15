ALTER TABLE edit_proposals
    ADD COLUMN edit_summary VARCHAR(1000) NULL
    AFTER editor_name;