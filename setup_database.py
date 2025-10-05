#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Job Assistant - راه‌اندازی اولیه دیتابیس
=========================================

این فایل برای ایجاد و راه‌اندازی اولیه دیتابیس PostgreSQL استفاده می‌شود.
تمام جدول‌ها، extensions و داده‌های اولیه را ایجاد می‌کند.

استفاده:
    python setup_database.py

نکات:
    - اطمینان حاصل کنید که PostgreSQL نصب و در حال اجرا است
    - کاربر باید دسترسی CREATE DATABASE داشته باشد
    - pgvector extension باید نصب باشد
"""

import os
import sys
import logging
import csv
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine, text
import json

# تنظیمات لاگ‌گیری
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# تنظیمات دیتابیس
DB_USER = "oosmajid"
DB_PASS = ""
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "hezardjab_local"

# تنظیمات پیش‌فرض
DEFAULT_GEMINI_API_KEY = "AIzaSyCxYoe12F2AZjL5PhE-vDSSQtpnFP7rIeg"
DEFAULT_MODEL = "models/gemini-flash-latest"

# Connection string برای اتصال به دیتابیس پروژه
PROJECT_DB_CONNECTION_STRING = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def create_database_if_not_exists():
    """ایجاد دیتابیس اگر وجود نداشته باشد"""
    try:
        # اتصال به PostgreSQL بدون دیتابیس مشخص
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database="postgres"  # اتصال به دیتابیس پیش‌فرض
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # بررسی وجود دیتابیس
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'")
        exists = cursor.fetchone()
        
        if not exists:
            logger.info(f"ایجاد دیتابیس '{DB_NAME}'...")
            cursor.execute(f"CREATE DATABASE {DB_NAME}")
            logger.info(f"✅ دیتابیس '{DB_NAME}' با موفقیت ایجاد شد")
        else:
            logger.info(f"✅ دیتابیس '{DB_NAME}' از قبل موجود است")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ خطا در ایجاد دیتابیس: {e}")
        return False

def create_extensions():
    """ایجاد extensions مورد نیاز"""
    extensions = [
        "CREATE EXTENSION IF NOT EXISTS vector;",  # pgvector برای embeddings
        "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";",  # برای UUID functions
    ]
    
    try:
        engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        
        with engine.connect() as conn:
            for ext_sql in extensions:
                try:
                    conn.execute(text(ext_sql))
                    logger.info(f"✅ Extension ایجاد شد: {ext_sql.split()[4]}")
                except Exception as e:
                    logger.warning(f"⚠️ خطا در ایجاد extension: {e}")
            conn.commit()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ خطا در ایجاد extensions: {e}")
        return False

def create_tables():
    """ایجاد تمام جدول‌های مورد نیاز"""
    
    # Schema برای جدول users
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
    
    # Schema برای جدول conversations
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
        user_embedding vector(768),  -- برای sentence-transformers
        final_report_text TEXT,
        report_generated TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    # Schema برای جدول prompts
    prompts_table = """
    CREATE TABLE IF NOT EXISTS public.prompts (
        id SERIAL PRIMARY KEY,
        prompt_key VARCHAR(100) UNIQUE NOT NULL,
        prompt_value TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    # Schema برای جدول settings
    settings_table = """
    CREATE TABLE IF NOT EXISTS public.settings (
        id SERIAL PRIMARY KEY,
        setting_key VARCHAR(100) UNIQUE NOT NULL,
        setting_value TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    # Schema برای جدول shared_chats
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
    
    # Schema برای جدول jobs (برای matching)
    jobs_table = """
    CREATE TABLE IF NOT EXISTS public.jobs (
        id INTEGER PRIMARY KEY,
        onet_code VARCHAR(20),
        title TEXT NOT NULL,
        description TEXT,
        onet_profile JSONB,
        embedding vector(768),  -- برای similarity search
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    
    -- ایجاد index برای similarity search
    CREATE INDEX IF NOT EXISTS jobs_embedding_idx ON public.jobs 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
    
    -- ایجاد index برای job_zone
    CREATE INDEX IF NOT EXISTS jobs_job_zone_idx ON public.jobs (job_zone);
    """
    
    tables = [
        ("users", users_table),
        ("conversations", conversations_table),
        ("prompts", prompts_table),
        ("settings", settings_table),
        ("shared_chats", shared_chats_table),
        ("jobs", jobs_table),
    ]
    
    try:
        engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        
        with engine.connect() as conn:
            for table_name, table_sql in tables:
                try:
                    conn.execute(text(table_sql))
                    logger.info(f"✅ جدول '{table_name}' ایجاد/بررسی شد")
                except Exception as e:
                    logger.error(f"❌ خطا در ایجاد جدول '{table_name}': {e}")
            conn.commit()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ خطا در ایجاد جدول‌ها: {e}")
        return False

def insert_initial_data():
    """درج داده‌های اولیه"""
    
    # تنظیمات اولیه
    initial_settings = [
        ("GEMINI_API_KEY", DEFAULT_GEMINI_API_KEY, "کلید API برای Gemini"),
        ("SELECTED_LLM_MODEL", DEFAULT_MODEL, "مدل LLM انتخاب شده"),
        ("ADMIN_PASSWORD", "admin123", "رمز عبور پنل مدیریت"),
        ("MAX_CONVERSATION_LENGTH", "100", "حداکثر طول مکالمه"),
        ("SESSION_TIMEOUT", "3600", "مدت انقضای session (ثانیه)"),
    ]
    
    # پرامپت‌های اولیه (نمونه)
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
    
    # نمونه مشاغل
    sample_jobs = [
        ("مهندس نرم‌افزار", "توسعه و طراحی نرم‌افزارهای کامپیوتری", 4),
        ("طراح گرافیک", "طراحی بصری و گرافیکی برای پروژه‌های مختلف", 3),
        ("مدیر پروژه", "مدیریت و هماهنگی پروژه‌های سازمانی", 5),
        ("تحلیلگر داده", "تحلیل و پردازش داده‌های سازمانی", 4),
        ("مشاور مالی", "ارائه مشاوره‌های مالی و سرمایه‌گذاری", 4),
        ("معلم", "آموزش و تدریس در مدارس و دانشگاه‌ها", 3),
        ("پزشک", "درمان و مراقبت از بیماران", 5),
        ("وکیل", "ارائه خدمات حقوقی و مشاوره قضایی", 4),
        ("مهندس مکانیک", "طراحی و ساخت سیستم‌های مکانیکی", 4),
        ("بازاریاب دیجیتال", "مدیریت و اجرای کمپین‌های بازاریابی آنلاین", 3),
    ]
    
    try:
        engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        
        with engine.connect() as conn:
            # درج تنظیمات
            for key, value, description in initial_settings:
                try:
                    conn.execute(text("""
                        INSERT INTO public.settings (setting_key, setting_value) 
                        VALUES (:key, :value)
                        ON CONFLICT (setting_key) DO NOTHING
                    """), {"key": key, "value": value})
                    logger.info(f"✅ تنظیم '{key}' اضافه شد")
                except Exception as e:
                    logger.warning(f"⚠️ خطا در اضافه کردن تنظیم '{key}': {e}")
            
            # درج پرامپت‌ها
            for key, value in initial_prompts:
                try:
                    conn.execute(text("""
                        INSERT INTO public.prompts (prompt_key, prompt_value) 
                        VALUES (:key, :value)
                        ON CONFLICT (prompt_key) DO NOTHING
                    """), {"key": key, "value": value})
                    logger.info(f"✅ پرامپت '{key}' اضافه شد")
                except Exception as e:
                    logger.warning(f"⚠️ خطا در اضافه کردن پرامپت '{key}': {e}")
            
            # درج مشاغل نمونه
            for title, description, job_zone in sample_jobs:
                try:
                    conn.execute(text("""
                        INSERT INTO public.jobs (title, description, job_zone) 
                        VALUES (:title, :desc, :zone)
                        ON CONFLICT DO NOTHING
                    """), {"title": title, "desc": description, "zone": job_zone})
                    logger.info(f"✅ شغل '{title}' اضافه شد")
                except Exception as e:
                    logger.warning(f"⚠️ خطا در اضافه کردن شغل '{title}': {e}")
            
            conn.commit()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ خطا در درج داده‌های اولیه: {e}")
        return False

def verify_setup():
    """بررسی صحت راه‌اندازی"""
    try:
        engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        
        with engine.connect() as conn:
            # بررسی جدول‌ها
            tables = ['users', 'conversations', 'prompts', 'settings', 'shared_chats', 'jobs']
            for table in tables:
                result = conn.execute(text(f"SELECT COUNT(*) FROM public.{table}"))
                count = result.scalar()
                logger.info(f"✅ جدول '{table}': {count} رکورد")
            
            # بررسی extensions
            result = conn.execute(text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'uuid-ossp')"))
            extensions = [row[0] for row in result.fetchall()]
            logger.info(f"✅ Extensions نصب شده: {extensions}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ خطا در بررسی راه‌اندازی: {e}")
        return False

def main():
    """تابع اصلی"""
    logger.info("🚀 شروع راه‌اندازی دیتابیس Job Assistant...")
    logger.info("=" * 50)
    
    # مرحله 1: ایجاد دیتابیس
    logger.info("📋 مرحله 1: بررسی و ایجاد دیتابیس...")
    if not create_database_if_not_exists():
        logger.error("❌ راه‌اندازی متوقف شد - خطا در ایجاد دیتابیس")
        return False
    
    # مرحله 2: ایجاد extensions
    logger.info("📋 مرحله 2: نصب extensions...")
    if not create_extensions():
        logger.error("❌ راه‌اندازی متوقف شد - خطا در نصب extensions")
        return False
    
    # مرحله 3: ایجاد جدول‌ها
    logger.info("📋 مرحله 3: ایجاد جدول‌ها...")
    if not create_tables():
        logger.error("❌ راه‌اندازی متوقف شد - خطا در ایجاد جدول‌ها")
        return False
    
    # مرحله 4: درج داده‌های اولیه
    logger.info("📋 مرحله 4: درج داده‌های اولیه...")
    if not insert_initial_data():
        logger.error("❌ راه‌اندازی متوقف شد - خطا در درج داده‌های اولیه")
        return False
    
    # مرحله 5: وارد کردن داده‌های jobs از CSV
    logger.info("📋 مرحله 5: وارد کردن داده‌های jobs از CSV...")
    try:
        import_jobs_from_csv()
        logger.info("✅ وارد کردن داده‌های jobs تکمیل شد")
    except Exception as e:
        logger.error(f"❌ خطا در وارد کردن داده‌های jobs: {e}")
        return False
    
    # مرحله 6: بررسی نهایی
    logger.info("📋 مرحله 6: بررسی نهایی...")
    if not verify_setup():
        logger.error("❌ راه‌اندازی متوقف شد - خطا در بررسی نهایی")
        return False
    
    logger.info("=" * 50)
    logger.info("🎉 راه‌اندازی دیتابیس با موفقیت تکمیل شد!")
    logger.info(f"✅ دیتابیس: {DB_NAME}")
    logger.info(f"✅ میزبان: {DB_HOST}:{DB_PORT}")
    logger.info(f"✅ کاربر: {DB_USER}")
    logger.info("")
    logger.info("📝 نکات مهم:")
    logger.info("1. کلید API Gemini را در پنل مدیریت تنظیم کنید")
    logger.info("2. رمز عبور پیش‌فرض پنل مدیریت: admin123")
    logger.info("3. برنامه آماده اجرا است!")
    
    return True

def import_jobs_from_csv():
    """داده‌های jobs را از فایل CSV وارد دیتابیس می‌کند."""
    csv_file_path = "jobs_rows.csv"
    
    if not os.path.exists(csv_file_path):
        logger.warning(f"فایل {csv_file_path} یافت نشد. وارد کردن داده‌ها رد شد.")
        return
    
    engine = create_engine(PROJECT_DB_CONNECTION_STRING)
    
    try:
        with engine.connect() as conn:
            # بررسی اینکه آیا داده‌ها قبلاً وارد شده‌اند
            result = conn.execute(text("SELECT COUNT(*) FROM public.jobs")).scalar()
            if result > 0:
                logger.info(f"جدول jobs قبلاً دارای {result} رکورد است. وارد کردن داده‌ها رد شد.")
                return
            
            logger.info(f"شروع وارد کردن داده‌ها از فایل {csv_file_path}...")
            
            with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                batch_size = 100
                batch_data = []
                
                for row_num, row in enumerate(reader, 1):
                    try:
                        # تبدیل embedding string به لیست
                        embedding_str = row['embedding']
                        embedding_list = json.loads(embedding_str)
                        
                        # تبدیل onet_profile string به JSON
                        onet_profile_str = row['onet_profile']
                        onet_profile_json = json.loads(onet_profile_str)
                        
                        batch_data.append({
                            'id': int(row['id']),
                            'onet_code': row['onet_code'],
                            'title': row['title'],
                            'description': row['description'],
                            'onet_profile': onet_profile_json,
                            'embedding': embedding_list
                        })
                        
                        # وارد کردن batch به دیتابیس
                        if len(batch_data) >= batch_size:
                            _insert_jobs_batch(conn, batch_data)
                            batch_data = []
                            logger.info(f"وارد شده: {row_num} رکورد...")
                    
                    except (ValueError, KeyError) as e:
                        logger.error(f"خطا در ردیف {row_num}: {e}")
                        continue
                
                # وارد کردن آخرین batch
                if batch_data:
                    _insert_jobs_batch(conn, batch_data)
                
                conn.commit()
                logger.info(f"وارد کردن داده‌ها با موفقیت تکمیل شد. تعداد کل رکوردها: {row_num}")
                
    except Exception as e:
        logger.error(f"خطا در وارد کردن داده‌های CSV: {e}")
        raise

def _insert_jobs_batch(conn, batch_data):
    """یک batch از داده‌های jobs را وارد دیتابیس می‌کند."""
    insert_sql = text("""
        INSERT INTO public.jobs (id, onet_code, title, description, onet_profile, embedding)
        VALUES (:id, :onet_code, :title, :description, :onet_profile, :embedding)
        ON CONFLICT (id) DO UPDATE SET
            onet_code = EXCLUDED.onet_code,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            onet_profile = EXCLUDED.onet_profile,
            embedding = EXCLUDED.embedding,
            updated_at = NOW()
    """)
    
    conn.execute(insert_sql, batch_data)

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ راه‌اندازی توسط کاربر متوقف شد")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ خطای غیرمنتظره: {e}")
        sys.exit(1)
