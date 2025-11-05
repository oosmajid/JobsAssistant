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
import requests
import uuid
import time
import secrets
from flask import Flask, request, jsonify, send_from_directory, session, redirect, render_template_string, Response
from flask_cors import CORS
from sqlalchemy import create_engine, text
import google.generativeai as genai
from google.api_core.client_options import ClientOptions
import jwt # برای ساختن توکن
import random
from datetime import datetime, timedelta, timezone # زمان‌بندی OTP و توکن
from kavenegar import KavenegarAPI # ارسال SMS
from functools import wraps # برای دکوریتور احراز هویت
from sqlalchemy.exc import IntegrityError # برای مدیریت خطاهای دیتابیس
# تعریف نام‌های مورد نیاز برای سیستم امتیازدهی (که هنوز در برخی توابع استفاده می‌شود)

KEY_MAP = {
    # RIASEC
    "Realistic": "واقع‌گرایانه",
    "Investigative": "جستجوگرانه",
    "Artistic": "هنری",
    "Social": "اجتماعی",
    "Enterprising": "کارآفرینانه", # توجه: CSV از "کارآفرینانه" استفاده می‌کند
    "Conventional": "قراردادی",
    
    # Work Values
    "Achievement": "موفقیت",
    "Independence": "استقلال", # این کلید در هر دو گروه وجود دارد
    "Recognition": "قدردانی",
    "Relationships": "روابط",
    "Support": "حمایت",
    "Working_Conditions": "شرایط کاری",

    # Work Styles
    "Attention_to_Detail": "توجه به جزئیات",
    "Stress_Tolerance": "تحمل استرس",
    "Initiative": "ابتکار",
    "Adaptability_Flexibility": "انعطاف‌پذیری",
    "Cooperation": "همکاری",
    "Leadership": "رهبری",
    "Dependability": "قابلیت اطمینان",
    "Integrity": "صداقت",
    "Self_Control": "خودکنترلی",
    "Persistence": "پشتکار",
    "Analytical_Thinking": "تفکر تحلیلی",
    "Concern_for_Others": "توجه به دیگران",
    "Achievement_Effort": "موفقیت/تلاش",
    "Social_Orientation": "جهت‌گیری اجتماعی",
    "Innovation": "نوآوری",
}

# فایل prompts.py فقط برای اولین راه‌اندازی (seeding) استفاده می‌شود
import prompts as prompts_file

# EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-small")
# EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "paraphrase-multilingual-mpnet-base-v2")
# EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
# تنظیمات لاگ‌گیری
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG,
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

# --- تنظیمات جدید برای لاگین ---
KAVEHNEGAR_API_KEY = os.getenv("KAVEHNEGAR_API_KEY")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "DEFAULT_FALLBACK_SECRET_KEY_CHANGE_ME")

# نمونه‌سازی API کاوه‌نگار
kaveh_api = None
if KAVEHNEGAR_API_KEY and KAVEHNEGAR_API_KEY != "YOUR_KAVEHNEGAR_API_KEY_HERE":
    try:
        kaveh_api = KavenegarAPI(KAVEHNEGAR_API_KEY)
        logger.info("Kavenegar API initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Kavenegar API: {e}")
else:
    logger.warning("KAVEHNEGAR_API_KEY not set. SMS functionality will be disabled.")
# --- پایان تنظیمات جدید ---

# --- [این بخش را اضافه کنید] ---
# ==============================================================================
# 6) Zarinpal & Credit Configuration
# ==============================================================================
ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID")
SUBSCRIPTION_PRICE = os.getenv("SUBSCRIPTION_PRICE", "100000") # قیمت اصلی اشتراک (۱۰۰ هزار تومان)
DISCOUNT_PRICE = os.getenv("DISCOUNT_PRICE", "49000") # قیمت تخفیف ۱ ساعته (۴۹ هزار تومان)

# آدرس‌های API زرین‌پال
ZARINPAL_REQUEST_URL = "https://api.zarinpal.com/pg/v4/payment/request.json"
ZARINPAL_VERIFY_URL = "https://api.zarinpal.com/pg/v4/payment/verify.json"
ZARINPAL_STARTPAY_URL = "https://www.zarinpal.com/pg/StartPay/"

# آدرس سرور شما برای بازگشت کاربر از درگاه پرداخت
# (مطمئن شوید که پورت 5007 با پورت اجرای برنامه شما یکی باشد)
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5007") 
PAYMENT_CALLBACK_URL = f"{APP_BASE_URL}/payment/verify"
# ---------------------------------

# [جدید] خواندن مدت زمان تخفیف از .env
try:
    DISCOUNT_DURATION_MINUTES = int(os.getenv("DISCOUNT_DURATION_MINUTES", "20"))
except ValueError:
    DISCOUNT_DURATION_MINUTES = 60 # استفاده از پیش‌فرض در صورت خطا

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

