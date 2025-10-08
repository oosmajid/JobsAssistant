# -*- coding: utf-8 -*-
# ==============================================================================
# 0) Environment Variables & Configuration
# ==============================================================================
import os
# بارگذاری متغیرهای محیطی از فایل .env
from dotenv import load_dotenv
load_dotenv()

# متغیرهای مهم از محیط
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROJECT_REF    = os.getenv("PROJECT_REF")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")  # پسورد پیش‌فرض ادمین
IS_METIS = True

# ==============================================================================
# 2) Imports and Basic Setup
# ==============================================================================
import logging
import asyncio
import json
import sys
import re
import uuid
import hashlib
import secrets
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, render_template_string
from flask_cors import CORS
from sqlalchemy import create_engine, text
import google.generativeai as genai
from google.api_core.client_options import ClientOptions
# from sentence_transformers import SentenceTransformer

# فایل prompts.py فقط برای اولین راه‌اندازی (seeding) استفاده می‌شود
import prompts as prompts_file

# EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-small")
# EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "paraphrase-multilingual-mpnet-base-v2")
# EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
# تنظیمات لاگ‌گیری
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


# ==============================================================================
# 3) AI & Database Configuration
# ==============================================================================

def configure_genai(api_key: str):
    if IS_METIS:
        genai.configure(api_key=api_key, transport='rest',
                        client_options=ClientOptions(api_endpoint="https://api.metisai.ir"))
    else:
        genai.configure(api_key=api_key)
    

# ==============================================================================
# 4) Database Configuration
# ==============================================================================
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_CONNECTION_STRING = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# مدل‌های موجود از متغیرهای محیطی
AVAILABLE_MODELS_STR = os.getenv("AVAILABLE_MODELS", "models/gemini-flash-latest,models/gemini-pro-latest,models/gemini-2.0-flash,models/gemini-2.0-flash-001")
AVAILABLE_MODELS = [model.strip() for model in AVAILABLE_MODELS_STR.split(",")]
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "models/gemini-flash-latest")

# دیکشنری گلوبال برای نگهداری پرامپت‌ها
PROMPTS = {}

# ==============================================================================
# Admin Authentication Functions
# ==============================================================================
def is_admin_authenticated():
    """بررسی می‌کند که آیا کاربر ادمین وارد شده است یا خیر."""
    return session.get('admin_authenticated', False)

