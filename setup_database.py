#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Job Assistant - Database Bootstrap (v3 - with Credits & Payments)
==================================================

- Creates DB (if missing)
- Installs extensions (pgvector, uuid-ossp)
- Creates tables:
    • users (phone_number PRIMARY KEY)
    • conversations (links to users.id OR an anonymous_user_id)
    • otps (for SMS login)
    • prompts
    • settings
    • shared_chats
    • [NEW] user_credits (manages message credits and subscriptions)
    • [NEW] referrals (manages referral codes)
    • [NEW] payments (manages payment transactions)
- Seeds minimal settings/prompts
"""

import os
import sys
import json
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
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
DEFAULT_JWT_SECRET = os.getenv("JWT_SECRET_KEY", "DEFAULT_FALLBACK_SECRET_KEY_CHANGE_ME")

PROJECT_DSN = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
ADMIN_DSN   = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/postgres"

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _engine(dsn: str):
    return create_engine(dsn, pool_pre_ping=True)

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
# 3) Tables (v3 Schema)
# ------------------------------------------------------------------------------
def create_tables():
    # users (جدید: مبتنی بر شماره موبایل)
    users_table = """
    CREATE TABLE IF NOT EXISTS public.users (
        id SERIAL PRIMARY KEY,
        phone_number VARCHAR(20) UNIQUE NOT NULL,
        first_name VARCHAR(100),
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """

    # conversations (جدید: پشتیبانی از کاربر مهمان و کاربر لاگین شده)
    conversations_table = """
    -- گام ۱: جدول را با ستون‌های اصلی (که احتمالاً از قبل وجود دارند) ایجاد کن
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
        report_generated TIMESTAMP
    );
    
    -- [اصلاحیه] گام ۲: ستون‌های جدید را با ALTER TABLE اضافه کن تا اسکریپت روی دیتابیس قدیمی هم اجرا شود
    ALTER TABLE public.conversations 
        ADD COLUMN IF NOT EXISTS anonymous_user_id VARCHAR(100) UNIQUE,
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

    -- گام ۳: حالا که مطمئنیم ستون‌ها وجود دارند، ایندکس‌ها را بساز
    CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON public.conversations(user_id);
    CREATE INDEX IF NOT EXISTS idx_conversations_anonymous_user_id ON public.conversations(anonymous_user_id);

    -- گام ۴: افزودن Constraint (محدودیت) اگر وجود نداشته باشد
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'chk_user_or_anonymous' AND conrelid = 'public.conversations'::regclass
        ) THEN
            ALTER TABLE public.conversations 
            ADD CONSTRAINT chk_user_or_anonymous CHECK (
                (user_id IS NOT NULL AND anonymous_user_id IS NULL) OR
                (user_id IS NULL AND anonymous_user_id IS NOT NULL)
            );
        END IF;
    END $$;
    """
    
    # otps (جدید: برای کدهای یکبار مصرف)
    otps_table = """
    CREATE TABLE IF NOT EXISTS public.otps (
        id SERIAL PRIMARY KEY,
        phone_number VARCHAR(20) NOT NULL,
        code VARCHAR(10) NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        expires_at TIMESTAMP NOT NULL
    );
    -- ایجاد ایندکس برای جستجوی سریع کدها
    CREATE INDEX IF NOT EXISTS idx_otps_phone_code ON public.otps(phone_number, code);
    """

    # prompts (بدون تغییر)
    prompts_table = """
    CREATE TABLE IF NOT EXISTS public.prompts (
        prompt_key TEXT PRIMARY KEY,
        prompt_value TEXT NOT NULL,
        last_updated TIMESTAMPTZ DEFAULT NOW()
    );
    """

    # settings (بدون تغییر)
    settings_table = """
    CREATE TABLE IF NOT EXISTS public.settings (
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT NOT NULL,
        last_updated TIMESTAMPTZ DEFAULT NOW()
    );
    """

    # shared_chats (بدون تغییر)
    shared_chats_table = """
    CREATE TABLE IF NOT EXISTS public.shared_chats (
        id SERIAL PRIMARY KEY,
        share_id VARCHAR(50) UNIQUE NOT NULL,
        original_user_id VARCHAR(100) NOT NULL,
        conversation_data JSONB NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '30 days'),
        view_count INTEGER DEFAULT 0,
        last_viewed_at TIMESTAMP,
        career_profile JSONB -- ستون از قبل اضافه شده بود, اینجا فقط برای اطمینان
    );
    """

    # --- [جدید] جدول اعتبار کاربران ---
    user_credits_table = """
    CREATE TABLE IF NOT EXISTS public.user_credits (
        id SERIAL PRIMARY KEY,
        -- اتصال یک به یک به کاربر
        user_id INTEGER UNIQUE NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
        -- تعداد پیام‌های رایگان باقیمانده
        message_credits INTEGER NOT NULL DEFAULT 4,
        -- تاریخ انقضای اشتراک (برای چت نامحدود)
        subscription_expires_at TIMESTAMP
        -- ستون جدید در دستور ALTER TABLE اضافه می‌شود
    );

    -- [اصلاح شد] این دستور ستون جدید را به جدول موجود اضافه می‌کند 
    -- (و اگر از قبل وجود داشته باشد، خطا نمی‌دهد)
    ALTER TABLE public.user_credits ADD COLUMN IF NOT EXISTS discount_timer_started_at TIMESTAMPTZ;

    -- ایندکس برای جستجوی سریع اعتبار کاربر
    CREATE INDEX IF NOT EXISTS idx_user_credits_user_id ON public.user_credits(user_id);
    """

    # --- [جدید] جدول کدهای معرف ---
    referrals_table = """
    CREATE TABLE IF NOT EXISTS public.referrals (
        id SERIAL PRIMARY KEY,
        -- کاربری که لینک را ساخته
        referrer_user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
        -- کد منحصر به فرد معرف
        referral_code VARCHAR(100) UNIQUE NOT NULL,
        -- کاربری که با لینک ثبت نام کرده
        referred_user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        -- زمانی که اعتبار به صاحب کد داده شد
        credited_at TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_referrals_referrer_id ON public.referrals(referrer_user_id);
    CREATE INDEX IF NOT EXISTS idx_referrals_code ON public.referrals(referral_code);
    """

    # --- [جدید] جدول سوابق پرداخت ---
    payments_table = """
    CREATE TABLE IF NOT EXISTS public.payments (
        id SERIAL PRIMARY KEY,
        -- کاربری که پرداخت را انجام داده
        user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
        -- مبلغ (به ریال یا تومان، بر اساس درگاه)
        amount INTEGER NOT NULL,
        -- کد رهگیری از زرین پال
        authority VARCHAR(100) NOT NULL,
        -- وضعیت تراکنش
        status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
        created_at TIMESTAMP DEFAULT NOW(),
        -- زمانی که پرداخت با موفقیت تایید شد
        verified_at TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_payments_user_id ON public.payments(user_id);
    CREATE INDEX IF NOT EXISTS idx_payments_authority ON public.payments(authority);
    """

    stmts = [
        ("users", users_table),
        ("conversations", conversations_table),
        ("otps", otps_table),
        ("prompts", prompts_table),
        ("settings", settings_table),
        ("shared_chats", shared_chats_table),
        # --- [جدید] افزودن جداول جدید به لیست اجرا ---
        ("user_credits", user_credits_table),
        ("referrals", referrals_table),
        ("payments", payments_table),
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
# 4) Seed minimal data
# ------------------------------------------------------------------------------
def insert_initial_data():
    initial_settings = [
        ("GEMINI_API_KEY", DEFAULT_GEMINI_API_KEY),
        ("SELECTED_LLM_MODEL", DEFAULT_MODEL),
        ("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD),
        ("JWT_SECRET_KEY", DEFAULT_JWT_SECRET),
        ("KAVEHNEGAR_API_KEY", os.getenv("KAVEHNEGAR_API_KEY", "YOUR_API_KEY")),
        ("MAX_CONVERSATION_LENGTH", os.getenv("MAX_CONVERSATION_LENGTH", "100")),
        ("SESSION_TIMEOUT", os.getenv("SESSION_TIMEOUT", "3600")),
        # --- [جدید] تنظیمات مربوط به پرداخت (می‌توانید بعداً از پنل ادمین تغییر دهید) ---
        ("ZARINPAL_MERCHANT_ID", os.getenv("ZARINPAL_MERCHANT_ID", "YOUR_MERCHANT_ID")),
        ("SUBSCRIPTION_PRICE", os.getenv("SUBSCRIPTION_PRICE", "100000")), # قیمت اصلی (۱۰۰ هزار تومان)
        ("DISCOUNT_PRICE", os.getenv("DISCOUNT_PRICE", "49000")), # قیمت تخفیف (۴۹ هزار تومان)
    ]

    initial_prompts = [
        ("COUNSELOR_MANIFESTO", "شما یک مشاور شغلی حرفه‌ای هستید که به کاربران کمک می‌کنید تا مسیر شغلی مناسب خود را پیدا کنند."),
        ("PERSONALITY_PARAGRAPH_PROMPT", "بر اساس پروفایل شغلی زیر، یک پاراگراف شخصیت‌شناسی بنویسید."),
        ("SYSTEM_ERROR_MESSAGE", "متاسفانه خطایی در سیستم رخ داده است. لطفاً دوباره تلاش کنید."),
        ("UNEXPECTED_ERROR_MESSAGE", "خطای غیرمنتظره‌ای رخ داده است."),
        ("ANALYSIS_START_MESSAGE", "تحلیل اطلاعات شما شروع شد. لطفاً صبر کنید..."),
        # (پرامپت‌های دیگر شما در راه‌اندازی بعدی app.py اضافه خواهند شد)
    ]

    try:
        engine = _engine(PROJECT_DSN)
        with engine.connect() as conn:
            # settings (upsert on key)
            for key, val in initial_settings:
                if val is None:
                    log.warning(f"⚠️ Skipping setting {key} as it is None")
                    continue
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
        return True
    except Exception as e:
        log.error(f"❌ insert_initial_data: {e}")
        return False


# ------------------------------------------------------------------------------
# 5) Verify (اصلاح شده)
# ------------------------------------------------------------------------------
def verify_setup():
    try:
        engine = _engine(PROJECT_DSN)
        with engine.connect() as conn:
            # --- [جدید] افزودن جداول جدید به لیست بررسی ---
            tables_to_check = [
                "users", "conversations", "prompts", "settings", 
                "shared_chats", "otps", "user_credits", "referrals", "payments"
            ]
            
            for tbl in tables_to_check:
                try:
                    cnt = conn.execute(text(f"SELECT COUNT(*) FROM public.{tbl}")).scalar()
                    log.info(f"✅ {tbl}: {cnt} rows")
                except Exception as e:
                    log.error(f"❌ verify table {tbl}: {e}")
                    return False

            exts = conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp');")
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
    log.info("🚀 DB bootstrap started (v3 Schema with Credits)")
    
    # اخطار مهم قبل از شروع
    log.warning("="*60)
    log.warning("!!! هشدار !!!")
    log.warning("این اسکریپت جداول اعتباردهی (Credits, Referrals, Payments) را اضافه می‌کند.")
    log.warning(f"دیتابیس هدف: {DB_NAME} روی {DB_HOST}")
    log.warning("اگر دیتابیس فعلی شما حاوی اطلاعات است، اکیداً توصیه می‌شود ابتدا یک نسخه پشتیبان تهیه کنید.")
    log.warning("="*60)
    
    # در محیط production, این بخش را برای تأیید دستی فعال کنید
    # if os.getenv("FLASK_ENV") != "development":
    #     try:
    #         response = input("آیا ادامه می‌دهید؟ (yes/no): ")
    #         if response.lower() != 'yes':
    #             log.info("عملیات لغو شد.")
    #             return False
    #     except EOFError:
    #         log.error("ورودی نامعتبر. عملیات لغو شد.")
    #         return False
            
    if not create_database_if_not_exists():
        return False
    if not create_extensions():
        return False
    if not create_tables():
        return False
    if not insert_initial_data():
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