# قالب HTML برای نمایش چت در پنل ادمین
ADMIN_VIEW_CHAT_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>مشاهده چت - ادمین</title>
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        body { font-family: 'Vazirmatn', sans-serif; background-color: #f4f7f9; margin: 0; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; background: #fff; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .header { background: #007bff; color: white; padding: 20px; border-radius: 8px 8px 0 0; }
        .header h1 { margin: 0; font-size: 1.5em; }
        .chat-log { padding: 30px; }
        .message { max-width: 80%; padding: 12px 18px; border-radius: 18px; line-height: 1.6; margin-bottom: 20px; word-wrap: break-word; }
        .user-message { background-color: #007bff; color: white; border-bottom-right-radius: 5px; margin-left: auto; }
        .model-message { background-color: #e9ecef; color: #333; border-bottom-left-radius: 5px; margin-right: auto; }
        .message p { margin: 0 0 10px 0; } /* فاصله بین پاراگراف‌ها در markdown */
        .message p:last-child { margin-bottom: 0; }
        .message ul, .message ol { margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>مشاهده چت (Conversation ID: {{ conversation_id }})</h1>
            <p style="margin: 5px 0 0 0;">کاربر: {{ identifier }}</p>
        </div>
        <div class="chat-log" id="chat-log">
                    </div>
    </div>
    <script>
        const conversationHistory = {{ conversation_data|tojson }};
        const chatLog = document.getElementById('chat-log');
        
        marked.setOptions({ breaks: true, gfm: true });

        conversationHistory.forEach(msg => {
            const msgDiv = document.createElement('div');
            msgDiv.classList.add('message');
            msgDiv.classList.add(msg.role === 'user' ? 'user-message' : 'model-message');
            
            // parts می‌تواند آرایه باشد یا فقط متن
            let textContent = '';
            if (Array.isArray(msg.parts)) {
                textContent = msg.parts.map(part => (typeof part === 'object' ? part.text : part)).join('\\n\\n');
            } else if (msg.parts) {
                textContent = msg.parts;
            }

            msgDiv.innerHTML = marked.parse(textContent);
            chatLog.appendChild(msgDiv);
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
def _sync_update_prompts_in_db(prompts_dict: dict):
    with engine.connect() as conn:
        # از transaction برای اجرای گروهی استفاده می‌کنیم
        with conn.begin():
            stmt = text("""
                INSERT INTO public.prompts (prompt_key, prompt_value) VALUES (:key, :value)
                ON CONFLICT (prompt_key) DO UPDATE SET prompt_value = EXCLUDED.prompt_value;
            """)
            data_to_insert = [{"key": key, "value": str(value)} for key, value in prompts_dict.items()]
            if data_to_insert:
                conn.execute(stmt, data_to_insert)
        logger.info(f"Successfully upserted {len(data_to_insert)} prompts into the database.")

def _sync_reload_all_data():
    """تمام پرامپت‌ها و تنظیمات را از دیتابیس مجدداً بارگذاری کرده و مدل هوش مصنوعی را آپدیت می‌کند."""
    # NEW: generic_model را به global اضافه کنید
    global PROMPTS, llm_model, SELECTED_MODEL_NAME, GEMINI_API_KEY, generic_model
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
            
            # NEW: مدل جنریک را نیز دوباره بسازید
            generic_model = genai.GenerativeModel(SELECTED_MODEL_NAME)

            logger.info(f"LLM model '{SELECTED_MODEL_NAME}' has been successfully re-configured with the latest system prompt.")

        logger.info(f"All data reloaded. {len(PROMPTS)} prompts are now active in memory.")
    except Exception as e:
        logger.error(f"Failed to reload data from DB: {e}", exc_info=True)
        raise

# NEW: مدل جنریک را در سطح گلوبال تعریف کنید
llm_model = embedding_model = engine = None
generic_model = None

# --- راه‌اندازی اولیه سرویس‌ها ---
try:
    engine = create_engine(DB_CONNECTION_STRING, pool_pre_ping=True)
    logger.info("Database engine created successfully.")
    
    # --- بارگذاری اولیه و همگام‌سازی پرامپت‌ها از فایل prompts.py ---
    # این بخش تضمین می‌کند که دیتابیس همیشه با فایل هماهنگ است
    try:
        import prompts as prompts_file
        prompts_to_sync = {
            key: value for key, value in vars(prompts_file).items()
            if not key.startswith('__') and isinstance(value, str)
        }
        if prompts_to_sync:
            logger.info(f"Found {len(prompts_to_sync)} prompts in prompts.py to sync with the database.")
            _sync_update_prompts_in_db(prompts_to_sync)
        else:
            logger.warning("No prompts found in prompts.py to sync.")
            
    except ImportError:
        logger.error("prompts.py file not found. Skipping initial prompt sync.")
    except Exception as e:
        logger.error(f"An error occurred during prompt syncing: {e}", exc_info=True)

    SELECTED_MODEL_NAME = "" # متغیر گلوبال برای نگهداری نام مدل

    with engine.connect() as conn:
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
        conn.execute(text("ALTER TABLE public.shared_chats ADD COLUMN IF NOT EXISTS career_profile JSONB"))
        conn.execute(text("ALTER TABLE public.conversations ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()"))
        conn.execute(text("ALTER TABLE public.conversations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()"))
        conn.commit()
        logger.info("Database tables verified/updated successfully.")
        
        # --- بارگذاری تمام پرامپت‌ها از دیتابیس به حافظه ---
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
    
    # NEW: نمونه مدل جنریک را بسازید
    generic_model = genai.GenerativeModel(SELECTED_MODEL_NAME)
    logger.info(f"Generic model (for helpers) also configured with: {SELECTED_MODEL_NAME}")


    # embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")
    # logger.info("Embedding model loaded successfully.")
    embedding_model = None

except Exception as e:
    logger.error(f"CRITICAL INITIALIZATION FAILED: {e}", exc_info=True)
    llm_model = embedding_model = engine = None
    generic_model = None # NEW: در صورت خطا، این را نیز None قرار دهید

def _sync_get_conversation(user_id: int = None, anonymous_user_id: str = None) -> dict:
    """
    (نسخه اصلاح شده)
    چت را بر اساس کاربر لاگین شده (user_id) یا کاربر ناشناس (anonymous_user_id) دریافت می‌کند.
    اگر چتی وجود نداشت، آن را "با همان شناسه" می‌سازد.
    """
    if not engine:
        return {"conversation_history": [], "career_profile": None, "id": None}
        
    with engine.connect() as conn:
        query = None
        params = {}
        
        # --- (اصلاح شد) منطق جستجو ---
        if user_id:
            query = text("SELECT id, conversation_history, career_profile FROM public.conversations WHERE user_id = :uid ORDER BY updated_at DESC LIMIT 1")
            params = {"uid": user_id}
        elif anonymous_user_id:
            query = text("SELECT id, conversation_history, career_profile FROM public.conversations WHERE anonymous_user_id = :aid ORDER BY updated_at DESC LIMIT 1")
            params = {"aid": anonymous_user_id}
        else:
            # این حالت نباید رخ دهد (چون /chat همیشه یک شناسه می‌سازد)
            logger.warning("get_conversation called with no IDs. This shouldn't happen.")
            return {"conversation_history": [], "career_profile": None, "id": None}

        result = conn.execute(query, params).mappings().first()
        
        if result:
            # اگر چت پیدا شد، آن را برگردان
            return dict(result)
        
        # --- (اصلاح شد) منطق ساخت چت ---
        # اگر چت پیدا نشد، "با همان شناسه" یکی بساز
        
        if user_id:
            logger.info(f"No conversation found for user_id {user_id}. Creating new.")
            stmt = text("INSERT INTO public.conversations (user_id, conversation_history) VALUES (:uid, '[]'::jsonb) RETURNING id")
            result = conn.execute(stmt, {"uid": user_id}).mappings().first()
            conn.commit()
            return {"id": result['id'], "conversation_history": [], "career_profile": None}
        
        elif anonymous_user_id:
            # (این باگ اصلی بود) حالا چت را با همان anonymous_id می‌سازیم
            logger.info(f"No conversation found for anonymous_id {anonymous_user_id}. Creating new.")
            stmt = text("INSERT INTO public.conversations (anonymous_user_id, conversation_history) VALUES (:aid, '[]'::jsonb) RETURNING id")
            result = conn.execute(stmt, {"aid": anonymous_user_id}).mappings().first()
            conn.commit()
            # (مهم) حالا شناسه را هم برگردان
            return {"id": result['id'], "conversation_history": [], "career_profile": None, "anonymous_user_id": anonymous_user_id}

        return {"conversation_history": [], "career_profile": None, "id": None}

async def get_conversation(user_id: int = None, anonymous_user_id: str = None) -> dict:
    if not engine: return {}
    return await asyncio.to_thread(_sync_get_conversation, user_id, anonymous_user_id)

def _sync_save_conversation(conversation_id: int, history: list):
    """ چت را بر اساس ID یکتای چت (conversation_id) ذخیره می‌کند """
    if not conversation_id:
        logger.error("Attempted to save conversation with no conversation_id.")
        return
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE public.conversations SET conversation_history = :hist, updated_at = NOW() WHERE id = :cid"),
            {"hist": json.dumps(history, ensure_ascii=False), "cid": conversation_id}
        )
        conn.commit()

async def save_conversation(conversation_id: int, history: list):
    if not engine: return
    await asyncio.to_thread(_sync_save_conversation, conversation_id, history)

def _sync_save_full_profile(user_id: int, **kwargs):
    update_data = {"uid": user_id}
    set_clauses = []
    for key, value in kwargs.items():
        if value is None: continue
        if key in ["career_profile", "evidence", "riasec_scores", "work_values_scores", "work_styles_scores"]:
            param_key = f"json_{key}"
            update_data[param_key] = json.dumps(value, ensure_ascii=False)
            set_clauses.append(f"{key} = :{param_key}")
        else:
            param_key = f"param_{key}"
            update_data[param_key] = value
            set_clauses.append(f"{key} = :{param_key}")
            
    if not set_clauses: return
    
    # NEW: اطمینان از آپدیت شدن updated_at
    set_clauses.append("updated_at = NOW()")
    
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
            # ابتدا بررسی کنیم که آیا shared_chat وجود دارد یا نه
            shared_chat_stmt = text("""
                SELECT original_user_id, created_at, view_count, conversation_data, career_profile
                FROM public.shared_chats 
                WHERE share_id = :share_id
            """)
            
            shared_result = conn.execute(shared_chat_stmt, {"share_id": share_id}).mappings().first()
            
            if not shared_result:
                logger.warning(f"Shared chat with share_id {share_id} not found")
                return None
            
            # بروزرسانی view_count
            conn.execute(text("""
                UPDATE public.shared_chats 
                SET view_count = view_count + 1, last_viewed_at = NOW()
                WHERE share_id = :share_id
            """), {"share_id": share_id})
            
            # دریافت conversation_data و career_profile از shared_chats
            conversation_data = shared_result["conversation_data"]
            career_profile = shared_result["career_profile"]
            
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
            # NEW: بررسی کنید که آیا model None است یا خیر
            if model is None:
                raise RuntimeError("LLM model (generic_model or llm_model) is not initialized.")
            return await asyncio.to_thread(lambda: model.generate_content(
                contents,
                request_options={'timeout': 30} # <--- اضافه کردن مهلت ۳۰ ثانیه‌ای
            ))
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

def llm_generate_with_retry_sync(model, contents, tries=3, backoff=1.5):
    """Synchronous version of the LLM retry helper."""
    last_err = None
    for i in range(tries):
        try:
            if model is None:
                raise RuntimeError("LLM model (generic_model or llm_model) is not initialized.")
            # Direct synchronous call
            return model.generate_content(
                contents,
                request_options={'timeout': 30} # <--- اضافه کردن مهلت ۳۰ ثانیه‌ای
            )
        except Exception as e:
            last_err = e
            error_msg = str(e)
            
            if "429" in error_msg or "quota" in error_msg.lower() or "exceeded" in error_msg.lower():
                logger.warning(f"API quota exceeded (sync). Stopping retry attempts.")
                fallback_response = type('obj', (object,), {
                    'text': "متاسفانه در حال حاضر به دلیل محدودیت استفاده روزانه، سرویس هوش مصنوعی در دسترس نیست. لطفاً فردا دوباره تلاش کنید یا پلن API خود را ارتقا دهید."
                })
                return fallback_response
            
            logger.warning(f"LLM call failed (sync attempt {i+1}/{tries}): {e}")
            # Use time.sleep instead of asyncio.sleep
            time.sleep(backoff * (i + 1))
    
    # If all attempts fail
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

async def generate_final_report_from_conversation(history: list) -> str:
    """
    تولید گزارش نهایی بر اساس گفتگو بدون استفاده از دیتابیس مشاغل
    """
    if not llm_model:
        return "متاسفانه سرویس هوش مصنوعی در دسترس نیست."
    
    try:
        # تبدیل تاریخچه به فرمت مناسب برای LLM
        history_gemini_fmt = sanitize_history(history)
        
        # پرامپت برای تولید گزارش نهایی
        report_prompt = """
بر اساس گفتگوی انجام شده با کاربر، یک گزارش کامل مشاوره شغلی تولید کن که شامل موارد زیر باشد:

۱. تحلیل شخصیت شغلی: بر اساس تمام پاسخ‌های کاربر، ویژگی‌های اصلی شخصیت شغلی او را خلاصه کن.

۲. پیشنهاد مشاغل: ۳ تا ۵ شغل مناسب پیشنهاد بده و برای هر کدام توضیح بده که چرا با شخصیت کاربر سازگار است.

۳. مشاغل نامناسب: ۲ تا ۳ شغل که کمتر مناسب است را معرفی کن و دلیل عدم تناسب را توضیح بده.

۴. تحلیل شغل فعلی: اگر کاربر شغل فعلی دارد، آن را تحلیل کن و بگو از چه نظرهایی مناسب است و از چه نظرهایی نیست.

۵. گام بعدی: راهنمایی کن که چگونه می‌تواند در مورد مشاغل پیشنهادی تحقیق کند.

لطفاً گزارش را با لحنی صمیمی و دوم شخص مفرد و افعال شکسته بنویس.

تاریخچه گفتگو:
{conversation_history}
""".format(conversation_history=json.dumps(history_gemini_fmt, ensure_ascii=False, indent=2))
        
        response = await llm_generate_with_retry(llm_model, report_prompt)
        return (response.text or "گزارشی تولید نشد.").strip()
        
    except Exception as e:
        logger.error(f"Error in generate_final_report_from_conversation: {e}", exc_info=True)
        return "متاسفانه در تولید گزارش نهایی خطایی رخ داد."


# ==============================================================================
# 8) Web Server Logic (Flask)
# ==============================================================================
app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))  # کلید مخفی برای session ها

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/bot_avatar.png')
def serve_bot_avatar():
    """
    این route جدید، فایل عکس آواتار ربات را سرو می‌کند.
    """
    return send_from_directory('.', 'bot_avatar.png', mimetype='image/png')

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
    """ایجاد لینک اشتراک‌گذاری برای چت (نسخه 2 - سازگار با لاگین)"""
    try:
        data = request.json
        conversation = data.get('conversation', [])
        career_profile = data.get('career_profile')
        
        identifier_to_save = None
        
        # ۱. تلاش برای خواندن کاربر لاگین شده از توکن
        token_header = request.headers.get('Authorization')
        if token_header:
            try:
                token = token_header.split(" ")[1]
                payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
                # ستون original_user_id در shared_chats از نوع VARCHAR است
                # پس user_id عددی را به رشته تبدیل می‌کنیم
                identifier_to_save = str(payload['user_id'])
                logger.info(f"Share request from logged-in user: {identifier_to_save}")
            except Exception as e:
                logger.warning(f"Invalid token in /share-chat, falling back to anonymous: {e}")
        
        # ۲. اگر توکن نبود، از شناسه کاربر مهمان استفاده کن
        if not identifier_to_save:
            identifier_to_save = data.get('anonymous_user_id')
            if identifier_to_save:
                logger.info(f"Share request from anonymous user: {identifier_to_save}")

        
        if not identifier_to_save or not conversation:
            return jsonify({'error': 'شناسه کاربر و مکالمه الزامی است'}), 400
        
        # ۳. ایجاد لینک
        share_id = _sync_create_shared_chat(identifier_to_save, conversation, career_profile)
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
    """دریافت لیست چت‌ها با pagination (نسخه 2 - سازگار با لاگین)"""
    try:
        offset = request.args.get('offset', 0, type=int)
        limit = request.args.get('limit', 50, type=int)
        
        with engine.connect() as conn:
            total_count = conn.execute(text("SELECT COUNT(*) FROM public.conversations")).scalar_one()
            
            all_chats = conn.execute(text("""
                SELECT 
                    c.id as conversation_id,
                    c.user_id,
                    c.anonymous_user_id,
                    c.created_at,
                    c.updated_at,
                    c.report_generated,
                    c.career_profile,
                    u.phone_number,
                    u.first_name
                FROM public.conversations c
                LEFT JOIN public.users u ON c.user_id = u.id
                ORDER BY c.updated_at DESC 
                LIMIT :limit OFFSET :offset
            """), {"limit": limit, "offset": offset}).mappings().all()
            
            chats_list = []
            for row in all_chats:
                # پردازش career_profile
                career_profile = row['career_profile']
                if isinstance(career_profile, str):
                    try: career_profile = json.loads(career_profile)
                    except json.JSONDecodeError: career_profile = None
                
                chat_data = {
                    'conversation_id': row['conversation_id'],
                    'user_id': row['user_id'],
                    'anonymous_user_id': row['anonymous_user_id'],
                    'identifier': row['phone_number'] if row['phone_number'] else (row['anonymous_user_id'] or 'N/A'),
                    'first_name': row['first_name'] or ('مهمان' if row['anonymous_user_id'] else 'N/A'),
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
                    'report_generated': row['report_generated'].isoformat() if row['report_generated'] else None,
                    'career_profile': career_profile,
                    # اطلاعات اشتراک‌گذاری به دلیل تغییر ساختار حذف شد
                }
                chats_list.append(chat_data)
            
            return jsonify({
                'all_chats': chats_list,
                'total_count': total_count
            })
            
    except Exception as e:
        logger.error(f"Error getting all chats: {e}", exc_info=True)
        return jsonify({'error': 'خطا در دریافت لیست چت‌ها'}), 500

@app.route('/admin/check-auth')
@require_admin_auth
def admin_check_auth():
    """بررسی احراز هویت ادمین"""
    return jsonify({'authenticated': True}), 200

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
async def handle_web_message(user_message: str, conversation_history: list, user_id: int = None, anonymous_user_id: str = None, conversation_id: int = None, is_post_login_trigger: bool = False) -> dict:
    new_anonymous_user_id = None # برای برگرداندن شناسه جدید در صورت ساخته شدن
    # ۱. دریافت یا ساخت چت
    if not conversation_history or not conversation_id:
        convo_data = await get_conversation(user_id=user_id, anonymous_user_id=anonymous_user_id)
        history_gemini_fmt = sanitize_history(convo_data.get("conversation_history", []))
        conversation_id = convo_data.get("id")
        if 'anonymous_user_id' in convo_data:
            anonymous_user_id = convo_data['anonymous_user_id']
            new_anonymous_user_id = anonymous_user_id
    else:
        history_gemini_fmt = sanitize_history(conversation_history)

    if not conversation_id:
        logger.error("CRITICAL: Could not find or create conversation_id.")
        return {'reply_type': 'error', 'reply': "خطا در یافتن شناسه چت."}

    # --- (منطق اصلاح شده) ---

    # تابع کمکی برای بررسی آخرین پیام (پرامپت ۴.۳)
    def is_last_model_message_confirmation(history):
        """بررسی کند آخرین پیام مدل خلاصه تاییدی (۴.۳) است یا نه."""
        if not history:
            return False
        last_bot = None
        for m in reversed(history):
            if m.get('role') == 'model':
                last_bot = m
                break
        if not last_bot:
            return False
        last_text = "".join(last_bot['parts']).strip() if isinstance(last_bot['parts'], list) else str(last_bot.get('parts'))
        # دقیق‌تر: شامل کلیدواژه تایید و تحلیل باشد
        TRIGGER_PHRASES = ["تصویر درستی ازت پیدا کردم","آیا این تصویر رو تایید می‌کنی","بر اساس حرف‌هات، من آدمی رو می‌بینم که"]
        return any(phrase in last_text for phrase in TRIGGER_PHRASES)

    # ۱. بررسی اینکه آیا کاربر *همین الان* در حال پاسخ به خلاصه تایید است؟
    is_replying_to_summary = is_last_model_message_confirmation(history_gemini_fmt)
    is_logged_in = (user_id is not None)

    # ۲. (حالت گیت لاگین) کاربر به خلاصه پاسخ داد، اما لاگین نیست
    if is_replying_to_summary and not is_logged_in:
        logger.info(f"Login required for anonymous user {anonymous_user_id}. User is confirming summary.")
        
        # (اصلاح قبلی) تاریخچه جدید را *با* پیام کاربر بساز
        updated_db_history = history_gemini_fmt + [{"role": "user", "parts": [user_message]}]
        # این تاریخچه را *همین الان* در دیتابیس ذخیره کن
        await save_conversation(conversation_id, updated_db_history)

        return {
            'reply_type': 'login_required',
            'login_gate': True,
            'reply': "خیلی هم عالی! تحلیلت رو تایید کردی. 🚀\n\n**برای مشاهده پیشنهادهای شغلی و تحلیل نهایی، لطفاً وارد شو یا ثبت‌نام کن.**",
            'conversation_history': updated_db_history, # <-- تاریخچه *آپدیت شده* را برگردان
            'conversation_id': conversation_id,
            'anonymous_user_id': anonymous_user_id,
            'new_anonymous_user_id': new_anonymous_user_id
        }

    # ۳. (حالت ادامه پس از لاگین) کاربر به خلاصه پاسخ داد (یا پیام ذخیره شده‌اش رسید) و لاگین است
    if is_replying_to_summary and is_logged_in:
        logger.info("User has confirmed summary and is logged in. Getting job suggestions.")
        
        # --- FIX (حل مشکل توقف/Stall) ---
        # تاریخچه (history_gemini_fmt) شامل پیام خلاصه ربات است.
        # ما باید پیام کاربر (user_message) را به آن اضافه کنیم تا برای LLM ارسال شود.
        contents = history_gemini_fmt + [{"role": "user", "parts": [user_message]}]
        # --- End FIX ---

        # و به LLM می‌فرستیم تا پیشنهادات شغلی (پرامپت ۴.۴) را بگیرد
        try:
            response_job = await llm_generate_with_retry(llm_model, contents)
            job_response_text = (response_job.text or "نتوانستم پیشنهادات را تولید کنم").strip()
        except Exception as e:
            logger.error(f"LLM error after summary confirm: {e}", exc_info=True)
            return {'reply_type': 'error', 'reply': 'خطا در تولید پیشنهادهای شغلی.'}
        
        # --- [تغییر ۳] اعطای 4 اعتبار پیام رایگان پس از تحویل گزارش ---
        # (این کار فقط یک بار انجام می‌شود، زمانی که اعتبار 1- است)
        try:
            with engine.connect() as conn:
                conn.execute(
                    text("""
                        UPDATE public.user_credits 
                        SET message_credits = 4
                        WHERE user_id = :uid AND message_credits = -1
                    """),
                    {"uid": user_id}
                )
                conn.commit()
                logger.info(f"Granted 4 follow-up message credits to user {user_id} (from -1 to 4).")
        except Exception as e:
            logger.error(f"Failed to grant follow-up credits to user {user_id}: {e}", exc_info=True)
        # --- [پایان تغییر ۳] ---

        # --- (اصلاح شده برای مشکل 1) ---
        # اگر این یک تریگر مخفی پس از لاگین است، پیام "ادامه بده" را در تاریخچه ذخیره نکن.
        if is_post_login_trigger:
            updated_db_history = history_gemini_fmt + [{"role": "model", "parts": [job_response_text]}]
            logger.info("Post-login trigger. Hiding user's 'continue' message from history.")
        else:
            updated_db_history = contents + [{"role": "model", "parts": [job_response_text]}]
        # --- پایان اصلاح ---

        await save_conversation(conversation_id, updated_db_history)
        return {
            'reply_type': 'standard',
            'reply': job_response_text,
            'conversation_history': updated_db_history,
            'conversation_id': conversation_id,
            'anonymous_user_id': anonymous_user_id,
            **({'new_anonymous_user_id': new_anonymous_user_id} if new_anonymous_user_id else {})
        }
        
    # ۴. (حالت مکالمه عادی)
    try:
        response = await llm_generate_with_retry(llm_model, history_gemini_fmt + [{"role": "user", "parts": [user_message]}])
        bot_response_text = (response.text or "متوجه نشدم؛ می‌تونی کمی روشن‌تر توضیح بدی؟").strip()
    except Exception as e:
        logger.error(f"LLM Error in handle_web_message: {e}", exc_info=True)
        return {'reply_type': 'error', 'reply': 'خطا در ارتباط با سرویس هوش مصنوعی.'}
    
    # --- (اصلاح شده برای مشکل 1) ---
    if is_post_login_trigger:
        updated_db_history = history_gemini_fmt + [{"role": "model", "parts": [bot_response_text]}]
        logger.info("Post-login trigger (normal chat). Hiding user's 'continue' message from history.")
    else:
        updated_db_history = history_gemini_fmt + [{"role": "user", "parts": [user_message]}] + [{"role": "model", "parts": [bot_response_text]}]
    # --- پایان اصلاح ---

    await save_conversation(conversation_id, updated_db_history)
    
    return_data = {
        'reply_type': 'standard',
        'reply': bot_response_text,
        'conversation_history': updated_db_history,
        'conversation_id': conversation_id,
        'anonymous_user_id': anonymous_user_id
    }
    if new_anonymous_user_id:
        return_data['new_anonymous_user_id'] = new_anonymous_user_id
    return return_data

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'Message is required'}), 400

    # --- منطق جدید احراز هویت ---
    user_id = None
    anonymous_user_id = data.get('anonymous_user_id') # شناسه کاربر مهمان
    conversation_history = data.get('conversation', []) # تاریخچه چت فعلی
    
    token = None
    if 'Authorization' in request.headers:
        try:
            token = request.headers['Authorization'].split(" ")[1]
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
            user_id = payload['user_id']
            # اگر کاربر لاگین کرده، دیگر شناسه ناشناس مهم نیست
            anonymous_user_id = None 
            logger.info(f"Chat request from logged-in user: {user_id}")

            # --- [جدید] منطق بررسی اعتبار برای کاربران لاگین شده ---
            try:
                with engine.connect() as conn:
                    credits_data = conn.execute(
                        text("""
                            SELECT message_credits, subscription_expires_at 
                            FROM public.user_credits 
                            WHERE user_id = :uid
                        """),
                        {"uid": user_id}
                    ).mappings().first()

                    if not credits_data:
                        # اگر کاربر لاگین کرده ولی ردیف اعتبار ندارد (نباید اتفاق بیفتد)
                        logger.error(f"No credits entry found for logged-in user {user_id}. Granting 4 fallback credits.")
                        conn.execute(
                            text("INSERT INTO public.user_credits (user_id, message_credits) VALUES (:uid, 4) ON CONFLICT (user_id) DO NOTHING"),
                            {"uid": user_id}
                        )
                        conn.commit()
                        credits_data = {'message_credits': 4, 'subscription_expires_at': None}

                    # بررسی اشتراک نامحدود
                    is_subscribed = credits_data.get('subscription_expires_at') and credits_data['subscription_expires_at'] > datetime.now(timezone.utc)

                    current_credits = credits_data.get('message_credits', 0)
                    is_pre_report_user = (current_credits == -1) # آیا کاربر هنوز گزارش نگرفته؟
                    has_message_credits = (current_credits > 0)  # آیا اعتبار پولی یا رایگان (بیش از صفر) دارد؟

                    if not is_subscribed and not has_message_credits and not is_pre_report_user:
                        # --- [جدید] مسدود کردن کاربر به دلیل اتمام اعتبار ---
                        # (این کد فقط کاربرانی که اعتبار 0 دارند را مسدود می‌کند)
                        logger.info(f"User {user_id} has 0 credits and is not pre-report. Blocking chat.")
                        return jsonify({'reply_type': 'credit_limit_reached'}), 200
            
            except Exception as e:
                logger.error(f"Error checking credits for user {user_id}: {e}", exc_info=True)
                return jsonify({'reply': 'خطا در بررسی اعتبار شما.'}), 500
            # --- پایان منطق بررسی اعتبار ---

        except jwt.ExpiredSignatureError:
            return jsonify({'reply_type': 'error', 'reply': 'Token منقضی شده. لطفاً دوباره لاگین کنید.', 'token_expired': True}), 401
        except Exception as e:
            logger.error(f"Invalid token: {e}")
            # با توکن نامعتبر ادامه نده
            return jsonify({'reply_type': 'error', 'reply': 'Token نامعتبر است.'}), 401
    
    if not user_id and not anonymous_user_id:
        # اگر نه لاگین بود و نه شناسه ناشناس داشت، یک شناسه جدید می‌سازیم
        anonymous_user_id = "web_user_" + str(uuid.uuid4())
        logger.info(f"Chat request from new anonymous user: {anonymous_user_id}")
    elif not user_id:
        logger.info(f"Chat request from anonymous user: {anonymous_user_id}")
    # --- پایان منطق جدید ---

    if not llm_model:
        return jsonify({'reply': 'متاسفانه سرویس هوش مصنوعی در حال حاضر در دسترس نیست.'}), 503

    try:
        # (جدید) conversation_id را از کلاینت بخوان
        conversation_id = data.get('conversation_id') 

        # --- (اصلاح شده برای مشکل 1) ---
        # پرچم مخفی را بخوان که آیا این پیام "ادامه بده" است یا نه
        is_post_login_trigger = data.get('is_post_login_trigger', False)

        # آبجکت request را برای تابع handle_web_message ارسال می‌کنیم
        response_data = asyncio.run(handle_web_message(
            user_message=user_message,
            conversation_history=conversation_history, # تاریخچه چت از فرانت
            user_id=user_id, # ID عددی کاربر لاگین شده
            anonymous_user_id=anonymous_user_id, # ID متنی کاربر مهمان
            conversation_id=conversation_id, # <<< (این خط اضافه شد)
            is_post_login_trigger=is_post_login_trigger
        ))
        
        # اگر شناسه ناشناس جدیدی ساخته شده، آن را برگردان
        if 'new_anonymous_user_id' in response_data:
            anonymous_user_id = response_data['new_anonymous_user_id']

        # --- [جدید] کسر اعتبار پس از پاسخ موفق ---
        # (فقط اگر کاربر لاگین بود و خطایی رخ نداده بود)
        if user_id and response_data.get('reply_type', 'standard') == 'standard':
            with engine.connect() as conn:
                # چک کن آیا اشتراک نامحدود دارد یا نه
                is_subscribed = conn.execute(
                    text("SELECT 1 FROM public.user_credits WHERE user_id = :uid AND subscription_expires_at > NOW()"),
                    {"uid": user_id}
                ).scalar_one_or_none()
                
                if not is_subscribed:
                    # اگر اشتراک نداشت، یک اعتبار کم کن
                    conn.execute(
                        text("UPDATE public.user_credits SET message_credits = message_credits - 1 WHERE user_id = :uid AND message_credits > 0"),
                        {"uid": user_id}
                    )
                    conn.commit()
                    logger.info(f"Deducted 1 message credit from user {user_id}")
        # --- پایان بخش کسر اعتبار ---

        return jsonify({**response_data, 'anonymous_user_id': anonymous_user_id})
    
    # --- 🔽 این بخش را اضافه کنید 🔽 ---
    except Exception as e:
        error_msg = str(e)
        # لاگ کردن خطا (توجه: web_user_id دیگر در اینجا تعریف نشده، پس لاگ را اصلاح می‌کنیم)
        log_user_id = user_id if user_id else anonymous_user_id
        logger.error(f"Error in /chat endpoint for user {log_user_id}: {e}", exc_info=True)
        
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
    # --- 🔼 پایان بخش اضافه شده 🔼 ---

        return jsonify({**response_data, 'anonymous_user_id': anonymous_user_id})

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

def _helper_generate_persona_intro(instructions: str = None) -> dict:
    """
    (جدید) تابع کمکی: با استفاده از LLM یک پرسونا و پیام معرفی تولید می‌کند.
    """
    logger.info(f"Generating new persona. Instructions: {instructions}")

    if instructions:
        # حالت "هدایت شده" (Guided Mode)
        prompt = f"""
        شما یک شبیه‌ساز شخصیت بسیار خلاق برای تست یک ربات مشاور شغلی هستید.
        من به شما دستورالعملی می‌دهم و شما باید بر اساس آن، یک شخصیت کامل خلق کنید.

        # دستورالعمل:
        "{instructions}"

        # وظیفه:
        1.  یک پاراگراف کوتاه به عنوان "جزئیات پرسونا" (persona_details) بنویسید که شامل سن، شغل، تحصیلات، علایق، و چالش‌های کلیدی این فرد باشد.
        2.  یک "پیام معرفی" (intro_message) بنویسید که این فرد در اولین پیام خود به مشاور شغلی ارسال می‌کند.

        # خروجی:
        خروجی باید *فقط و فقط* یک آبجکت JSON خام با دو کلید "persona_details" و "intro_message" باشد.
        """
    else:
        # حالت "تصادفی" (Random Mode)
        prompt = f"""
        شما یک شبیه‌ساز شخصیت بسیار خلاق برای تست یک ربات مشاور شغلی هستید.
        یک شخصیت کاملاً تصادفی، جالب و منحصر به فرد خلق کنید.

        # وظیفه:
        1.  یک پاراگراف کوتاه به عنوان "جزئیات پرسونا" (persona_details) بنویسید که شامل سن، شغل (یا دانشجو)، سطح تحصیلات، علایق، و یک چالش شغلی برای او باشد. (مثلاً: "مرد، 45 ساله، مدیر مالی، از کارش خسته شده و دنبال کاری با معنای اجتماعی می‌گردد")
        2.  یک "پیام معرفی" (intro_message) بنویسید که این فرد در اولین پیام خود به مشاور شغلی ارسال می‌کند.

        # خروجی:
        خروجی باید *فقط و فقط* یک آبجکت JSON خام با دو کلید "persona_details" و "intro_message" باشد.
        """

    try:
        # FIX: از 'generic_model' استفاده کنید
        # <<<<<<<<<<<<<<< این خط تغییر کرده است >>>>>>>>>>>>>>>
        response = llm_generate_with_retry_sync(generic_model, prompt)
        # تمیز کردن خروجی JSON از بلاک‌های کد
        clean_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)

        if "persona_details" in data and "intro_message" in data:
            logger.info(f"Persona generated: {data['persona_details']}")
            return data
        raise ValueError("Missing keys in persona JSON")

    except Exception as e:
        logger.error(f"Failed to generate persona: {e}")
        # بازگشت یک پرسونا جایگزین در صورت خطا
        return {
            "persona_details": "شخصیت جایگزین (خطا در تولید): سارا، 28 ساله، گرافیست. از کار روتین خسته شده و دنبال خلاقیت بیشتر است.",
            "intro_message": "سلام. من سارا هستم، 28 سالمه و گرافیستم. حس می‌کنم کارم خیلی تکراری شده و نمی‌دونم باید چیکار کنم."
        }