def require_admin_auth(f):
    """دکوراتور برای محافظت از route های ادمین."""
    def decorated_function(*args, **kwargs):
        if not is_admin_authenticated():
            # برای صفحه HTML، redirect به صفحه لاگین
            if request.endpoint in ['serve_admin', 'serve_stats']:
                return render_template_string(ADMIN_LOGIN_TEMPLATE), 401
            # برای API ها، JSON error برگردانیم
            else:
                return jsonify({'error': 'Authentication required', 'login_required': True}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def get_admin_password():
    """دریافت پسورد ادمین از دیتابیس یا متغیر محیطی."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT setting_value FROM public.settings WHERE setting_key = 'ADMIN_PASSWORD'")).fetchone()
            if result:
                return result[0]
    except:
        pass
    return ADMIN_PASSWORD

# Template ورود ادمین
ADMIN_LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ورود ادمین - مشاور شغلی</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/gh/rastikerdar/vazir-font@v30.1.0/dist/font-face.css" rel="stylesheet">
    <style>
        body { 
            font-family: 'Vazirmatn', Vazirmatn, Tahoma, Arial, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-card {
            background: white;
            border-radius: 15px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
            padding: 2rem;
            width: 100%;
            max-width: 400px;
        }
        .login-title {
            text-align: center;
            margin-bottom: 2rem;
            color: #333;
            font-weight: 600;
        }
        .form-control {
            border-radius: 10px;
            border: 2px solid #e9ecef;
            padding: 12px 15px;
            font-size: 16px;
        }
        .form-control:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25);
        }
        .btn-login {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 10px;
            padding: 12px;
            font-size: 16px;
            font-weight: 600;
            width: 100%;
            color: white;
        }
        .btn-login:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        .alert {
            border-radius: 10px;
            border: none;
        }
        .back-link {
            text-align: center;
            margin-top: 1rem;
        }
        .back-link a {
            color: #667eea;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="login-card">
        <h2 class="login-title">🔐 ورود ادمین</h2>
        <div id="error-alert" class="alert alert-danger" style="display: none;"></div>
        
        <form id="loginForm">
            <div class="mb-3">
                <label for="password" class="form-label">رمز عبور ادمین:</label>
                <input type="password" class="form-control" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-login">ورود به پنل ادمین</button>
        </form>
        
        <div class="back-link">
            <a href="/">← بازگشت به صفحه اصلی</a>
        </div>
    </div>

    <script>
        document.getElementById('loginForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const password = document.getElementById('password').value;
            const errorAlert = document.getElementById('error-alert');
            
            try {
                const response = await fetch('/admin/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ password: password })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    window.location.href = '/admin';
                } else {
                    errorAlert.textContent = data.error || 'خطا در ورود';
                    errorAlert.style.display = 'block';
                }
            } catch (error) {
                errorAlert.textContent = 'خطا در ارتباط با سرور';
                errorAlert.style.display = 'block';
            }
        });
    </script>
</body>
</html>
'''

def validate_model_access(api_key: str, model_name: str) -> bool:
    """بررسی می‌کند که آیا به مدل مشخص شده دسترسی وجود دارد یا خیر."""
    try:
        logger.info(f"Validating access to model: {model_name}...")
        configure_genai(api_key)
        model = genai.GenerativeModel(model_name)
        _ = model.generate_content("ping", request_options={'timeout': 10}) # 10 ثانیه مهلت
        logger.info(f"Successfully validated access to {model_name}.")
        return True
    except Exception as e:
        error_msg = str(e)
        # بررسی خطای کوتای
        if "429" in error_msg or "quota" in error_msg.lower() or "exceeded" in error_msg.lower():
            logger.warning(f"API quota exceeded for {model_name}. This is normal for free tier users.")
            logger.warning("Application will continue with limited functionality. Consider upgrading your API plan.")
            # برای خطای کوتای، True برمی‌گردانیم تا اپلیکیشن ادامه دهد
            return True
        else:
            logger.error(f"Validation failed for {model_name}: {e}", exc_info=True)
            return False

def is_text_generation_model(model_name: str) -> bool:
    """بررسی اینکه آیا مدل برای تولید متن مناسب است یا نه"""
    model_lower = model_name.lower()
    
    # حذف مدل‌های image-generation، vision و TTS
    excluded_keywords = [
        'image', 'vision', 'imagen', 'dall-e', 'stable-diffusion',  # image generation
        'tts', 'text-to-speech', 'speech', 'audio', 'voice', 'sound'  # TTS models
    ]
    if any(keyword in model_lower for keyword in excluded_keywords):
        return False
    
    # فقط مدل‌های Gemini برای تولید متن
    if 'gemini' not in model_lower:
        return False
    
    return True

def fetch_available_models_from_api(api_key: str) -> list[str]:
    """دریافت لیست مدل‌های در دسترس از API Gemini"""
    try:
        logger.info("Fetching available models from Gemini API...")
        configure_genai(api_key)
        
        # دریافت لیست تمام مدل‌ها
        models = list(genai.list_models())
        
        # فیلتر کردن مدل‌های مناسب (فقط generateContent و بدون image-generation)
        suitable_models = []
        logger.info(f"Total models found from API: {len(models)}")
        
        for model in models:
            # بررسی اینکه مدل قابلیت generate_content دارد
            if 'generateContent' in model.supported_generation_methods:
                model_name = model.name
                
                # استفاده از تابع کمکی برای فیلتر کردن
                if is_text_generation_model(model_name):
                    suitable_models.append(model_name)
                    logger.debug(f"Added model: {model_name}")
                else:
                    logger.debug(f"Filtered out model: {model_name}")
        
        logger.info(f"Text generation models after filtering: {len(suitable_models)}")
        
        # مرتب‌سازی بر اساس اولویت (مدل‌های جدیدتر و latest اولویت بالاتری دارند)
        priority_order = {
            'gemini-2.0-flash': 1,
            'gemini-2.0-flash-001': 2,
            'gemini-exp-1206': 3,  # مدل آزمایشی جدید
            'gemini-flash-latest': 4,
            'gemini-pro-latest': 5,
            'gemini-1.5-flash-latest': 6,  # مدل latest جدید
            'gemini-1.5-pro-latest': 7,    # مدل latest جدید
            'gemini-1.5-pro-002': 8,
            'gemini-1.5-flash-8b': 9,
            'gemini-1.5-pro': 10,
            'gemini-1.5-flash': 11,
            'gemini-1.0-pro': 12
        }
        
        def get_priority(model_name):
            model_lower = model_name.lower()
            
            # کلید اصلی مرتب‌سازی: آیا مدل 'latest' است یا نه؟
            # به مدل‌های latest گروه 0 و به بقیه گروه 1 می‌دهیم.
            is_latest_group = 0 if 'latest' in model_lower else 1
            
            # کلید دوم مرتب‌سازی: استفاده از دیکشنری اولویت‌بندی
            specific_priority = 999  # اولویت پیش‌فرض برای مدل‌های ناشناس
            for key, p_val in priority_order.items():
                if key in model_lower:
                    specific_priority = p_val
                    break # پس از پیدا کردن اولین تطابق، حلقه متوقف می‌شود
            
            # خروجی یک تاپل است. پایتون ابتدا بر اساس عضو اول (گروه) مرتب می‌کند
            # و سپس در صورت تساوی، بر اساس عضو دوم (اولویت) مرتب می‌کند.
            return (is_latest_group, specific_priority)
        
        suitable_models.sort(key=get_priority)
        
        # فقط 10 مدل اول را برگردانیم
        top_models = suitable_models[:100]
        
        logger.info(f"Successfully fetched {len(top_models)} models: {top_models}")
        return top_models
        
    except Exception as e:
        logger.error(f"Failed to fetch models from API: {e}")
        # در صورت خطا، مدل‌های پیش‌فرض را برگردانیم
        return [
            "models/gemini-2.0-flash",
            "models/gemini-2.0-flash-001", 
            "models/gemini-flash-latest",
            "models/gemini-pro-latest",
            "models/gemini-1.5-flash-latest",
            "models/gemini-1.5-pro-latest",
            "models/gemini-1.5-pro-002",
            "models/gemini-1.5-flash-8b",
            "models/gemini-exp-1206",
            "models/gemini-1.5-pro"
        ]

def try_fallback_models(api_key: str, primary_model: str) -> str:
    """سعی می‌کند مدل‌های جایگزین را پیدا کند اگر مدل اصلی کار نکند."""
    # استفاده از مدل‌های پویا به جای لیست ثابت
    fallback_models = fetch_available_models_from_api(api_key)
    
    # حذف مدل اصلی از لیست fallback
    if primary_model in fallback_models:
        fallback_models.remove(primary_model)
    
    for fallback_model in fallback_models:
        try:
            logger.info(f"Trying fallback model: {fallback_model}")
            if validate_model_access(api_key, fallback_model):
                logger.info(f"Successfully found working fallback model: {fallback_model}")
                return fallback_model
        except Exception as e:
            logger.warning(f"Fallback model {fallback_model} also failed: {e}")
            continue
    
    logger.error("All fallback models failed. Returning primary model anyway.")
    return primary_model

def embed_with_gemini(text: str) -> list[float]:
    """
    برمی‌گرداند: لیست float (بردار امبدینگ) از سرویس Gemini
    مدل: text-embedding-004
    """
    configure_genai(GEMINI_API_KEY)
    resp = genai.embed_content(
        model="models/text-embedding-004",  # یا "text-embedding-004" در برخی ریلیزها
        content=text
    )
    # سازگار با دو فرمت رایج خروجی کتابخانه:
    # 1) dict با resp["embedding"] یا resp["embedding"]["values"]
    # 2) آبجکت با .embedding یا .values
    emb = None
    if isinstance(resp, dict):
        emb = resp.get("embedding", resp.get("data"))  # بعضی ورژن‌ها
    else:
        emb = getattr(resp, "embedding", None) or getattr(resp, "data", None)

    if isinstance(emb, dict):
        values = emb.get("values") or emb.get("embedding")
    elif hasattr(emb, "values"):
        values = emb.values
    else:
        values = emb

    if not values or not isinstance(values, (list, tuple)):
        raise RuntimeError(f"Embedding response malformed: {type(resp)} -> {resp}")
    return [float(x) for x in values]

def _sync_get_or_create_setting(conn, key: str, default_value: str) -> str:
    """یک تنظیم را از دیتابیس می‌خواند یا اگر وجود نداشت، با مقدار پیش‌فرض آن را ایجاد می‌کند."""
    value = conn.execute(
        text("SELECT setting_value FROM public.settings WHERE setting_key = :key"),
        {"key": key}
    ).scalar_one_or_none()
    
    if value is None:
        logger.warning(f"Setting '{key}' not found. Creating it with default value '{default_value}'.")
        conn.execute(
            text("INSERT INTO public.settings (setting_key, setting_value) VALUES (:key, :value)"),
            {"key": key, "value": default_value}
        )
        # conn.commit() را از اینجا حذف کنید چون تراکنش توسط with engine.connect() مدیریت می‌شود
        return default_value
    return value


# --- راه‌اندازی اولیه سرویس‌ها ---
try:
    engine = create_engine(DB_CONNECTION_STRING, pool_pre_ping=True)
    logger.info("Database engine created successfully.")
    
    SELECTED_MODEL_NAME = "" # متغیر گلوبال برای نگهداری نام مدل

    with engine.connect() as conn:
        # --- ایجاد جدول shared_chats اگر وجود نداشته باشد ---
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.shared_chats (
                id SERIAL PRIMARY KEY,
                share_id VARCHAR(50) UNIQUE NOT NULL,
                original_user_id VARCHAR(100) NOT NULL,
                conversation_data JSONB NOT NULL,
                career_profile JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '30 days'),
                view_count INTEGER DEFAULT 0,
                last_viewed_at TIMESTAMP
            )
        """))
        
        # --- اضافه کردن فیلد career_profile اگر وجود نداشته باشد ---
        conn.execute(text("""
            ALTER TABLE public.shared_chats 
            ADD COLUMN IF NOT EXISTS career_profile JSONB
        """))
        
        # --- اضافه کردن ستون‌های created_at و updated_at به جدول conversations اگر وجود نداشته باشند ---
        conn.execute(text("""
            ALTER TABLE public.conversations 
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()
        """))
        
        conn.execute(text("""
            ALTER TABLE public.conversations 
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()
        """))
        
        conn.commit()
        logger.info("Shared chats table created/verified successfully.")
        
        # --- بارگذاری یا seeding پرامپت‌ها ---
        # (این بخش بدون تغییر باقی می‌ماند)
        if not conn.execute(text("SELECT 1 FROM public.prompts LIMIT 1")).scalar_one_or_none():
            logger.warning("Prompts table is empty. Seeding from prompts.py file...")
            
            # کد کامل seeding
            prompts_to_seed = {
                key: value for key, value in vars(prompts_file).items()
                if not key.startswith('__') and isinstance(value, str)
            }
            if not prompts_to_seed:
                raise RuntimeError("No string variables found in prompts.py to seed the database.")

            insert_stmt = text("INSERT INTO public.prompts (prompt_key, prompt_value) VALUES (:key, :value)")
            data_to_insert = [{"key": key, "value": value} for key, value in prompts_to_seed.items()]
            
            conn.execute(insert_stmt, data_to_insert)
            conn.commit()
            logger.info(f"Successfully seeded {len(prompts_to_seed)} prompts into the database.")
        
        all_prompts_result = conn.execute(text("SELECT prompt_key, prompt_value FROM public.prompts")).mappings().all()
        PROMPTS = {row['prompt_key']: row['prompt_value'] for row in all_prompts_result}
        logger.info(f"Successfully loaded {len(PROMPTS)} prompts from the database into memory.")

        # --- خواندن یا ایجاد تنظیم مدل LLM ---
        SELECTED_MODEL_NAME = _sync_get_or_create_setting(conn, "SELECTED_LLM_MODEL", DEFAULT_MODEL)
        logger.info(f"Selected LLM model from settings: {SELECTED_MODEL_NAME}")
        
        # --- خواندن یا ایجاد کلید API ---
        GEMINI_API_KEY = _sync_get_or_create_setting(conn, "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
        if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
            raise RuntimeError("GEMINI_API_KEY is not set in database settings. Please configure it in the admin panel.")
        logger.info("Gemini API key loaded from database settings.")

    # --- ادامه راه‌اندازی مدل‌های هوش مصنوعی ---
    if not validate_model_access(GEMINI_API_KEY, SELECTED_MODEL_NAME):
        logger.warning(f"Primary model '{SELECTED_MODEL_NAME}' not accessible. Trying fallback models...")
        SELECTED_MODEL_NAME = try_fallback_models(GEMINI_API_KEY, SELECTED_MODEL_NAME)
        logger.info(f"Using model: {SELECTED_MODEL_NAME}")

    configure_genai(GEMINI_API_KEY)
    llm_model = genai.GenerativeModel(
        SELECTED_MODEL_NAME,
        system_instruction=PROMPTS.get('COUNSELOR_MANIFESTO', 'You are a helpful assistant.')
    )
    logger.info(f"Gemini API configured successfully with model: {SELECTED_MODEL_NAME}")

    # embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")
    # logger.info("Embedding model loaded successfully.")
    embedding_model = None

except Exception as e:
    logger.error(f"CRITICAL INITIALIZATION FAILED: {e}", exc_info=True)
    llm_model = embedding_model = engine = None



# ==============================================================================
# 4) User Information Extraction Helpers
# توابع کمکی برای استخراج اطلاعات کاربر از درخواست‌ها
# ==============================================================================

def extract_user_info_from_request(request_obj):
    """استخراج اطلاعات کاربر از درخواست HTTP"""
    user_info = {}
    
    # آدرس IP
    user_info['ip_address'] = request_obj.headers.get('X-Forwarded-For', 
                                                    request_obj.headers.get('X-Real-IP', 
                                                    request_obj.remote_addr))
    if ',' in user_info['ip_address']:
        user_info['ip_address'] = user_info['ip_address'].split(',')[0].strip()
    
    # User Agent
    user_agent = request_obj.headers.get('User-Agent', '')
    user_info['user_agent'] = user_agent
    
    # استخراج اطلاعات مرورگر و سیستم عامل
    browser_info = parse_user_agent(user_agent)
    user_info.update(browser_info)
    
    # اطلاعات اضافی از هدرها
    user_info['language'] = request_obj.headers.get('Accept-Language', '').split(',')[0].strip()
    user_info['referrer'] = request_obj.headers.get('Referer', '')
    
    # ایجاد session_id منحصر به فرد
    user_info['session_id'] = str(uuid.uuid4())
    
    return user_info

def parse_user_agent(user_agent):
    """تجزیه User Agent برای استخراج اطلاعات مرورگر و سیستم عامل"""
    info = {
        'browser_name': 'Unknown',
        'browser_version': 'Unknown',
        'operating_system': 'Unknown',
        'device_type': 'Desktop'
    }
    
    if not user_agent:
        return info
    
    # تشخیص مرورگر
    if 'Chrome' in user_agent and 'Edg' not in user_agent:
        info['browser_name'] = 'Chrome'
        match = re.search(r'Chrome/(\d+\.?\d*)', user_agent)
        if match:
            info['browser_version'] = match.group(1)
    elif 'Firefox' in user_agent:
        info['browser_name'] = 'Firefox'
        match = re.search(r'Firefox/(\d+\.?\d*)', user_agent)
        if match:
            info['browser_version'] = match.group(1)
    elif 'Safari' in user_agent and 'Chrome' not in user_agent:
        info['browser_name'] = 'Safari'
        match = re.search(r'Version/(\d+\.?\d*)', user_agent)
        if match:
            info['browser_version'] = match.group(1)
    elif 'Edg' in user_agent:
        info['browser_name'] = 'Edge'
        match = re.search(r'Edg/(\d+\.?\d*)', user_agent)
        if match:
            info['browser_version'] = match.group(1)
    
    # تشخیص سیستم عامل
    if 'Windows' in user_agent:
        info['operating_system'] = 'Windows'
        if 'Windows NT 10.0' in user_agent:
            info['operating_system'] = 'Windows 10/11'
        elif 'Windows NT 6.3' in user_agent:
            info['operating_system'] = 'Windows 8.1'
        elif 'Windows NT 6.1' in user_agent:
            info['operating_system'] = 'Windows 7'
    elif 'Mac OS X' in user_agent or 'macOS' in user_agent:
        info['operating_system'] = 'macOS'
    elif 'Linux' in user_agent:
        info['operating_system'] = 'Linux'
    elif 'Android' in user_agent:
        info['operating_system'] = 'Android'
        info['device_type'] = 'Mobile'
    elif 'iPhone' in user_agent or 'iPad' in user_agent:
        info['operating_system'] = 'iOS'
        if 'iPad' in user_agent:
            info['device_type'] = 'Tablet'
        else:
            info['device_type'] = 'Mobile'
    
    # تشخیص نوع دستگاه
    if 'Mobile' in user_agent or 'Android' in user_agent or 'iPhone' in user_agent:
        info['device_type'] = 'Mobile'
    elif 'Tablet' in user_agent or 'iPad' in user_agent:
        info['device_type'] = 'Tablet'
    
    return info

def get_location_info(ip_address):
    """دریافت اطلاعات جغرافیایی از IP (ساده شده)"""
    # در اینجا می‌توانید از سرویس‌های IP geolocation استفاده کنید
    # برای مثال: ipapi.co, ip-api.com, یا maxmind
    # فعلاً مقادیر پیش‌فرض برمی‌گردانیم
    
    # تشخیص کشور بر اساس IP (ساده شده)
    if ip_address.startswith('127.') or ip_address == '::1':
        return {'country': 'ایران', 'city': 'محلی', 'timezone': 'Asia/Tehran'}
    
    # برای IP های خارجی، می‌توانید از API های مخصوص استفاده کنید
    # فعلاً مقادیر پیش‌فرض
    return {'country': 'نامشخص', 'city': 'نامشخص', 'timezone': 'UTC'}

# ==============================================================================
# 5) DB Helpers
# توابع کمکی دیتابیس (بدون تغییر زیاد، به جز بخش پرامپت‌ها)
# ==============================================================================
# تابع برای آپدیت کردن پرامپت‌ها در دیتابیس
def _sync_update_prompts_in_db(prompts_dict: dict):
    with engine.connect() as conn:
        stmt = text("""
            INSERT INTO public.prompts (prompt_key, prompt_value) VALUES (:key, :value)
            ON CONFLICT (prompt_key) DO UPDATE SET prompt_value = EXCLUDED.prompt_value;
        """)
        for key, value in prompts_dict.items():
            conn.execute(stmt, {"key": key, "value": str(value)})
        conn.commit()

# تابع برای بارگذاری مجدد پرامپت‌ها در حافظه
def _sync_reload_all_data():
    """تمام پرامپت‌ها و تنظیمات را از دیتابیس مجدداً بارگذاری کرده و مدل هوش مصنوعی را آپدیت می‌کند."""
    global PROMPTS, llm_model, SELECTED_MODEL_NAME, GEMINI_API_KEY
    try:
        with engine.connect() as conn:
            # بارگذاری مجدد پرامپت‌ها
            prompts_result = conn.execute(text("SELECT prompt_key, prompt_value FROM public.prompts")).mappings().all()
            PROMPTS = {row['prompt_key']: row['prompt_value'] for row in prompts_result}
            
            # بارگذاری مجدد تنظیمات مدل
            new_model_name = conn.execute(
                text("SELECT setting_value FROM public.settings WHERE setting_key = 'SELECTED_LLM_MODEL'")
            ).scalar_one_or_none()
            
            # اگر تنظیم پیدا نشد، از مقدار پیش‌فرض استفاده می‌کنیم
            if new_model_name is None:
                new_model_name = DEFAULT_MODEL
                logger.warning(f"Setting 'SELECTED_LLM_MODEL' not found in DB. Using default: {DEFAULT_MODEL}")
            
            # بارگذاری مجدد کلید API
            new_api_key = conn.execute(
                text("SELECT setting_value FROM public.settings WHERE setting_key = 'GEMINI_API_KEY'")
            ).scalar_one_or_none()
            
            if new_api_key is None:
                new_api_key = os.getenv("GEMINI_API_KEY")
                logger.warning("Setting 'GEMINI_API_KEY' not found in DB. Using environment variable.")
            
            # اگر نام مدل یا کلید API تغییر کرده است، ابتدا آن را اعتبارسنجی می‌کنیم
            if new_model_name != SELECTED_MODEL_NAME or new_api_key != GEMINI_API_KEY or llm_model is None:
                if not validate_model_access(new_api_key, new_model_name):
                    logger.warning(f"Cannot access the new model '{new_model_name}'. Trying fallbacks...")
                    working_model = try_fallback_models(new_api_key, new_model_name)
                    
                    if working_model != new_model_name:
                        logger.info(f"Using fallback model instead: {working_model}")
                        new_model_name = working_model
                    else:
                        logger.error("All models failed. Reverting to the previously active configuration to keep the service running.")
                        # بازگشت به تنظیمات قبلی تا برنامه متوقف نشود
                        new_model_name = SELECTED_MODEL_NAME
                        new_api_key = GEMINI_API_KEY
                
                # به‌روزرسانی متغیرهای گلوبال با مقادیر تایید شده نهایی
                SELECTED_MODEL_NAME = new_model_name
                GEMINI_API_KEY = new_api_key

            # ✅ **راه‌حل اصلی:** مدل زبان را *همیشه* پس از بارگذاری داده‌ها، 
            # با جدیدترین دستورالعمل سیستمی از حافظه، دوباره می‌سازیم.
            configure_genai(GEMINI_API_KEY)
            llm_model = genai.GenerativeModel(
                SELECTED_MODEL_NAME,
                system_instruction=PROMPTS.get('COUNSELOR_MANIFESTO', 'You are a helpful assistant.')
            )
            logger.info(f"LLM model '{SELECTED_MODEL_NAME}' has been successfully re-configured with the latest system prompt.")

        logger.info(f"All data reloaded. {len(PROMPTS)} prompts are now active in memory.")
    except Exception as e:
        logger.error(f"Failed to reload data from DB: {e}", exc_info=True)
        raise

# ... (تمام توابع دیگر get_or_create_user, get_conversation و غیره را بدون تغییر اینجا قرار دهید) ...
def _sync_get_or_create_user(web_user_id: str, first_name: str, user_info: dict = None) -> int:
    with engine.connect() as conn:
        user_id = conn.execute(text("SELECT id FROM public.users WHERE telegram_user_id = :tid"), {"tid": web_user_id}).scalar_one_or_none()
        
        if user_id:
            # کاربر موجود است - بروزرسانی اطلاعات
            if user_info:
                update_fields = []
                update_params = {"uid": user_id, "tid": web_user_id}
                
                # فیلدهای قابل بروزرسانی
                updatable_fields = [
                    'ip_address', 'user_agent', 'browser_name', 'browser_version',
                    'operating_system', 'device_type', 'country', 'city', 'timezone',
                    'language', 'referrer', 'session_id', 'last_seen'
                ]
                
                for field in updatable_fields:
                    if field in user_info and user_info[field]:
                        update_fields.append(f"{field} = :{field}")
                        update_params[field] = user_info[field]
                
                if update_fields:
                    update_fields.append("visit_count = visit_count + 1")
                    update_fields.append("updated_at = NOW()")
                    
                    stmt = text(f"""
                        UPDATE public.users 
                        SET {', '.join(update_fields)}
                        WHERE id = :uid
                    """)
                    conn.execute(stmt, update_params)
                    conn.commit()
            
            return user_id
        
        # کاربر جدید - ایجاد رکورد جدید
        if user_info is None:
            user_info = {}
        
        # اضافه کردن اطلاعات جغرافیایی
        if 'ip_address' in user_info:
            location_info = get_location_info(user_info['ip_address'])
            user_info.update(location_info)
        
        # تنظیم مقادیر پیش‌فرض
        default_values = {
            'first_name': first_name,
            'visit_count': 1,
            'created_at': datetime.now(),
            'updated_at': datetime.now(),
            'last_seen': datetime.now()
        }
        user_info.update(default_values)
        
        # ایجاد کوئری INSERT
        fields = ['telegram_user_id']
        values = [':telegram_user_id']
        params = {'telegram_user_id': web_user_id}
        
        # اضافه کردن فیلدهای موجود در user_info
        db_fields_mapping = {
            'ip_address': 'ip_address',
            'user_agent': 'user_agent', 
            'browser_name': 'browser_name',
            'browser_version': 'browser_version',
            'operating_system': 'operating_system',
            'device_type': 'device_type',
            'country': 'country',
            'city': 'city',
            'timezone': 'timezone',
            'language': 'language',
            'referrer': 'referrer',
            'session_id': 'session_id',
            'first_name': 'first_name',
            'visit_count': 'visit_count',
            'created_at': 'created_at',
            'updated_at': 'updated_at',
            'last_seen': 'last_seen'
        }
        
        for key, db_field in db_fields_mapping.items():
            if key in user_info:
                fields.append(db_field)
                values.append(f':{key}')
                params[key] = user_info[key]
        
        stmt = text(f"""
            INSERT INTO public.users ({', '.join(fields)}) 
            VALUES ({', '.join(values)}) 
            RETURNING id
        """)
        
        result = conn.execute(stmt, params)
        conn.commit()
        return result.scalar_one()

async def get_or_create_user(web_user_id: str, first_name: str = "WebUser", user_info: dict = None) -> int | None:
    if not engine: return None
    return await asyncio.to_thread(_sync_get_or_create_user, web_user_id, first_name, user_info)

def _sync_get_conversation(user_id: int) -> dict:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT conversation_history, career_profile FROM public.conversations WHERE user_id = :uid"), {"uid": user_id}).mappings().first()
        if result: return dict(result)
        conn.execute(text("INSERT INTO public.conversations (user_id, conversation_history) VALUES (:uid, '[]'::jsonb)"), {"uid": user_id})
        conn.commit()
        return {"conversation_history": [], "career_profile": None}

async def get_conversation(user_id: int) -> dict:
    if not engine: return {}
    return await asyncio.to_thread(_sync_get_conversation, user_id)

def _sync_save_conversation(user_id: int, history: list):
    with engine.connect() as conn:
        conn.execute(text("UPDATE public.conversations SET conversation_history = :hist WHERE user_id = :uid"), {"hist": json.dumps(history, ensure_ascii=False), "uid": user_id})
        conn.commit()

async def save_conversation(user_id: int, history: list):
    if not engine: return
    await asyncio.to_thread(_sync_save_conversation, user_id, history)

def to_pgvector_literal(vec_floats: list) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vec_floats) + "]"

