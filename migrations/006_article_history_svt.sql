-- WikiGuardian migration 006
-- Add article_history: Wikipedia's own revision history as a MariaDB
-- System-Versioned Table (SVT), the foundation of the "Wikipedia through time"
-- features (point-in-time view, change timeline, revert / edit-war detection).
--
-- Source data: MariaDB Wikipedia Dataset M (every saved version of each Finnish
-- "History of Finland" article, 2002 - 1 Oct 2026). Loaded by import_dataset_m.py
-- with SET system_versioning_insert_history = 1, so each row carries Wikipedia's
-- real edit times: row_start = when the version was saved, row_end = when the
-- next version replaced it; the latest version has no row_end (stays current).
--
-- Modeled on MariaDB's reference time-machine table
-- (mariadb-system-versioning-wikipedia/schema.sql). Links to the app's articles
-- table logically by page_id = articles.wikipedia_page_id (language_code = 'fi').
-- No FOREIGN KEY on purpose: InnoDB does not allow foreign keys on a table that
-- is PARTITIONed, and the yearly SYSTEM_TIME partitioning below is what keeps
-- "as of <year>" queries fast at full-dataset scale.
--
-- Text is raw wikitext (old versions exist only as wikitext) and COMPRESSED,
-- because consecutive versions are nearly identical. Plan ~5-7 GB for all of M;
-- for a demo, import_dataset_m.py loads only a chosen subset of page_ids.
--
-- This file is intentionally not executed automatically.
-- Requires MariaDB 11.7+ (system versioning + partitioning; 11.8 in use).
--
-- Apply (PowerShell). Copy the command only:
--   & "C:\Program Files\MariaDB 11.8\bin\mysql.exe" -u root -p wikiguardian -e "source migrations/006_article_history_svt.sql"

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
    -- Lets "as of <date>" start from the versions that began before the date;
    -- MariaDB's own history index is ordered by row_end.
    KEY idx_history_start (page_id, row_start)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
  ENGINE=InnoDB
  WITH SYSTEM VERSIONING
  -- One partition per year of history; a version lands in the partition of the
  -- year it stopped being current (its row_end). AUTO adds partitions as needed.
  PARTITION BY SYSTEM_TIME INTERVAL 1 YEAR STARTS '2002-01-01 00:00:00' AUTO PARTITIONS 26;