def _helper_get_persona_response(persona_details: str, chat_history_str: str, counselor_question: str) -> str:
    """
    (جدید) تابع کمکی: به عنوان پرسونا، به سوال مشاور پاسخ می‌دهد.
    """
    logger.info(f"Persona is thinking about: {counselor_question}")
    prompt = f"""
    # نقش شما
    شما در حال ایفای نقش هستید. شما *نباید* مانند یک هوش مصنوعی پاسخ دهید.

    # شخصیت شما (نقش):
    {persona_details}

    # تاریخچه چت تاکنون:
    {chat_history_str}

    # سوال مشاور از شما:
    "{counselor_question}"

    # وظیفه:
    فقط و فقط به عنوان «شخصیت» خودتان، یک پاسخ طبیعی، انسانی و کوتاه به این سوال بدهید.
    """

    try:
        # FIX: از 'generic_model' استفاده کنید
        # <<<<<<<<<<<<<<< این خط تغییر کرده است >>>>>>>>>>>>>>>
        response = llm_generate_with_retry_sync(generic_model, prompt)
        return (response.text or "نمیدونم چی بگم.").strip().replace("*", "") # حذف کاراکترهای مارک‌داون
    except Exception as e:
        logger.error(f"Failed to get persona response: {e}")
        return "راستش نمیدونم در موردش چی فکر می‌کنم."