def _sync_save_full_profile(user_id: int, **kwargs):
    update_data = {"uid": user_id}
    set_clauses = []
    for key, value in kwargs.items():
        if value is None: continue
        if key in ["career_profile", "evidence", "riasec_scores", "work_values_scores", "work_styles_scores"]:
            param_key = f"json_{key}"
            update_data[param_key] = json.dumps(value, ensure_ascii=False)
            set_clauses.append(f"{key} = :{param_key}")
        elif key == "user_embedding":
            update_data["ue"] = to_pgvector_literal(value)
            set_clauses.append("user_embedding = CAST(:ue AS vector)")
        else:
            param_key = f"param_{key}"
            update_data[param_key] = value
            set_clauses.append(f"{key} = :{param_key}")
    if not set_clauses: return
    stmt = text(f"UPDATE public.conversations SET {', '.join(set_clauses)} WHERE user_id = :uid")
    with engine.connect() as conn:
        conn.execute(stmt, update_data)
        conn.commit()

async def save_full_profile(user_id: int, **kwargs):
    if not engine: return
    await asyncio.to_thread(_sync_save_full_profile, user_id, **kwargs)

def _sync_mark_report_generated(user_id: int):
    with engine.connect() as conn:
        conn.execute(text("UPDATE public.conversations SET report_generated = NOW() WHERE user_id = :uid"), {"uid": user_id})
        conn.commit()

