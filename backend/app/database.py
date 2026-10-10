from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


def get_connection():
    settings = get_settings()

    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    return psycopg.connect(
        settings.database_url,
        connect_timeout=10,
        row_factory=dict_row,
    )


def initialize_database() -> None:
    """Create ONEID tables if they do not already exist."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS oneid_users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    username_normalized TEXT NOT NULL UNIQUE,
                    nickname TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user'
                        CHECK (role IN ('user', 'admin')),
                    global_suspended BOOLEAN NOT NULL DEFAULT FALSE,
                    suspension_reason TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS oneid_site_suspensions (
                    user_id TEXT NOT NULL
                        REFERENCES oneid_users(user_id)
                        ON DELETE CASCADE,
                    client_id TEXT NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, client_id)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS oneid_oauth_codes (
                    code_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL
                        REFERENCES oneid_users(user_id)
                        ON DELETE CASCADE,
                    client_id TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    code_challenge TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS
                    idx_oneid_oauth_codes_expires_at
                ON oneid_oauth_codes (expires_at)
            """)