@app.route('/admin/advanced-test', methods=['POST'])
@require_admin_auth
def admin_advanced_test():
    """
    (ارتقا یافته) تست خودکار پیشرفته با شبیه‌سازی پرسونا
    این نسخه برای سیستم Generative جدید (بدون سیگنال) آپدیت شده است.
    """
    try:
        # 1. دریافت حالت تست (بدون تغییر)
        data = request.json
        mode = data.get('mode', 'random') # 'random' or 'guided'
        instructions = data.get('instructions')
        
        if mode == 'guided' and not instructions:
            return jsonify({
                "success": False,
                "error": "برای حالت هدایت‌شده، ارسال دستورالعمل الزامی است."
            }), 400

        # ایجاد user_id منحصر به فرد برای این تست (بدون تغییر)
        test_user_id = f'sim_test_{int(datetime.now().timestamp())}'
        conversation_log = [] # لاگ کامل چت برای نمایش به ادمین
        
        logger.info(f"Starting NEW advanced test for user '{test_user_id}' in '{mode}' mode.")

        # 2. تولید پرسونا و پیام اول (بدون تغییر)
        # (این توابع کمکی _helper اکنون از generic_model استفاده می‌کنند و درست کار خواهند کرد)
        persona_data = _helper_generate_persona_intro(instructions)
        persona_details = persona_data["persona_details"]
        current_user_message = persona_data["intro_message"]

        human_readable_history = ""
        
        # 3. شروع حلقه شبیه‌سازی (تغییر یافته)
        # ما مکالمه را برای 12 نوبت (6 سوال مشاور و 6 پاسخ کاربر) اجرا می‌کنیم
        for i in range(16): 
            
            logger.info(f"Test Loop {i+1} - User '{test_user_id}': {current_user_message}")
            human_readable_history += f"\nکاربر: {current_user_message}\n"
            conversation_log.append({"role": "user", "message": current_user_message})
            
            # 4. ارسال پیام "کاربر شبیه‌سازی شده" به "مشاور" (بدون تغییر)
            db_user_id = _sync_get_or_create_user(test_user_id, "SimUser")
            convo_data = _sync_get_conversation(db_user_id)
            history_gemini_fmt = sanitize_history(convo_data.get("conversation_history", []))
            
            contents = history_gemini_fmt + [{"role": "user", "parts": [current_user_message]}]
            
            response = llm_generate_with_retry_sync(llm_model, contents)
            bot_response_text = (response.text or "متوجه نشدم.").strip()
            
            updated_db_history = contents + [{"role": "model", "parts": [bot_response_text]}]
            _sync_save_conversation(db_user_id, updated_db_history)
            
            # 5. لاگ کردن پاسخ "مشاور" (بدون تغییر)
            logger.info(f"Test Loop {i+1} - Counselor: {bot_response_text[:100]}...")
            human_readable_history += f"\nمشاور: {bot_response_text}\n"
            conversation_log.append({"role": "model", "message": bot_response_text})

            # 6. [بخش سیگنال حذف شد]
            # دیگر نیازی به چک کردن analysis_complete نیست
            
            # 7. اگر چت تمام نشده، از "شبیه‌ساز" بخواه پاسخ دهد (بدون تغییر)
            current_user_message = _helper_get_persona_response(
                persona_details,
                human_readable_history,
                bot_response_text # سوال مشاور
            )

        # 8. شبیه‌سازی تمام شد
        logger.info(f"Simulation finished after 12 turns for '{test_user_id}'.")
        
        # 9. [بخش تحلیل نهایی حذف شد]
        # دیگر تابع trigger_analysis_for_user را فراخوانی نمی‌کنیم
        
        # 10. برگرداندن نتیجه کامل به ادمین (تغییر یافته)
        return jsonify({
            "success": True,
            "persona_details": persona_details,
            "conversation": conversation_log,
            "final_report": "گزارش نهایی دیگر به صورت جداگانه وجود ندارد. لطفاً مکالمه را بررسی کنید، پیشنهادات شغلی باید در پیام‌های آخر مشاور باشند.",
            "career_profile": None, # دیگر پروفایل جداگانه نداریم
            "test_user_id": test_user_id
        }), 200

    except Exception as e:
        logger.error(f"Error in advanced-test: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "خطا در اجرای تست شبیه‌سازی"
        }), 500