async def mark_report_generated(user_id: int):
    if not engine: return
    await asyncio.to_thread(_sync_mark_report_generated, user_id)

def _sync_update_prompts_in_db(prompts_dict: dict):
    """با استفاده از یک عملیات گروهی، پرامپت‌ها را در دیتابیس آپدیت (upsert) می‌کند."""
    try:
        data_to_update = [{"key": k, "value": v} for k, v in prompts_dict.items()]
        
        stmt = text("""
            INSERT INTO public.prompts (prompt_key, prompt_value)
            VALUES (:key, :value)
            ON CONFLICT (prompt_key)
            DO UPDATE SET prompt_value = EXCLUDED.prompt_value;
        """)

        with engine.connect() as conn:
            conn.execute(stmt, data_to_update)
            conn.commit()
        logger.info(f"Successfully updated/inserted {len(data_to_update)} prompts in the database.")
    except Exception as e:
        logger.error(f"Failed to update prompts in DB: {e}", exc_info=True)
        raise # خطا را دوباره ایجاد می‌کنیم تا در route handler مدیریت شود

def _sync_create_shared_chat(user_id: str, conversation_data: list, career_profile: dict = None) -> str:
    """ایجاد لینک اشتراک‌گذاری برای چت"""
    try:
        # تولید share_id منحصر به فرد
        timestamp = int(datetime.now().timestamp())
        random_part = secrets.token_urlsafe(16)
        share_id = f"{timestamp}_{random_part}"
        
        with engine.connect() as conn:
            stmt = text("""
                INSERT INTO public.shared_chats (share_id, original_user_id, conversation_data, career_profile)
                VALUES (:share_id, :user_id, :conversation_data, :career_profile)
                RETURNING share_id
            """)
            
            result = conn.execute(stmt, {
                "share_id": share_id,
                "user_id": user_id,
                "conversation_data": json.dumps(conversation_data, ensure_ascii=False),
                "career_profile": json.dumps(career_profile, ensure_ascii=False) if career_profile else None
            })
            conn.commit()
            
            return result.scalar_one()
    except Exception as e:
        logger.error(f"Failed to create shared chat: {e}", exc_info=True)
        raise

