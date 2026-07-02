-- ============================================================================
-- Interactive Tutorial Builder — Supabase Postgres schema
-- Run this ONCE in the Supabase dashboard → SQL Editor → New query → Run.
--
-- These are the application's own tables. The LangGraph checkpoint tables
-- (checkpoints, checkpoint_writes, checkpoint_blobs, ...) are created
-- automatically by the app on first connect via PostgresSaver.setup(), so you
-- do NOT need to create them here.
-- ============================================================================

-- Cross-session memory — one row per course (shared by all its sessions).
create table if not exists course_memory (
    course          text primary key,
    prior_concepts  jsonb       not null default '[]'::jsonb,
    mcq_topics      jsonb       not null default '[]'::jsonb,
    feedback        jsonb       not null default '[]'::jsonb,
    eval_history    jsonb       not null default '[]'::jsonb,
    updated_at      timestamptz not null default now()
);

-- Cost ledger — a single accumulating document (id is always 'global').
create table if not exists cost_ledger (
    id          text primary key default 'global',
    data        jsonb       not null default '{}'::jsonb,
    updated_at  timestamptz not null default now()
);

-- Run metadata (RunInfo) — mirrored from the API so the run list survives restarts.
-- (Graph state itself lives in the LangGraph checkpoint tables, not here.)
create table if not exists runs (
    run_id        text primary key,
    course_name   text,
    session_name  text,
    status        text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    data          jsonb       not null
);

create index if not exists runs_created_idx on runs (created_at desc);
