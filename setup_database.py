#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Job Assistant - Database Bootstrap (clean edition)
==================================================

- Creates DB (if missing)
- Installs extensions (pgvector, uuid-ossp)
- Creates tables aligned with your SQL dump:
    • users
    • conversations
    • prompts        (prompt_key PRIMARY KEY, last_updated)
    • settings       (setting_key PRIMARY KEY, last_updated)
    • shared_chats
    • jobs           (id PRIMARY KEY, title, job_zone INT, embedding vector, onet_code, description, onet_profile)
- Seeds minimal settings/prompts + a few sample jobs
- Optionally imports jobs from jobs_rows.csv (with embedding as vector)

Run:
    python setup_database.py
"""

import os
import sys
import json
import csv
import logging
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی
load_dotenv()

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout
)
log = logging.getLogger("setup")

# ------------------------------------------------------------------------------
# Config (از فایل .env)
# ------------------------------------------------------------------------------
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")

DEFAULT_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "models/gemini-flash-latest")

CSV_PATH = os.getenv("JOBS_CSV_PATH", "jobs_rows.csv")

PROJECT_DSN = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
ADMIN_DSN   = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/postgres"

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _engine(dsn: str):
    return create_engine(dsn, pool_pre_ping=True)

def to_pgvector_literal(vec):
    """list[float] -> '[f1,f2,...]' as pgvector literal string."""
    if isinstance(vec, str):
        # assume already a JSON string like "[...]" -> keep as is
        try:
            arr = json.loads(vec)
            vec = arr
        except Exception:
            return vec  # let db fail if it's not valid
    if not isinstance(vec, (list, tuple)):
        raise ValueError("embedding must be list/tuple or JSON string")
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"

# ------------------------------------------------------------------------------
# 1) Create database (if not exists)
# ------------------------------------------------------------------------------
def create_database_if_not_exists():
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database="postgres"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (DB_NAME,))
        exists = cur.fetchone()
        if not exists:
            log.info(f"Creating database '{DB_NAME}' ...")
            cur.execute(f'CREATE DATABASE "{DB_NAME}";')
            log.info("✅ Database created.")
        else:
            log.info("✅ Database already exists.")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        log.error(f"❌ create_database_if_not_exists: {e}")
        return False

# ------------------------------------------------------------------------------
# 2) Extensions
# ------------------------------------------------------------------------------
def create_extensions():
    try:
        engine = _engine(PROJECT_DSN)
        with engine.connect() as conn:
            trx = conn.begin()
            try:
                conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
                trx.commit()
                log.info("✅ Extension ready: uuid-ossp")
            except Exception as e:
                trx.rollback()
                log.error(f"❌ create_extensions: {e}")
                return False
        return True
    except Exception as e:
        log.error(f"❌ create_extensions(engine): {e}")
        return False

# ------------------------------------------------------------------------------
# 3) Tables (aligned with your SQL)
# ------------------------------------------------------------------------------
def create_tables():
    # users (similar to your current app expectations)
    users_table = """
    CREATE TABLE IF NOT EXISTS public.users (
        id SERIAL PRIMARY KEY,
        telegram_user_id VARCHAR(100) UNIQUE NOT NULL,
        first_name VARCHAR(100),
        ip_address INET,
        user_agent TEXT,
        browser_name VARCHAR(50),
        browser_version VARCHAR(20),
        operating_system VARCHAR(50),
        device_type VARCHAR(20),
        country VARCHAR(50),
        city VARCHAR(50),
        timezone VARCHAR(50),
        language VARCHAR(10),
        referrer TEXT,
        session_id UUID,
        visit_count INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        last_seen TIMESTAMP DEFAULT NOW()
    );
    """

    # conversations (user_embedding as vector; app casts to vector)
    conversations_table = """
    CREATE TABLE IF NOT EXISTS public.conversations (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
        conversation_history JSONB DEFAULT '[]'::jsonb,
        career_profile JSONB,
        evidence JSONB,
        riasec_scores JSONB,
        work_values_scores JSONB,
        work_styles_scores JSONB,
        job_zone_estimate INTEGER,
        job_zone_justification TEXT,
        personality_paragraph TEXT,
        final_report_text TEXT,
        report_generated TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """

    # prompts (key as PRIMARY KEY + last_updated)
    prompts_table = """
    CREATE TABLE IF NOT EXISTS public.prompts (
        prompt_key TEXT PRIMARY KEY,
        prompt_value TEXT NOT NULL,
        last_updated TIMESTAMPTZ DEFAULT NOW()
    );
    """

    # settings (key as PRIMARY KEY + last_updated)
    settings_table = """
    CREATE TABLE IF NOT EXISTS public.settings (
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT NOT NULL,
        last_updated TIMESTAMPTZ DEFAULT NOW()
    );
    """

    # shared_chats (as your app uses)
    shared_chats_table = """
    CREATE TABLE IF NOT EXISTS public.shared_chats (
        id SERIAL PRIMARY KEY,
        share_id VARCHAR(50) UNIQUE NOT NULL,
        original_user_id VARCHAR(100) NOT NULL,
        conversation_data JSONB NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '30 days'),
        view_count INTEGER DEFAULT 0,
        last_viewed_at TIMESTAMP
    );
    """

    # jobs (ALIGNED: job_zone INT exists; embedding vector (no dimension))
    jobs_table = """
    CREATE TABLE IF NOT EXISTS public.jobs (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        job_zone INT,
        onet_code VARCHAR(50),
        description TEXT,
        onet_profile JSONB
    );

    -- simple btree index on job_zone for filtering
    CREATE INDEX IF NOT EXISTS jobs_job_zone_idx ON public.jobs (job_zone);

    -- ایندکس وکتور را حذف کنید
    -- CREATE INDEX IF NOT EXISTS jobs_embedding_idx
    --   ON public.jobs USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
    """

    stmts = [
        ("users", users_table),
        ("conversations", conversations_table),
        ("prompts", prompts_table),
        ("settings", settings_table),
        ("shared_chats", shared_chats_table),
        ("jobs", jobs_table),
    ]

    try:
        engine = _engine(PROJECT_DSN)
        with engine.connect() as conn:
            for name, sql in stmts:
                trx = conn.begin()
                try:
                    conn.execute(text(sql))
                    trx.commit()
                    log.info(f"✅ table '{name}' ready")
                except Exception as e:
                    trx.rollback()
                    log.error(f"❌ create_tables[{name}]: {e}")
                    return False
        return True
    except Exception as e:
        log.error(f"❌ create_tables(engine): {e}")
        return False

# ------------------------------------------------------------------------------
# 4) Seed minimal data (with rollback-per-row safety)
# ------------------------------------------------------------------------------
def insert_initial_data():
    initial_settings = [
        ("GEMINI_API_KEY", DEFAULT_GEMINI_API_KEY),
        ("SELECTED_LLM_MODEL", DEFAULT_MODEL),
        ("ADMIN_PASSWORD", os.getenv("ADMIN_PASSWORD")),
        ("MAX_CONVERSATION_LENGTH", os.getenv("MAX_CONVERSATION_LENGTH", "100")),
        ("SESSION_TIMEOUT", os.getenv("SESSION_TIMEOUT", "3600")),
    ]

    initial_prompts = [
        ("COUNSELOR_MANIFESTO", "شما یک مشاور شغلی حرفه‌ای هستید که به کاربران کمک می‌کنید تا مسیر شغلی مناسب خود را پیدا کنند."),
        ("EVIDENCE_EXTRACTION_PROMPT", "از مکالمه زیر، شواهد مربوط به علایق، ارزش‌ها و سبک کاری کاربر را استخراج کنید."),
        ("PERSONALITY_PARAGRAPH_PROMPT", "بر اساس پروفایل شغلی زیر، یک پاراگراف شخصیت‌شناسی بنویسید."),
        ("FINAL_REPORT_PROMPT", "گزارش نهایی مشاوره شغلی را بر اساس اطلاعات زیر بنویسید."),
        ("SYSTEM_ERROR_MESSAGE", "متاسفانه خطایی در سیستم رخ داده است. لطفاً دوباره تلاش کنید."),
        ("UNEXPECTED_ERROR_MESSAGE", "خطای غیرمنتظره‌ای رخ داده است."),
        ("ANALYSIS_START_MESSAGE", "تحلیل اطلاعات شما شروع شد. لطفاً صبر کنید..."),
        ("OUTPUT_PROTOCOL", "لطفاً پاسخ خود را به صورت JSON و فارسی ارائه دهید."),
    ]

    sample_jobs = [
        ("مهندس نرم‌افزار", "توسعه و طراحی نرم‌افزارهای کامپیوتری", 4),
        ("طراح گرافیک", "طراحی بصری و گرافیکی برای پروژه‌های مختلف", 3),
        ("مدیر پروژه", "مدیریت و هماگی پروژه‌های سازمانی", 5),
    ]

    try:
        engine = _engine(PROJECT_DSN)
        with engine.connect() as conn:
            # settings (upsert on key)
            for key, val in initial_settings:
                trx = conn.begin()
                try:
                    conn.execute(
                        text("""
                            INSERT INTO public.settings (setting_key, setting_value)
                            VALUES (:k, :v)
                            ON CONFLICT (setting_key)
                            DO UPDATE SET setting_value = EXCLUDED.setting_value,
                                          last_updated = NOW();
                        """),
                        {"k": key, "v": val}
                    )
                    trx.commit()
                    log.info(f"✅ setting: {key}")
                except Exception as e:
                    trx.rollback()
                    log.warning(f"⚠️ settings[{key}]: {e}")

            # prompts (upsert on key)
            for key, val in initial_prompts:
                trx = conn.begin()
                try:
                    conn.execute(
                        text("""
                            INSERT INTO public.prompts (prompt_key, prompt_value)
                            VALUES (:k, :v)
                            ON CONFLICT (prompt_key)
                            DO UPDATE SET prompt_value = EXCLUDED.prompt_value,
                                          last_updated = NOW();
                        """),
                        {"k": key, "v": val}
                    )
                    trx.commit()
                    log.info(f"✅ prompt: {key}")
                except Exception as e:
                    trx.rollback()
                    log.warning(f"⚠️ prompts[{key}]: {e}")

            # a few sample jobs without id/embedding (for health check)
            for title, desc, zone in sample_jobs:
                trx = conn.begin()
                try:
                    conn.execute(
                        text("""
                            INSERT INTO public.jobs (id, title, description, job_zone)
                            VALUES (floor(random()*1000000)::int, :t, :d, :z)
                            ON CONFLICT (id) DO NOTHING;
                        """),
                        {"t": title, "d": desc, "z": zone}
                    )
                    trx.commit()
                    log.info(f"✅ sample job: {title}")
                except Exception as e:
                    trx.rollback()
                    log.warning(f"⚠️ sample job[{title}]: {e}")

        return True
    except Exception as e:
        log.error(f"❌ insert_initial_data: {e}")
        return False

# ------------------------------------------------------------------------------
# 5) Import jobs from CSV (optional)
# ------------------------------------------------------------------------------
def import_jobs_from_csv(csv_path: str = CSV_PATH):
    if not os.path.exists(csv_path):
        log.warning(f"CSV '{csv_path}' not found. Skipping jobs import.")
        return True  # not an error

    engine = _engine(PROJECT_DSN)
    try:
        with engine.connect() as conn, open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            batch, batch_size, row_num = [], 200, 0

            for row in reader:
                row_num += 1
                try:
                    id_  = int(row.get("id"))
                    code = row.get("onet_code")
                    title = row.get("title")
                    desc  = row.get("description")
                    onet_profile = json.loads(row.get("onet_profile") or "{}")

                    batch.append({
                        "id": id_,
                        "onet_code": code,
                        "title": title,
                        "description": desc,
                        "onet_profile": json.dumps(onet_profile, ensure_ascii=False),
                    })

                    if len(batch) >= batch_size:
                        _flush_jobs_batch(conn, batch)
                        batch.clear()
                        log.info(f"Inserted {row_num} rows so far...")

                except Exception as e:
                    log.warning(f"Row {row_num} skipped: {e}")

            if batch:
                _flush_jobs_batch(conn, batch)

        log.info("✅ CSV import finished.")
        return True
    except Exception as e:
        log.error(f"❌ import_jobs_from_csv: {e}")
        return False

def _flush_jobs_batch(conn, rows):
    trx = conn.begin()
    try:
        # embedding as CAST(:embedding AS vector)
        conn.execute(
            text("""
                INSERT INTO public.jobs (id, onet_code, title, description, onet_profile)
                VALUES (:id, :onet_code, :title, :description, CAST(:onet_profile AS jsonb))
                ON CONFLICT (id) DO UPDATE SET
                    onet_code    = EXCLUDED.onet_code,
                    title        = EXCLUDED.title,
                    description  = EXCLUDED.description,
                    onet_profile = EXCLUDED.onet_profile
            """),
            rows
        )
        trx.commit()
    except Exception as e:
        trx.rollback()
        raise

# ------------------------------------------------------------------------------
# 6) Verify
# ------------------------------------------------------------------------------
def verify_setup():
    try:
        engine = _engine(PROJECT_DSN)
        with engine.connect() as conn:
            for tbl in ["users","conversations","prompts","settings","shared_chats","jobs"]:
                try:
                    cnt = conn.execute(text(f"SELECT COUNT(*) FROM public.{tbl}")).scalar()
                    log.info(f"✅ {tbl}: {cnt} rows")
                except Exception as e:
                    log.error(f"❌ verify table {tbl}: {e}")
                    return False

            exts = conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname IN ('vector','uuid-ossp');")
            ).fetchall()
            log.info(f"✅ extensions: {[e[0] for e in exts]}")
        return True
    except Exception as e:
        log.error(f"❌ verify_setup: {e}")
        return False

# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------
def main():
    log.info("🚀 DB bootstrap started")
    if not create_database_if_not_exists():
        return False
    if not create_extensions():
        return False
    if not create_tables():
        return False
    if not insert_initial_data():
        return False
    # CSV is optional; run if present
    if not import_jobs_from_csv(CSV_PATH):
        return False
    if not verify_setup():
        return False
    log.info("🎉 All done!")
    log.info(f"DB  : {DB_NAME}")
    log.info(f"Host: {DB_HOST}:{DB_PORT}")
    log.info(f"User: {DB_USER}")
    return True

if __name__ == "__main__":
    try:
        ok = main()
        sys.exit(0 if ok else 1)
    except KeyboardInterrupt:
        log.warning("Interrupted by user.")
        sys.exit(1)
    except Exception as e:
        log.error(f"❌ Unexpected error: {e}")
        sys.exit(1)