def _sync_get_shared_chat(share_id: str) -> dict:
    """دریافت چت اشتراکی"""
    try:
        with engine.connect() as conn:
            # بروزرسانی view_count
            conn.execute(text("""
                UPDATE public.shared_chats 
                SET view_count = view_count + 1, last_viewed_at = NOW()
                WHERE share_id = :share_id
            """), {"share_id": share_id})
            
            # دریافت اطلاعات shared_chat
            shared_chat_stmt = text("""
                SELECT original_user_id, created_at, view_count
                FROM public.shared_chats 
                WHERE share_id = :share_id
            """)
            
            shared_result = conn.execute(shared_chat_stmt, {"share_id": share_id}).mappings().first()
            
            if not shared_result:
                return None
            
            # دریافت داده‌های live از جدول conversations
            user_id_stmt = text("""
                SELECT id FROM public.users 
                WHERE telegram_user_id = :user_id
            """)
            
            user_id = conn.execute(user_id_stmt, {"user_id": shared_result["original_user_id"]}).scalar_one_or_none()
            
            if not user_id:
                return None
            
            # دریافت conversation_history و career_profile از جدول conversations
            conversation_stmt = text("""
                SELECT conversation_history, career_profile 
                FROM public.conversations 
                WHERE user_id = :user_id
            """)
            
            conv_result = conn.execute(conversation_stmt, {"user_id": user_id}).mappings().first()
            
            if not conv_result:
                return None
            
            conversation_data = conv_result["conversation_history"]
            career_profile = conv_result["career_profile"]
            
            logger.info(f"Raw conversation_data type: {type(conversation_data)}")
            
            # اگر conversation_data یک string است، آن را parse کنیم
            if isinstance(conversation_data, str):
                try:
                    conversation_data = json.loads(conversation_data)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse conversation_data JSON: {e}")
                    return None
            
            # اگر career_profile یک string است، آن را parse کنیم
            if isinstance(career_profile, str):
                try:
                    career_profile = json.loads(career_profile)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse career_profile JSON: {e}")
                    career_profile = None
            
            logger.info(f"Processed conversation_data type: {type(conversation_data)}, length: {len(conversation_data) if isinstance(conversation_data, list) else 'N/A'}")
            
            conn.commit()
            
            return {
                "conversation": conversation_data,
                "career_profile": career_profile,
                "created_at": shared_result["created_at"],
                "view_count": shared_result["view_count"]
            }
    except Exception as e:
        logger.error(f"Failed to get shared chat: {e}", exc_info=True)
        return None

# ==============================================================================
# 5) LLM Helpers
# ... (این بخش بدون تغییر باقی می‌ماند) ...
# ==============================================================================
async def llm_generate_with_retry(model, contents, tries=3, backoff=1.5):
    last_err = None
    for i in range(tries):
        try:
            return await asyncio.to_thread(lambda: model.generate_content(contents))
        except Exception as e:
            last_err = e
            error_msg = str(e)
            
            # بررسی خطای کوتای - فوراً متوقف می‌شویم
            if "429" in error_msg or "quota" in error_msg.lower() or "exceeded" in error_msg.lower():
                logger.warning(f"API quota exceeded. Stopping retry attempts immediately.")
                # فوراً پیام fallback برمی‌گردانیم
                fallback_response = type('obj', (object,), {
                    'text': "متاسفانه در حال حاضر به دلیل محدودیت استفاده روزانه، سرویس هوش مصنوعی در دسترس نیست. لطفاً فردا دوباره تلاش کنید یا پلن API خود را ارتقا دهید."
                })
                return fallback_response
            
            logger.warning(f"LLM call failed (attempt {i+1}/{tries}): {e}")
            await asyncio.sleep(backoff * (i + 1))
    
    # اگر همه تلاش‌ها ناموفق بود (غیر از quota)
    raise last_err

def sanitize_history(raw_history: list) -> list:
    safe = []
    for entry in (raw_history or []):
        if not isinstance(entry, dict): continue
        role = entry.get("role")
        if role not in ("user", "model"): continue
        parts_list = entry.get("parts", [])
        if not isinstance(parts_list, list): parts_list = [parts_list]
        texts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in parts_list]
        clean_texts = [t for t in texts if isinstance(t, str) and t.strip()]
        if clean_texts:
            safe.append({"role": role, "parts": clean_texts})
    return safe

# ==============================================================================
# 6) Evidence Extraction & Scoring
# ==============================================================================
async def extract_evidence_with_llm(history_contents: list):
    # حالا پرامپت از دیکشنری خوانده می‌شود
    prompt = PROMPTS.get('EVIDENCE_EXTRACTION_PROMPT', '{}')
    response = await llm_generate_with_retry(llm_model, history_contents + [{"role": "user", "parts": [prompt]}])
    clean_json_text = response.text.strip().replace("```json", "").replace("```", "")
    return json.loads(clean_json_text or "{}")

# ... (تابع score_with_ebp بدون تغییر باقی می‌ماند) ...
def score_with_ebp(ev_json: dict):
    # This function uses hardcoded values from prompts.py, let's keep it that way for simplicity
    # or move these settings to another config/db table later.
    from prompts import DEFAULT_SCORES, RIASEC_NAMES, WORK_VALUES_NAMES, WORK_STYLES_NAMES, JOB_ZONE_MAPPING
    
    def clip(x, lo, hi): return max(lo, min(hi, x))
    rs_sum, wv_sum, ws_sum = {k: DEFAULT_SCORES["riasec_base"] for k in RIASEC_NAMES}, {k: DEFAULT_SCORES["work_values_base"] for k in WORK_VALUES_NAMES}, {k: DEFAULT_SCORES["work_styles_base"] for k in WORK_STYLES_NAMES}
    
    education_hint = (ev_json or {}).get("education_hint", "Unknown") or "Unknown"
    comp_hints = set((ev_json or {}).get("complexity_hints", []) or [])
    
    for e in (ev_json or {}).get("evidence", []) or []:
        cat, name, strength, conf = e.get("category", ""), e.get("name", ""), int(e.get("strength", 1)), float(e.get("confidence", 0.5))
        delta = (0.3 + 0.5 * conf) * max(1, min(3, strength))
        if cat == "RIASEC" and name in rs_sum: rs_sum[name] += delta
        elif cat == "WorkValue" and name in wv_sum: wv_sum[name] += delta
        elif cat == "WorkStyle" and name in ws_sum: ws_sum[name] += delta
        
    rs_scores = {k: round(clip(v, 1.0, 7.0), 2) for k, v in rs_sum.items()}
    wv_scores = {k: round(clip(v, 1.0, 6.0), 2) for k, v in wv_sum.items()}
    ws_scores = {k: round(clip(v, 1.0, 5.0), 2) for k, v in ws_sum.items()}
    
    base_map = JOB_ZONE_MAPPING
    jz = base_map.get(education_hint, 3) + ('complex_projects' in comp_hints) + ('management_desire' in comp_hints) - ('routine_preference' in comp_hints) - ('job_security_emphasis' in comp_hints)
    jz = int(clip(jz, 1, 5))
    
    jz_just = f"Base={education_hint}→{base_map.get(education_hint, 3)}; Adj: +{int('complex_projects' in comp_hints)}(complex) +{int('management_desire' in comp_hints)}(mgmt) -{int('routine_preference' in comp_hints)}(routine) -{int('job_security_emphasis' in comp_hints)}(security)."
    
    career_profile = {"job_zone": jz, "interests": rs_scores, "work_values": wv_scores, "work_styles": ws_scores}
    return career_profile, jz, jz_just


async def build_personality_paragraph(career_profile: dict) -> str:
    prompt_text = PROMPTS.get('PERSONALITY_PARAGRAPH_PROMPT', '').format(
        career_profile=json.dumps(career_profile, ensure_ascii=False, indent=2)
    )
    response = await llm_generate_with_retry(llm_model, prompt_text)
    return (response.text or "").strip()