# ==============================================================================
# 10) Authentication API Endpoints (OTP)
# ==============================================================================

def normalize_phone(phone: str) -> str | None:
    """شماره موبایل را نرمال‌سازی می‌کند (مثال: 09121234567)"""
    if not phone:
        return None
    # حذف همه چیز به جز اعداد
    phone_digits = re.sub(r'\D', '', phone)
    
    # اگر با +98 شروع شده، آن را با 0 جایگزین کن
    if phone_digits.startswith('98'):
        phone_digits = '0' + phone_digits[2:]
        
    # بررسی فرمت (مثلاً 09xxxxxxxxx)
    if re.match(r'^09\d{9}$', phone_digits):
        return phone_digits
    
    logger.warning(f"Invalid phone number format: {phone}")
    return None

@app.route('/api/send-otp', methods=['POST'])
def api_send_otp():
    """
    یک کد OTP به شماره موبایل کاربر ارسال می‌کند.
    """
    data = request.json
    phone_number_raw = data.get('phone_number')
    
    phone_number = normalize_phone(phone_number_raw)
    
    if not phone_number:
        return jsonify({'error': 'فرمت شماره موبایل اشتباه است. (مثال: 09121234567)'}), 400
        
    # --- (اصلاح شد) ---
    # بررسی صریح حالت تست
    # اگر kaveh_api None باشد یا کلید API برابر با TEST_MODE باشد
    is_test_mode = (not kaveh_api) or (KAVEHNEGAR_API_KEY == "TEST_MODE")
    
    if is_test_mode:
        logger.error("Kavenegar API is not configured or in TEST_MODE. Cannot send OTP.")
        logger.warning("!!! KAVEHNEGAR API NOT SET. USING TEST OTP: 123456 !!!")
        code = "123456" # <--- استفاده اجباری از کد تست
    else:
        # ارسال واقعی
        code = str(random.randint(100000, 999999))
        try:
            # الگو (template) خود در کاوه‌نگار را اینجا بگذارید
            response = kaveh_api.verify_lookup({'receptor': phone_number, 'token': code, 'template': 'verify-otp'})
            logger.info(f"OTP Sent. Receptor: {phone_number}, Response: {response}")
            
            # حالت شبیه‌سازی (برای تست بدون ارسال واقعی)
            #logger.info(f"!!! SIMULATING Kavehnegar Send. Phone: {phone_number}, Code: {code} !!!")
            
        except Exception as e:
            logger.error(f"Kavenegar API error: {e}")
            return jsonify({'error': 'خطا در ارسال پیامک. لطفاً دقایقی دیگر تلاش کنید.'}), 500

    # ذخیره کد در دیتابیس
    try:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        with engine.connect() as conn:
            # کدهای قبلی این شماره را پاک کن
            conn.execute(text("DELETE FROM public.otps WHERE phone_number = :phone"), {"phone": phone_number})
            # کد جدید را اضافه کن
            conn.execute(
                text("INSERT INTO public.otps (phone_number, code, expires_at) VALUES (:phone, :code, :exp)"),
                {"phone": phone_number, "code": code, "exp": expires_at}
            )
            conn.commit()
        
        return jsonify({'success': True, 'message': 'کد تایید ارسال شد.'})
        
    except Exception as e:
        logger.error(f"Error saving OTP to DB: {e}", exc_info=True)
        return jsonify({'error': 'خطای داخلی در ذخیره کد.'}), 500