# ==============================================================================
# 7) Final Analysis & Matching
# ==============================================================================
async def run_final_analysis_and_matching(user_id: int, history: list) -> str:
    # if not all([llm_model, embedding_model, engine]):
    if not all([llm_model, engine]):
        return PROMPTS.get('SYSTEM_ERROR_MESSAGE', 'System error.')
    try:
        history_gemini_fmt = sanitize_history(history)
        evidence_json = await extract_evidence_with_llm(history_gemini_fmt)
        career_profile, jz, jz_just = score_with_ebp(evidence_json)
        personality_paragraph = await build_personality_paragraph(career_profile)
        
        # final_user_vector = embedding_model.encode(personality_paragraph).tolist()
        final_user_vector = embed_with_gemini(personality_paragraph)

        def _sync_db_matching():
            with engine.connect() as conn:
                sql_best = text("SELECT title FROM public.jobs WHERE job_zone = :jz ORDER BY embedding <=> CAST(:embedding AS vector) ASC LIMIT 10")
                best_matches = conn.execute(sql_best, {"jz": jz, "embedding": to_pgvector_literal(final_user_vector)}).mappings().all()
                sql_worst = text("SELECT title FROM public.jobs WHERE job_zone = :jz ORDER BY embedding <=> CAST(:embedding AS vector) DESC LIMIT 10")
                worst_matches = conn.execute(sql_worst, {"jz": jz, "embedding": to_pgvector_literal(final_user_vector)}).mappings().all()
                return [r['title'] for r in best_matches], [r['title'] for r in worst_matches]

        best_jobs_list, worst_jobs_list = await asyncio.to_thread(_sync_db_matching)
        
        report_prompt = PROMPTS.get('FINAL_REPORT_PROMPT', '').format(
            personality_paragraph=personality_paragraph,
            best_jobs_list=json.dumps(best_jobs_list, ensure_ascii=False),
            worst_jobs_list=json.dumps(worst_jobs_list, ensure_ascii=False),
            conversation_history=json.dumps(history_gemini_fmt, ensure_ascii=False)
        )
        
        enhanced_report_prompt = f"{PROMPTS.get('OUTPUT_PROTOCOL', '')}\n\n{report_prompt}"
        final_report_response = await llm_generate_with_retry(llm_model, enhanced_report_prompt)
        final_report = (final_report_response.text or "گزارشی تولید نشد.").strip()

        await save_full_profile(
            user_id=user_id, career_profile=career_profile, evidence=evidence_json,
            riasec_scores=career_profile.get("interests"), work_values_scores=career_profile.get("work_values"),
            work_styles_scores=career_profile.get("work_styles"), job_zone_estimate=jz,
            job_zone_justification=jz_just, personality_paragraph=personality_paragraph,
            user_embedding=final_user_vector, final_report_text=final_report
        )
        await mark_report_generated(user_id)
        
        return final_report

    except Exception as e:
        logger.error(f"Critical error in final analysis for user {user_id}: {e}", exc_info=True)
        return PROMPTS.get('UNEXPECTED_ERROR_MESSAGE', 'Unexpected error.')


# ==============================================================================
# 8) Web Server Logic (Flask)
# ==============================================================================
app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))  # کلید مخفی برای session ها

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/admin/login', methods=['POST'])
def admin_login():
    """ورود ادمین"""
    try:
        data = request.json
        password = data.get('password', '')
        
        correct_password = get_admin_password()
        
        if password == correct_password:
            session['admin_authenticated'] = True
            session.permanent = True  # session دائمی تا مرورگر بسته شود
            logger.info("Admin successfully logged in")
            return jsonify({'message': 'ورود موفقیت‌آمیز'}), 200
        else:
            logger.warning("Failed admin login attempt")
            return jsonify({'error': 'رمز عبور اشتباه است'}), 401
            
    except Exception as e:
        logger.error(f"Error in admin login: {e}")
        return jsonify({'error': 'خطا در سرور'}), 500

@app.route('/admin/logout', methods=['POST', 'GET'])
def admin_logout():
    """خروج ادمین"""
    # پاک کردن تمام session
    session.clear()
    logger.info("Admin logged out")
    
    # اگر GET request است، redirect به صفحه اصلی
    if request.method == 'GET':
        return redirect('/')
    
    # اگر POST request است، JSON response برگردانیم
    return jsonify({'message': 'خروج موفقیت‌آمیز'}), 200

@app.route('/admin/change-password', methods=['POST'])
@require_admin_auth
def admin_change_password():
    """تغییر رمز عبور ادمین"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'داده‌ای ارسال نشده است'}), 400
            
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        
        # بررسی وجود رمز فعلی
        if not current_password:
            return jsonify({'error': 'رمز عبور فعلی وارد نشده است'}), 400
            
        # بررسی وجود رمز جدید
        if not new_password:
            return jsonify({'error': 'رمز عبور جدید وارد نشده است'}), 400
        
        correct_password = get_admin_password()
        
        # بررسی رمز فعلی
        if current_password != correct_password:
            logger.warning(f"Failed password change attempt - wrong current password")
            return jsonify({'error': 'رمز عبور فعلی اشتباه است'}), 401
        
        # بررسی طول رمز جدید
        if len(new_password) < 6:
            return jsonify({'error': 'رمز عبور جدید باید حداقل 6 کاراکتر باشد'}), 400
        
        # ذخیره رمز جدید در دیتابیس
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO public.settings (setting_key, setting_value) 
                    VALUES ('ADMIN_PASSWORD', :password)
                    ON CONFLICT (setting_key) 
                    DO UPDATE SET setting_value = EXCLUDED.setting_value
                """),
                {"password": new_password}
            )
            conn.commit()
        
        logger.info("Admin password changed successfully")
        return jsonify({'message': 'رمز عبور با موفقیت تغییر کرد'}), 200
        
    except Exception as e:
        logger.error(f"Error changing admin password: {e}")
        return jsonify({'error': 'خطا در تغییر رمز عبور'}), 500

@app.route('/admin')
@require_admin_auth
def serve_admin():
    return send_from_directory('.', 'admin.html')

@app.route('/admin/stats-page')
@require_admin_auth
def serve_stats():
    return send_from_directory('.', 'stats.html')

@app.route('/shared/<share_id>')
def serve_shared_chat(share_id):
    return send_from_directory('.', 'shared_chat.html')

@app.route('/share-chat', methods=['POST'])
def share_chat():
    """ایجاد لینک اشتراک‌گذاری برای چت"""
    try:
        data = request.json
        user_id = data.get('user_id')
        conversation = data.get('conversation', [])
        career_profile = data.get('career_profile')
        
        if not user_id or not conversation:
            return jsonify({'error': 'User ID and conversation are required'}), 400
        
        share_id = _sync_create_shared_chat(user_id, conversation, career_profile)
        return jsonify({'share_id': share_id})
        
    except Exception as e:
        logger.error(f"Error in share-chat endpoint: {e}", exc_info=True)
        return jsonify({'error': 'خطا در ایجاد لینک اشتراک‌گذاری'}), 500

@app.route('/api/shared/<share_id>', methods=['GET'])
def get_shared_chat(share_id):
    """دریافت چت اشتراکی"""
    try:
        shared_data = _sync_get_shared_chat(share_id)
        
        if not shared_data:
            return jsonify({'error': 'چت اشتراکی یافت نشد یا منقضی شده است'}), 404
        
        return jsonify(shared_data)
        
    except Exception as e:
        logger.error(f"Error in get-shared-chat endpoint: {e}", exc_info=True)
        return jsonify({'error': 'خطا در دریافت چت اشتراکی'}), 500

@app.route('/admin/stats')
@require_admin_auth
def admin_stats():
    """نمایش آمار کاربران"""
    try:
        with engine.connect() as conn:
            # آمار کلی
            total_users = conn.execute(text("SELECT COUNT(*) FROM public.users")).scalar_one()
            
            # آمار مرورگرها
            browser_stats = conn.execute(text("""
                SELECT browser_name, COUNT(*) as count 
                FROM public.users 
                WHERE browser_name != 'Unknown' 
                GROUP BY browser_name 
                ORDER BY count DESC
            """)).mappings().all()
            
            # آمار سیستم عامل
            os_stats = conn.execute(text("""
                SELECT operating_system, COUNT(*) as count 
                FROM public.users 
                WHERE operating_system != 'Unknown' 
                GROUP BY operating_system 
                ORDER BY count DESC
            """)).mappings().all()
            
            # آمار کشورها
            country_stats = conn.execute(text("""
                SELECT country, COUNT(*) as count 
                FROM public.users 
                WHERE country != 'نامشخص' AND country IS NOT NULL
                GROUP BY country 
                ORDER BY count DESC
                LIMIT 10
            """)).mappings().all()
            
            # آمار نوع دستگاه
            device_stats = conn.execute(text("""
                SELECT device_type, COUNT(*) as count 
                FROM public.users 
                WHERE device_type IS NOT NULL
                GROUP BY device_type 
                ORDER BY count DESC
            """)).mappings().all()
            
            # کاربران فعال (آخرین 24 ساعت)
            active_users = conn.execute(text("""
                SELECT COUNT(*) FROM public.users 
                WHERE last_seen > NOW() - INTERVAL '24 hours'
            """)).scalar_one()
            
            stats = {
                'total_users': total_users,
                'active_users_24h': active_users,
                'browser_stats': [dict(row) for row in browser_stats],
                'os_stats': [dict(row) for row in os_stats],
                'country_stats': [dict(row) for row in country_stats],
                'device_stats': [dict(row) for row in device_stats]
            }
            
            return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}", exc_info=True)
        return jsonify({'error': 'خطا در دریافت آمار'}), 500