@app.route('/api/verify-otp', methods=['POST'])
def api_verify_otp():
    """
    کد OTP را تایید می‌کند، کاربر را لاگین/ثبت‌نام می‌کند،
    چت‌های ناشناس را به او متصل می‌کند و توکن JWT برمی‌گرداند.
    """
    data = request.json
    phone_number_raw = data.get('phone_number')
    code = data.get('code')
    anonymous_user_id = data.get('anonymous_user_id') # شناسه چت مهمان

    phone_number = normalize_phone(phone_number_raw)

    if not phone_number or not code:
        return jsonify({'error': 'شماره موبایل و کد الزامی است.'}), 400

    try:
        with engine.connect() as conn:
            # ۱. بررسی کد OTP
            now = datetime.now(timezone.utc)
            otp_result = conn.execute(
                text("SELECT id FROM public.otps WHERE phone_number = :phone AND code = :code AND expires_at > :now"),
                {"phone": phone_number, "code": code, "now": now}
            ).mappings().first()
            
            # --- (اصلاح شد) ---
            # بررسی صریح حالت تست
            is_test_mode = (not kaveh_api) or (KAVEHNEGAR_API_KEY == "TEST_MODE")

            if not otp_result:
                # حالت تست: اجازه ورود با کد ۱۲۳۴۵۶ اگر کاوه‌نگار تنظیم نشده
                if is_test_mode and code == "123456":
                    logger.warning(f"Bypassing OTP check for {phone_number} with test code 123456")
                else:
                    return jsonify({'error': 'کد تایید اشتباه است یا منقضی شده.'}), 400
            
            # کد استفاده شد، آن را پاک کن
            conn.execute(text("DELETE FROM public.otps WHERE phone_number = :phone"), {"phone": phone_number})
            
            # ۲. پیدا کردن یا ساختن کاربر
            user_id = conn.execute(
                text("SELECT id FROM public.users WHERE phone_number = :phone"),
                {"phone": phone_number}
            ).scalar_one_or_none()
            
            referral_code = data.get('referral_code') # خواندن کد معرف از درخواست

            if not user_id:
                # --- ثبت نام کاربر جدید ---
                user_id = conn.execute(
                    text("INSERT INTO public.users (phone_number) VALUES (:phone) RETURNING id"),
                    {"phone": phone_number}
                ).scalar_one()
                logger.info(f"New user created. Phone: {phone_number}, UserID: {user_id}")

                # --- [جدید] اعطای 4 اعتبار پیام رایگان به کاربر جدید ---
                conn.execute(
                    # [تغییر ۱] اعتبار اولیه از 4 به -1 تغییر کرد
                    text("INSERT INTO public.user_credits (user_id, message_credits) VALUES (:uid, -1)"),
                    {"uid": user_id}
                )
                logger.info(f"Granted -1 (pre-report) credits to new user {user_id}")

                # --- [جدید] بررسی و اعمال کد معرف ---
                if referral_code:
                    # 1. کد معرف را پیدا کن (کدی که استفاده نشده باشد)
                    referral_entry = conn.execute(
                        text("SELECT id, referrer_user_id FROM public.referrals WHERE referral_code = :code AND referred_user_id IS NULL"),
                        {"code": referral_code}
                    ).mappings().first()
                    
                    if referral_entry:
                        referrer_id = referral_entry['referrer_user_id']
                        # 2. کد را به نام کاربر جدید ثبت کن (تا دوباره استفاده نشود)
                        conn.execute(
                            text("UPDATE public.referrals SET referred_user_id = :new_user_id, credited_at = NOW() WHERE id = :ref_id"),
                            {"new_user_id": user_id, "ref_id": referral_entry['id']}
                        )
                        # 3. به صاحب کد (معرف) 20 اعتبار پاداش بده
                        conn.execute(
                            text("UPDATE public.user_credits SET message_credits = message_credits + 20 WHERE user_id = :referrer_id"),
                            {"referrer_id": referrer_id}
                        )
                        logger.info(f"Referral code {referral_code} applied. Granted 20 credits to referrer {referrer_id}.")
                    else:
                        logger.warning(f"Invalid or already used referral code {referral_code} attempted by new user {user_id}.")
                # --- پایان بخش کد معرف ---

            else:
                # --- کاربر لاگین کرد (ثبت نام جدید نبود) ---
                logger.info(f"User logged in. Phone: {phone_number}, UserID: {user_id}")
                # (اختیاری) مطمئن شو اگر قبلاً ردیف اعتبار نداشته، الان بگیرد
                conn.execute(
                    text("INSERT INTO public.user_credits (user_id, message_credits) VALUES (:uid, 0) ON CONFLICT (user_id) DO NOTHING"),
                    {"uid": user_id}
                )
            
            # ۳. (مهم) انتقال چت‌های ناشناس (منطق اصلاح شده برای مشکل 2)
            if anonymous_user_id:
                # --- (اصلاح شده) ---
                # ابتدا بررسی کن آیا این کاربر (user_id) از قبل چتی دارد یا نه
                existing_chat_id = conn.execute(
                    text("SELECT id FROM public.conversations WHERE user_id = :uid LIMIT 1"),
                    {"uid": user_id}
                ).scalar_one_or_none()

                if existing_chat_id:
                    # اگر کاربر از قبل چت دارد (یعنی فقط لاگین کرده):
                    # چت ناشناس جدید (مثلاً با یک "سلام") را نادیده بگیر و حذف کن.
                    logger.info(f"User {user_id} already has chat {existing_chat_id}. Discarding new anonymous chat {anonymous_user_id}.")
                    conn.execute(
                        text("DELETE FROM public.conversations WHERE anonymous_user_id = :aid"),
                        {"aid": anonymous_user_id}
                    )
                else:
                    # اگر کاربر از قبل چت ندارد (اولین بار است لاگین می‌کند):
                    # چت ناشناس را به او منتقل کن.
                    try:
                        conn.execute(
                            text("""
                                UPDATE public.conversations 
                                SET user_id = :uid, anonymous_user_id = NULL 
                                WHERE anonymous_user_id = :aid
                            """),
                            {"uid": user_id, "aid": anonymous_user_id}
                        )
                        logger.info(f"First-time login. Merged anonymous chat {anonymous_user_id} to new user {user_id}")
                    except IntegrityError:
                        logger.warning(f"Could not merge chat {anonymous_user_id}. IntegrityError.")
                        pass # ادامه می‌دهیم
                # --- پایان اصلاح ---
            
            # ۴. ساخت توکن JWT
            token_payload = {
                'user_id': user_id,
                'phone': phone_number,
                'exp': datetime.now(timezone.utc) + timedelta(days=30) # ۳۰ روز اعتبار
            }
            token = jwt.encode(token_payload, JWT_SECRET_KEY, algorithm="HS256")
            
            conn.commit()
            
            return jsonify({'success': True, 'token': token, 'user_id': user_id})

    except Exception as e:
        logger.error(f"Error in verify-otp: {e}", exc_info=True)
        return jsonify({'error': 'خطای داخلی سرور هنگام تایید.'}), 500

# دکوریتور برای چک کردن توکن (اختیاری ولی خوب است)
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            try:
                token = request.headers['Authorization'].split(" ")[1]
            except IndexError:
                return jsonify({'error': 'Token format is invalid'}), 401
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            data = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
            current_user_id = data['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except Exception as e:
            logger.error(f"Token decode error: {e}")
            return jsonify({'error': 'Token is invalid'}), 401
            
        return f(current_user_id, *args, **kwargs)
    return decorated

@app.route('/api/get-my-chats', methods=['GET'])
@token_required
def get_my_chats(current_user_id):
    """ یک اندپوینت امن که چت‌های کاربر لاگین شده را برمی‌گرداند """
    try:
        with engine.connect() as conn:
            chats = conn.execute(
                text("""
                    SELECT id, conversation_history, career_profile, updated_at 
                    FROM public.conversations 
                    WHERE user_id = :uid 
                    ORDER BY updated_at DESC
                """),
                {"uid": current_user_id}
            ).mappings().all()
            
            return jsonify([dict(chat) for chat in chats])
            
    except Exception as e:
        logger.error(f"Error getting chats for user {current_user_id}: {e}", exc_info=True)
        return jsonify({'error': 'خطا در دریافت چت‌ها'}), 500

@app.route('/admin/view-chat/<int:conversation_id>')
@require_admin_auth
def admin_view_chat(conversation_id):
    """صفحه مشاهده چت برای ادمین"""
    try:
        with engine.connect() as conn:
            # دریافت مکالمه و اطلاعات کاربر
            chat_data = conn.execute(text("""
                SELECT 
                    c.conversation_history,
                    u.phone_number,
                    c.anonymous_user_id
                FROM public.conversations c
                LEFT JOIN public.users u ON c.user_id = u.id
                WHERE c.id = :cid
            """), {"cid": conversation_id}).mappings().first()
            
            if not chat_data:
                return "چت یافت نشد.", 404
            
            history = chat_data['conversation_history']
            if isinstance(history, str):
                history = json.loads(history)
            
            identifier = chat_data['phone_number'] or chat_data['anonymous_user_id']

            return render_template_string(
                ADMIN_VIEW_CHAT_TEMPLATE,
                conversation_id=conversation_id,
                identifier=identifier,
                conversation_data=history
            )
    except Exception as e:
        logger.error(f"Error in admin_view_chat: {e}", exc_info=True)
        return "خطای سرور در بارگذاری چت", 500


# ==============================================================================
# 11) Credit & Payment API Endpoints
# ==============================================================================

@app.route('/api/get-referral-link', methods=['POST'])
@token_required
def get_referral_link(current_user_id):
    """
    لینک معرف منحصر به فرد کاربر را ایجاد یا بازیابی می‌کند.
    """
    try:
        with engine.connect() as conn:
            # 1. چک کن آیا کاربر از قبل کد فعال دارد
            code = conn.execute(
                text("SELECT referral_code FROM public.referrals WHERE referrer_user_id = :uid"),
                {"uid": current_user_id}
            ).scalar_one_or_none()
            
            if not code:
                # 2. اگر نداشت، یک کد جدید بساز
                code = str(uuid.uuid4()) # استفاده از uuid
                conn.execute(
                    text("INSERT INTO public.referrals (referrer_user_id, referral_code) VALUES (:uid, :code)"),
                    {"uid": current_user_id, "code": code}
                )
                conn.commit()
                logger.info(f"Generated new referral code for user {current_user_id}")
            
            # 3. لینک کامل را برگردان
            referral_link = f"{APP_BASE_URL}/?ref={code}"
            return jsonify({'success': True, 'referral_link': referral_link})
            
    except Exception as e:
        logger.error(f"Error getting referral link for user {current_user_id}: {e}", exc_info=True)
        return jsonify({'error': 'خطا در ساخت لینک معرف'}), 500

# --- [جدید] API برای اطلاع‌رسانی قیمت به فرانت‌اند ---
@app.route('/api/get-subscription-price', methods=['GET'])
@token_required
def get_subscription_price(current_user_id):
    """
    [اصلاح شده]
    بررسی می‌کند کاربر شامل تخفیف می‌شود یا نه.
    اگر تایمر تخفیف قبلاً شروع نشده، آن را همین لحظه شروع می‌کند.
    """
    try:
        with engine.connect() as conn:
            # [اصلاح شد] به جای جدول users، از user_credits بخوان
            timer_start_time = conn.execute(
                text("SELECT discount_timer_started_at FROM public.user_credits WHERE user_id = :uid"),
                {"uid": current_user_id}
            ).scalar_one_or_none()

            if not timer_start_time:
                # [جدید] اگر تایمر هرگز شروع نشده، همین الان آن را ست کن
                logger.info(f"Discount timer not set for user {current_user_id}. Starting it now.")
                timer_start_time = conn.execute(
                    text("""
                        UPDATE public.user_credits 
                        SET discount_timer_started_at = NOW() 
                        WHERE user_id = :uid
                        RETURNING discount_timer_started_at
                    """),
                    {"uid": current_user_id}
                ).scalar_one()
                conn.commit()

            # [اصلاح شد] مقایسه با زمان شروع تایمر (نه زمان ثبت نام)
            # (از utcnow() استفاده می‌کنیم چون ستون ما TIMESTAMPTZ است)
            time_since_start = datetime.now(timezone.utc) - timer_start_time

            # زمان تخفیf خود را اینجا تنظیم کنید (مثلاً 1 ساعت یا 1 روز)
            discount_duration = timedelta(minutes=DISCOUNT_DURATION_MINUTES) 

            if time_since_start < discount_duration:
                # --- شامل تخفیf می‌شود ---
                discount_ends_at = timer_start_time + discount_duration
                return jsonify({
                    "price": int(DISCOUNT_PRICE),
                    "original_price": int(SUBSCRIPTION_PRICE),
                    "is_discounted": True,
                    "discount_ends_at": discount_ends_at.isoformat()
                })
            else:
                # --- تخفیf تمام شده ---
                return jsonify({
                    "price": int(SUBSCRIPTION_PRICE),
                    "original_price": int(SUBSCRIPTION_PRICE),
                    "is_discounted": False
                })

    except Exception as e:
        logger.error(f"Error getting subscription price for user {current_user_id}: {e}", exc_info=True)
        return jsonify({'error': 'خطا در دریافت اطلاعات قیمت'}), 500

@app.route('/api/create-payment-request', methods=['POST'])
@token_required
def create_payment_request(current_user_id):
    """
    [اصلاح شده برای مدیریت صحیح اتصال]
    یک درخواست پرداخت در زرین‌پال ایجاد کرده و کاربر را به درگاه هدایت می‌کند.
    """
    payment_id = None
    final_amount = 0
    description = ""
    phone = f"user_{current_user_id}"

    try:
        # --- بلاک ۱: اتصال به دیتابیس برای محاسبه قیمت و ایجاد ردیف PENDING ---
        with engine.connect() as conn:
            # ۱. دریافت اطلاعات کاربر و محاسبه قیمت
            user_data = conn.execute(
                text("""
                    SELECT u.phone_number, c.discount_timer_started_at 
                    FROM public.users u
                    LEFT JOIN public.user_credits c ON u.id = c.user_id
                    WHERE u.id = :uid
                """),
                {"uid": current_user_id}
            ).mappings().first()

            if not user_data:
                 return jsonify({'error': 'کاربر یافت نشد'}), 404

            phone = user_data['phone_number'] or f"user_{current_user_id}"
            timer_start_time = user_data['discount_timer_started_at']

            is_discounted = False
            if timer_start_time:
                time_since_start = datetime.now(timezone.utc) - timer_start_time
                discount_duration = timedelta(minutes=DISCOUNT_DURATION_MINUTES)
                if time_since_start < discount_duration:
                    is_discounted = True
            
            # مقادیر را برای استفاده در خارج از with ذخیره کن
            final_amount = int(DISCOUNT_PRICE) if is_discounted else int(SUBSCRIPTION_PRICE)
            description = f"اشتراک ۱ روزه (تخفیف ویژه)" if is_discounted else f"اشتراک ۱ روزه"

            # ۲. ایجاد رکورد پرداخت PENDING
            temp_authority = str(uuid.uuid4())
            payment_record = conn.execute(
                text("""
                    INSERT INTO public.payments (user_id, amount, authority, status) 
                    VALUES (:uid, :amount, :auth, 'PENDING')
                    RETURNING id
                """),
                {"uid": current_user_id, "amount": final_amount, "auth": temp_authority}
            ).mappings().first()
            payment_id = payment_record['id']
            
            # ۳. اتصال را کامیت کن و ببند
            conn.commit()
            logger.info(f"DB: Created PENDING payment record {payment_id} for user {current_user_id}.")

        # --- بلاک ۲: تماس با زرین‌پال (خارج از اتصال دیتابیس) ---
        payload = {
            "merchant_id": ZARINPAL_MERCHANT_ID,
            "amount": final_amount * 10, # [اصلاح شد]
            "callback_url": PAYMENT_CALLBACK_URL,
            "description": f"{description} - {phone}",
            "metadata": {"user_id": current_user_id, "payment_id": payment_id}
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        logger.info(f"Calling Zarinpal API for payment {payment_id}...")
        response = requests.post(ZARINPAL_REQUEST_URL, data=json.dumps(payload), headers=headers, timeout=10)
        response.raise_for_status() # پرتاب خطا در صورت 4xx/5xx
        
        response_data = response.json()

        # --- بلاک ۳: اتصال مجدد به دیتابیس برای آپدیت رکورد ---
        if response_data.get("data", {}).get("code") == 100:
            # ۴. درخواست موفق بود
            zarinpal_authority = response_data['data']['authority']
            payment_url = f"{ZARINPAL_STARTPAY_URL}{zarinpal_authority}"
            
            # ۵. [اتصال مجدد] آپدیت رکورد با Authority واقعی
            with engine.connect() as conn:
                conn.execute(
                    text("UPDATE public.payments SET authority = :auth WHERE id = :pid"),
                    {"auth": zarinpal_authority, "pid": payment_id}
                )
                conn.commit()
            
            logger.info(f"Zarinpal request created for user {current_user_id}. Amount: {final_amount}, Authority: {zarinpal_authority}")
            return jsonify({'success': True, 'payment_url': payment_url})
        else:
            # زرین‌پال خطا برگرداند
            error_code = response_data.get("errors", {}).get("code", "unknown")
            error_message = response_data.get("errors", {}).get("message", "خطای نامشخص از زرین‌پال")
            logger.error(f"Zarinpal request error for user {current_user_id}. Code: {error_code}, Msg: {error_message}")
            
            # ۶. [اتصال مجدد] ردیف پرداخت PENDING را پاک کنید
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM public.payments WHERE id = :pid"), {"pid": payment_id})
                conn.commit()
            return jsonify({'error': f'خطای درگاه پرداخت: {error_message} (کد: {error_code})'}), 500

    except requests.exceptions.RequestException as e:
        logger.error(f"Zarinpal request failed: {e}", exc_info=True)
        # [اصلاح شد] اگر تماس با شبکه خطا داد، ردیف PENDING را پاک کن
        if payment_id:
            try:
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM public.payments WHERE id = :pid AND status = 'PENDING'"), {"pid": payment_id})
                    conn.commit()
                logger.info(f"Cleaned up PENDING payment {payment_id} after network error.")
            except Exception as db_e:
                logger.error(f"Failed to cleanup PENDING payment {payment_id}: {db_e}")
        return jsonify({'error': 'خطا در ارتباط با درگاه پرداخت.'}), 500
    
    except Exception as e:
        logger.error(f"Error creating payment request for user {current_user_id}: {e}", exc_info=True)
        # پاک کردن ردیف در صورت بروز هر خطای دیگری
        if payment_id:
            try:
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM public.payments WHERE id = :pid AND status = 'PENDING'"), {"pid": payment_id})
                    conn.commit()
                logger.info(f"Cleaned up PENDING payment {payment_id} after general error.")
            except Exception as db_e:
                logger.error(f"Failed to cleanup PENDING payment {payment_id}: {db_e}")
        return jsonify({'error': 'خطای داخلی سرور در ایجاد پرداخت'}), 500

@app.route('/payment/verify', methods=['GET'])
def verify_payment():
    """
    این اندپوینت Callback زرین‌پال است.
    پرداخت را تایید نهایی (Verify) کرده و اشتراک را فعال می‌کند.
    """
    authority = request.args.get('Authority')
    status = request.args.get('Status')
    
    # URL هایی که کاربر به آن‌ها هدایت می‌شود. شما باید این صفحات را در فرانت بسازید.
    # فعلاً آن‌ها را به صفحه اصلی هدایت می‌کنیم با یک پارامتر
    success_url = f"{APP_BASE_URL}/?payment=success"
    failed_url = f"{APP_BASE_URL}/?payment=failed"

    if not authority or not status:
        logger.warning("Invalid payment callback. Missing Authority or Status.")
        return redirect(failed_url)

    try:
        with engine.connect() as conn:
            # 1. رکورد پرداخت را بر اساس Authority پیدا کنید
            payment = conn.execute(
                text("SELECT id, user_id, amount FROM public.payments WHERE authority = :auth AND status = 'PENDING'"),
                {"auth": authority}
            ).mappings().first()

            if not payment:
                logger.warning(f"Payment not found or already processed. Authority: {authority}")
                # چک کن آیا قبلاً تایید شده؟
                verified = conn.execute(text("SELECT 1 FROM public.payments WHERE authority = :auth AND status = 'COMPLETED'"), {"auth": authority}).scalar_one_or_none()
                return redirect(success_url if verified else failed_url)

            if status == "NOK":
                # پرداخت ناموفق بود یا توسط کاربر لغو شد
                conn.execute(
                    text("UPDATE public.payments SET status = 'FAILED' WHERE id = :pid"),
                    {"pid": payment['id']}
                )
                conn.commit()
                logger.info(f"Payment failed by user. Authority: {authority}")
                return redirect(failed_url)

            if status == "OK":
                # 2. پرداخت در ظاهر موفق بوده، حالا باید با زرین‌پال تایید (Verify) شود
                payload = {
                    "merchant_id": ZARINPAL_MERCHANT_ID,
                    "amount": payment['amount']* 10,
                    "authority": authority
                }
                response = requests.post(ZARINPAL_VERIFY_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=10)
                response.raise_for_status()
                response_data = response.json()
                
                if response_data.get("data", {}).get("code") == 100:
                    # 3. --- پرداخت موفقیت‌آمیز و تایید شده! ---
                    logger.info(f"Payment SUCCESSFUL. Authority: {authority}, User: {payment['user_id']}")
                    
                    # 4. وضعیت پرداخت را در DB آپدیت کنید
                    conn.execute(
                        text("UPDATE public.payments SET status = 'COMPLETED', verified_at = NOW() WHERE id = :pid"),
                        {"pid": payment['id']}
                    )
                    # 5. اشتراک 3 روزه را برای کاربر فعال کنید
                    conn.execute(
                        text("""
                            UPDATE public.user_credits 
                            SET subscription_expires_at = (NOW() + INTERVAL '1 days')
                            WHERE user_id = :uid
                        """),
                        {"uid": payment['user_id']}
                    )
                    conn.commit()
                    return redirect(success_url)
                
                else:
                    # 6. تاییدیه زرین‌پال ناموفق بود
                    error_code = response_data.get("errors", {}).get("code", "verify_failed")
                    logger.error(f"Zarinpal verification FAILED. Authority: {authority}, Code: {error_code}")
                    conn.execute(
                        text("UPDATE public.payments SET status = 'FAILED' WHERE id = :pid"),
                        {"pid": payment['id']}
                    )
                    conn.commit()
                    return redirect(failed_url)

    except Exception as e:
        logger.error(f"CRITICAL error in payment verification: {e}", exc_info=True)
        return redirect(failed_url)


# ==============================================================================
# 12) Admin Credit Management Endpoints
# ==============================================================================

@app.route('/admin/credits')
@require_admin_auth
def serve_admin_credits():
    """
    صفحه HTML مدیریت اعتبار کاربران را نمایش می‌دهد.
    """
    return send_from_directory('.', 'admin-credits.html')


@app.route('/admin/get-user-credits', methods=['POST'])
@require_admin_auth
def admin_get_user_credits():
    """
    اطلاعات اعتبار کاربر را بر اساس شماره موبایل جستجو می‌کند.
    """
    try:
        data = request.json
        phone_raw = data.get('phone_number')
        phone = normalize_phone(phone_raw)
        
        if not phone:
            return jsonify({'error': 'فرمت شماره موبایل اشتباه است'}), 400
        
        with engine.connect() as conn:
            # 1. پیدا کردن کاربر
            user = conn.execute(
                text("SELECT id, first_name, phone_number FROM public.users WHERE phone_number = :phone"),
                {"phone": phone}
            ).mappings().first()
            
            if not user:
                return jsonify({'error': 'کاربری با این شماره یافت نشد'}), 404
            
            # 2. پیدا کردن اعتبار کاربر
            credits = conn.execute(
                text("SELECT message_credits, subscription_expires_at FROM public.user_credits WHERE user_id = :uid"),
                {"uid": user['id']}
            ).mappings().first()
            
            if not credits:
                # اگر کاربر وجود دارد ولی اعتبار ندارد (نباید اتفاق بیفتد)، یکی برایش بساز
                conn.execute(
                    text("INSERT INTO public.user_credits (user_id, message_credits) VALUES (:uid, 0)"),
                    {"uid": user['id']}
                )
                conn.commit()
                credits = {'message_credits': 0, 'subscription_expires_at': None}

            return jsonify({
                "user_id": user['id'],
                "first_name": user['first_name'],
                "phone_number": user['phone_number'],
                "message_credits": credits['message_credits'],
                "subscription_expires_at": credits['subscription_expires_at'].isoformat() if credits['subscription_expires_at'] else None
            })

    except Exception as e:
        logger.error(f"Error in admin_get_user_credits: {e}", exc_info=True)
        return jsonify({'error': 'خطای داخلی سرور'}), 500


@app.route('/admin/set-user-credits', methods=['POST'])
@require_admin_auth
def admin_set_user_credits():
    """
    اعتبار پیام و/یا اشتراک کاربر را آپدیت می‌کند.
    """
    try:
        data = request.json
        user_id = data.get('user_id')
        new_messages = data.get('new_messages') # می‌تواند null باشد
        add_days = data.get('add_days')       # می‌تواند null باشد
        
        if not user_id:
            return jsonify({'error': 'user_id الزامی است'}), 400
        
        # اطمینان از اینکه ورودی‌ها عددی هستند (اگر null نیستند)
        try:
            if new_messages is not None:
                new_messages = int(new_messages)
            if add_days is not None:
                add_days = int(add_days)
        except ValueError:
            return jsonify({'error': 'مقادیر باید عددی باشند'}), 400
            
        with engine.connect() as conn:
            set_clauses = []
            params = {"uid": user_id}
            
            # 1. منطق آپدیت اعتبار پیام
            if new_messages is not None:
                set_clauses.append("message_credits = :messages")
                params["messages"] = new_messages
            
            # 2. منطق آپدیت اشتراک
            if add_days is not None:
                # این SQL هوشمند است:
                # 1. اگر اشتراک فعال دارد (در آینده)، به آن اضافه می‌کند.
                # 2. اگر اشتراک ندارد (یا منقضی شده)، از "امروز" حساب می‌کند.
                set_clauses.append("""
                    subscription_expires_at = (
                        CASE 
                            WHEN subscription_expires_at > NOW() 
                            THEN subscription_expires_at 
                            ELSE NOW() 
                        END
                    ) + (INTERVAL '1 day' * :days)
                """)
                params["days"] = add_days
            
            if not set_clauses:
                return jsonify({'error': 'هیچ مقداری برای آپدیت ارسال نشد'}), 400

            # 3. اجرای کوئری نهایی
            query = f"UPDATE public.user_credits SET {', '.join(set_clauses)} WHERE user_id = :uid"
            conn.execute(text(query), params)
            conn.commit()
            
            logger.info(f"Admin updated credits for user {user_id}. Payload: {data}")
            return jsonify({'success': True, 'message': 'اعتبار کاربر با موفقیت آپدیت شد.'})

    except Exception as e:
        logger.error(f"Error in admin_set_user_credits: {e}", exc_info=True)
        return jsonify({'error': 'خطای داخلی سرور هنگام آپدیت'}), 500

# ==============================================================================
# Main Application Routes
# ==============================================================================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5007)