@app.route('/admin/recent-shared-chats')
@require_admin_auth
def admin_recent_shared_chats():
    """دریافت لیست 100 چت اشتراکی اخیر"""
    try:
        with engine.connect() as conn:
            # دریافت 100 چت اشتراکی اخیر به ترتیب جدیدترین
            shared_chats = conn.execute(text("""
                SELECT 
                    share_id,
                    original_user_id,
                    created_at,
                    view_count,
                    last_viewed_at,
                    expires_at,
                    CASE 
                        WHEN expires_at > NOW() THEN true 
                        ELSE false 
                    END as is_active
                FROM public.shared_chats 
                ORDER BY created_at DESC 
                LIMIT 100
            """)).mappings().all()
            
            # تبدیل به لیست دیکشنری
            chats_list = []
            for row in shared_chats:
                chat_data = {
                    'share_id': row['share_id'],
                    'original_user_id': row['original_user_id'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'view_count': row['view_count'],
                    'last_viewed_at': row['last_viewed_at'].isoformat() if row['last_viewed_at'] else None,
                    'expires_at': row['expires_at'].isoformat() if row['expires_at'] else None,
                    'is_active': row['is_active'],
                    'share_url': f"/shared/{row['share_id']}"
                }
                chats_list.append(chat_data)
            
            return jsonify({
                'shared_chats': chats_list,
                'total_count': len(chats_list)
            })
            
    except Exception as e:
        logger.error(f"Error getting recent shared chats: {e}", exc_info=True)
        return jsonify({'error': 'خطا در دریافت لیست چت‌های اشتراکی'}), 500

@app.route('/admin/all-chats')
@require_admin_auth
def admin_all_chats():
    """دریافت لیست چت‌ها با pagination"""
    try:
        # دریافت پارامترهای pagination
        offset = request.args.get('offset', 0, type=int)
        limit = request.args.get('limit', 50, type=int)
        
        with engine.connect() as conn:
            # دریافت تعداد کل چت‌ها
            total_count = conn.execute(text("""
                SELECT COUNT(*) FROM public.conversations
            """)).scalar_one()
            
            # دریافت چت‌ها با pagination
            all_chats = conn.execute(text("""
                SELECT 
                    c.id as conversation_id,
                    c.user_id,
                    c.created_at,
                    c.updated_at,
                    c.report_generated,
                    u.telegram_user_id,
                    u.first_name,
                    sc.share_id,
                    sc.view_count,
                    sc.last_viewed_at,
                    sc.expires_at,
                    CASE 
                        WHEN sc.share_id IS NOT NULL AND sc.expires_at > NOW() THEN true 
                        ELSE false 
                    END as has_active_share,
                    CASE 
                        WHEN sc.share_id IS NOT NULL THEN true 
                        ELSE false 
                    END as has_share
                FROM public.conversations c
                LEFT JOIN public.users u ON c.user_id = u.id
                LEFT JOIN public.shared_chats sc ON sc.original_user_id = u.telegram_user_id
                ORDER BY c.updated_at DESC 
                LIMIT :limit OFFSET :offset
            """), {"limit": limit, "offset": offset}).mappings().all()
            
            # تبدیل به لیست دیکشنری
            chats_list = []
            for row in all_chats:
                # اگر لینک اشتراکی وجود ندارد، یکی ایجاد می‌کنیم
                share_url = None
                share_id = row['share_id']
                
                if not share_id:
                    # ایجاد لینک اشتراکی جدید
                    try:
                        # دریافت conversation_data
                        conv_data = conn.execute(text("""
                            SELECT conversation_history FROM public.conversations 
                            WHERE id = :conv_id
                        """), {"conv_id": row['conversation_id']}).scalar_one_or_none()
                        
                        if conv_data:
                            # تبدیل به فرمت مناسب
                            if isinstance(conv_data, str):
                                try:
                                    conversation_data = json.loads(conv_data)
                                except json.JSONDecodeError:
                                    conversation_data = []
                            elif isinstance(conv_data, list):
                                conversation_data = conv_data
                            else:
                                conversation_data = []
                            
                            # بررسی اینکه آیا conversation_data خالی نیست
                            if conversation_data and len(conversation_data) > 0:
                                # ایجاد لینک اشتراکی
                                share_id = _sync_create_shared_chat(
                                    row['telegram_user_id'], 
                                    conversation_data
                                )
                                share_url = f"/shared/{share_id}"
                            else:
                                share_url = "چت خالی است"
                        else:
                            share_url = "چت خالی است"
                    except Exception as e:
                        logger.error(f"Error creating share link for chat {row['conversation_id']}: {e}")
                        share_url = "خطا در ایجاد لینک"
                else:
                    share_url = f"/shared/{share_id}"
                
                chat_data = {
                    'conversation_id': row['conversation_id'],
                    'user_id': row['user_id'],
                    'telegram_user_id': row['telegram_user_id'],
                    'first_name': row['first_name'] or 'نامشخص',
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
                    'report_generated': row['report_generated'].isoformat() if row['report_generated'] else None,
                    'share_id': share_id,
                    'view_count': row['view_count'] or 0,
                    'last_viewed_at': row['last_viewed_at'].isoformat() if row['last_viewed_at'] else None,
                    'expires_at': row['expires_at'].isoformat() if row['expires_at'] else None,
                    'has_active_share': row['has_active_share'],
                    'has_share': row['has_share'],
                    'share_url': share_url
                }
                chats_list.append(chat_data)
            
            return jsonify({
                'all_chats': chats_list,
                'total_count': total_count
            })
            
    except Exception as e:
        logger.error(f"Error getting all chats: {e}", exc_info=True)
        return jsonify({'error': 'خطا در دریافت لیست چت‌ها'}), 500

@app.route('/admin/data', methods=['GET', 'POST'])
@require_admin_auth
def admin_data():
    if request.method == 'GET':
        settings = {
            "SELECTED_LLM_MODEL": SELECTED_MODEL_NAME,
            "GEMINI_API_KEY": GEMINI_API_KEY
        }
        
        # دریافت مدل‌های پویا از API
        try:
            dynamic_models = fetch_available_models_from_api(GEMINI_API_KEY)
            logger.info(f"Dynamic models fetched for admin panel: {dynamic_models}")
        except Exception as e:
            logger.error(f"Failed to fetch dynamic models, using fallback: {e}")
            # در صورت خطا، مدل‌های پیش‌فرض را استفاده کنیم
            dynamic_models = AVAILABLE_MODELS
        
        data = {
            "prompts": PROMPTS,
            "settings": settings,
            "available_models": dynamic_models
        }
        return jsonify(data)
    
    if request.method == 'POST':
        try:
            data = request.json
            new_prompts = data.get('prompts', {})
            new_settings = data.get('settings', {})
            
            # بررسی اعتبار مدل جدید اگر تغییر کرده باشد
            new_model_name = new_settings.get('SELECTED_LLM_MODEL')
            new_api_key = new_settings.get('GEMINI_API_KEY')
            
            if new_model_name and new_model_name != SELECTED_MODEL_NAME:
                logger.info(f"Validating new model: {new_model_name}")
                
                # استفاده از API key جدید اگر ارائه شده، در غیر این صورت از کلید فعلی
                api_key_to_validate = new_api_key if new_api_key else GEMINI_API_KEY
                
                if not validate_model_access(api_key_to_validate, new_model_name):
                    logger.warning(f"Model validation failed for: {new_model_name}")
                    
                    # تلاش برای پیدا کردن مدل جایگزین
                    fallback_model = try_fallback_models(api_key_to_validate, new_model_name)
                    
                    if fallback_model != new_model_name:
                        logger.info(f"Using fallback model: {fallback_model}")
                        # بروزرسانی تنظیمات با مدل جایگزین
                        new_settings['SELECTED_LLM_MODEL'] = fallback_model
                        
                        return jsonify({
                            'message': f'مدل انتخابی "{new_model_name}" قابل دسترسی نیست.',
                            'validation_failed': True,
                            'fallback_model': fallback_model,
                            'original_model': new_model_name
                        }), 200
                    else:
                        logger.error(f"All models failed validation for: {new_model_name}")
                        return jsonify({
                            'error': f'مدل انتخابی "{new_model_name}" قابل دسترسی نیست و هیچ مدل جایگزینی یافت نشد.',
                            'validation_failed': True,
                            'original_model': new_model_name
                        }), 400
            
            # ذخیره پرامپت‌ها
            _sync_update_prompts_in_db(new_prompts)
            
            # ذخیره تنظیمات
            with engine.connect() as conn:
                for key, value in new_settings.items():
                    conn.execute(
                        text("""
                            INSERT INTO public.settings (setting_key, setting_value) 
                            VALUES (:key, :value)
                            ON CONFLICT (setting_key) 
                            DO UPDATE SET setting_value = EXCLUDED.setting_value
                        """),
                        {"key": key, "value": value}
                    )
                conn.commit()
            
            # بارگذاری مجدد همه چیز
            _sync_reload_all_data() 
            
            return jsonify({'message': 'تغییرات با موفقیت ذخیره و بارگذاری مجدد شدند!'}), 200
        except Exception as e:
            logger.error(f"Error updating data: {e}", exc_info=True)
            return jsonify({'error': 'خطای داخلی سرور هنگام ذخیره تغییرات.'}), 500

@app.route('/admin/refresh-models', methods=['GET'])
@require_admin_auth
def admin_refresh_models():
    """دریافت لیست جدید مدل‌ها از API"""
    try:
        dynamic_models = fetch_available_models_from_api(GEMINI_API_KEY)
        logger.info(f"Models refreshed for admin panel: {dynamic_models}")
        return jsonify({
            'available_models': dynamic_models,
            'message': f'لیست مدل‌ها به‌روزرسانی شد ({len(dynamic_models)} مدل)'
        })
    except Exception as e:
        logger.error(f"Failed to refresh models: {e}")
        return jsonify({
            'available_models': AVAILABLE_MODELS,
            'error': f'خطا در به‌روزرسانی لیست مدل‌ها: {str(e)}'
        }), 500

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    web_user_id = data.get('user_id')
    user_message = data.get('message', '').strip()

    if not web_user_id or not user_message:
        return jsonify({'error': 'User ID and message are required'}), 400

    if not llm_model:
        return jsonify({'reply': 'متاسفانه سرویس هوش مصنوعی در حال حاضر در دسترس نیست.'}), 503

    try:
        response_data = asyncio.run(handle_web_message(web_user_id, user_message, request))
        return jsonify(response_data)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error in /chat endpoint for user {web_user_id}: {e}", exc_info=True)
        
        if "429" in error_msg or "quota" in error_msg.lower() or "exceeded" in error_msg.lower():
            return jsonify({
                'reply_type': 'standard',
                'reply': '⚠️ متاسفانه به دلیل محدودیت استفاده روزانه، سرویس هوش مصنوعی در حال حاضر در دسترس نیست. لطفاً فردا دوباره تلاش کنید یا پلن API خود را ارتقا دهید.',
                'error_type': 'quota_exceeded'
            }), 429
        else:
            return jsonify({
                'reply_type': 'standard',
                'reply': '⚠️ یک خطای داخلی در سرور رخ داد.'
            }), 500

@app.route('/start-analysis', methods=['POST'])
def start_analysis():
    data = request.json
    web_user_id = data.get('user_id')

    if not web_user_id:
        return jsonify({'error': 'User ID is required'}), 400

    try:
        # Run the analysis and get the final report and profile
        report, profile = asyncio.run(trigger_analysis_for_user(web_user_id))
        return jsonify({'final_report': report, 'career_profile': profile})
    except Exception as e:
        logger.error(f"Error in /start-analysis for user {web_user_id}: {e}", exc_info=True)
        return jsonify({'final_report': '⚠️ یک خطای داخلی در سرور هنگام تحلیل رخ داد.'}), 500

async def trigger_analysis_for_user(web_user_id: str) -> tuple[str, dict | None]:
    """
    >>> CHANGE: This function now cleans up the conversation history in the database
    after the final report is generated.
    """
    db_user_id = await get_or_create_user(web_user_id)
    if not db_user_id:
        return "خطا در یافتن اطلاعات کاربری شما.", None
    
    convo_data = await get_conversation(db_user_id)
    history = convo_data.get("conversation_history", [])
    
    # Run the analysis; this populates the final_report_text column in the DB
    final_report = await run_final_analysis_and_matching(db_user_id, history)
    
    # --- START: NEW LOGIC to clean up conversation history ---
    # Create a new, clean history to replace the one with the JSON signal
    clean_history = []
    found_and_replaced = False
    for message in history:
        is_signal = False
        # Check if the current message is the JSON signal from the model
        if message.get("role") == "model":
            try:
                parts = message.get("parts", [])
                if parts and isinstance(parts[0], str) and json.loads(parts[0]).get("analysis_complete") is True:
                    is_signal = True
            except (json.JSONDecodeError, IndexError, TypeError):
                # Not the signal, just a regular message
                pass
        
        if is_signal:
            # If it's the signal, replace it with the two messages the user actually saw
            initial_message = PROMPTS.get('ANALYSIS_START_MESSAGE', 'تحلیل شما تایید شد. در حال آماده‌سازی گزارش...')
            clean_history.append({"role": "model", "parts": [initial_message]})
            clean_history.append({"role": "model", "parts": [final_report]})
            found_and_replaced = True
        else:
            # Otherwise, just add the original message to the clean history
            clean_history.append(message)
            
    # If the replacement happened, save the clean history back to the database
    if found_and_replaced:
        await save_conversation(db_user_id, clean_history)
    # --- END: NEW LOGIC ---

    # Fetch the updated profile from the DB after analysis
    updated_convo_data = await get_conversation(db_user_id)
    career_profile = updated_convo_data.get("career_profile")
    
    return final_report, career_profile

async def handle_web_message(web_user_id: str, user_message: str, request_obj=None) -> dict:
    user_info = None
    if request_obj:
        user_info = extract_user_info_from_request(request_obj)
    
    db_user_id = await get_or_create_user(web_user_id, "WebUser", user_info)
    if not db_user_id:
        return {'reply_type': 'standard', 'reply': "خطا در دسترسی به اطلاعات کاربری شما."}

    convo_data = await get_conversation(db_user_id)
    history_gemini_fmt = sanitize_history(convo_data.get("conversation_history", []))

    contents = history_gemini_fmt + [{"role": "user", "parts": [user_message]}]
    response = await llm_generate_with_retry(llm_model, contents)
    bot_response_text = (response.text or "متوجه نشدم؛ می‌تونی کمی روشن‌تر توضیح بدی؟").strip()

    is_signal = False
    try:
        if json.loads(bot_response_text).get("analysis_complete") is True:
            is_signal = True
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass

    if is_signal:
        # 1. Create the final history entry including the bot's JSON signal
        updated_db_history = contents + [{"role": "model", "parts": [bot_response_text]}]
        
        # 2. Save this history to the database so the next request can access it
        await save_conversation(db_user_id, updated_db_history)
        
        # 3. Return an immediate response telling the frontend to start the analysis process
        return {
            'reply_type': 'analysis_started',
            'reply': PROMPTS.get('ANALYSIS_START_MESSAGE', 'تحلیل شما تایید شد. در حال آماده‌سازی گزارش...'),
        }
    else:
        # Standard message handling
        updated_db_history = contents + [{"role": "model", "parts": [bot_response_text]}]
        await save_conversation(db_user_id, updated_db_history)
        return {
            'reply_type': 'standard',
            'reply': bot_response_text,
        }

if __name__ == "__main__":
    # ابتدا بررسی می‌کنیم که آیا راه‌اندازی اولیه موفقیت‌آمیز بوده یا خیر
    if not all([engine, llm_model]):
        logger.error("="*59)
        logger.error("!!!   APPLICATION FAILED TO INITIALIZE   !!!")
        logger.error("یکی از کامپوننت‌های اصلی (دیتابیس یا مدل زبان) مقداردهی نشده است.")
        logger.error("لطفاً به خطاهای بالاتر در ترمینال دقت کنید تا دلیل اصلی را پیدا کنید.")
        logger.error("="*59)
        sys.exit(1)

    if "YOUR_GEMINI_API_KEY" in str(GEMINI_API_KEY) or "YOUR_PROJECT_REF" in PROJECT_REF:
        print("\n⚠️ هشدار: اطلاعات محرمانه در فایل .env تنظیم نشده است.")
    else:
        PORT = int(os.getenv("PORT", "5007"))
        print("✅ سرور Flask آماده به کار است.")
        print(f"صفحه چت در آدرس: http://127.0.0.1:{PORT}")
        print(f"پنل مدیریت پرامپت‌ها در آدرس: http://127.0.0.1:{PORT}/admin")
        app.run(host='0.0.0.0', port=PORT)