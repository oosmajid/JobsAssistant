# مشاور شغلی هوشمند هزارجاب

یک سیستم مشاوره شغلی مبتنی بر هوش مصنوعی که با استفاده از مدل‌های Gemini و تکنیک‌های پیشرفته NLP، به کاربران کمک می‌کند تا شغل مناسب خود را پیدا کنند.

## 🎯 ویژگی‌های اصلی

### 💬 مصاحبه هوشمند
- **رویکرد روایی**: استفاده از نظریه مشاوره شغلی روایی برای گفتگوی طبیعی
- **تحلیل عمیق**: استخراج الگوهای شخصیتی از پاسخ‌های کاربر
- **سوالات تطبیقی**: انتخاب هوشمندانه سوالات بر اساس نیازهای کاربر

### 🧠 تحلیل پیشرفته
- **چارچوب O*NET**: تحلیل بر اساس استانداردهای بین‌المللی
- **امتیازدهی چندبعدی**: ارزیابی علایق، ارزش‌ها و سبک‌های کاری
- **تشخیص منطقه شغلی**: تعیین سطح پیچیدگی مناسب برای کاربر

### 🎨 رابط کاربری مدرن
- **طراحی ریسپانسیو**: سازگار با تمام دستگاه‌ها
- **حالت تاریک**: تجربه کاربری بهتر در محیط‌های کم‌نور
- **رابط چت تعاملی**: گفتگوی طبیعی و روان

## 🛠️ تکنولوژی‌های استفاده شده

### Backend
- **Flask**: فریم‌ورک وب Python
- **PostgreSQL**: پایگاه داده رابطه‌ای با پشتیبانی از vector
- **SQLAlchemy**: ORM برای مدیریت پایگاه داده
- **Google Gemini AI**: مدل زبانی برای تحلیل و گفتگو

### Frontend
- **HTML5/CSS3**: ساختار و طراحی
- **JavaScript**: تعامل کاربری
- **Font Awesome**: آیکون‌ها
- **Vazirmatn**: فونت فارسی

### AI/ML
- **Sentence Transformers**: مدل embedding برای شباهت‌یابی
- **Vector Search**: جستجوی شغل بر اساس شباهت معنایی
- **Prompt Engineering**: طراحی پرامپت‌های تخصصی

## 📋 پیش‌نیازها

- Python 3.9+
- PostgreSQL 12+ (با extension pgvector)
- Google Gemini API Key

## 🚀 راه‌اندازی

### 1. کلون کردن پروژه
```bash
git clone <repository-url>
cd jobsAssistant
```

### 2. ایجاد محیط مجازی
```bash
python -m venv venv
source venv/bin/activate  # در Windows: venv\Scripts\activate
```

### 3. نصب وابستگی‌ها
```bash
pip install -r requirements.txt
```

### 4. تنظیم پایگاه داده
```bash
# نصب PostgreSQL و pgvector
# ایجاد دیتابیس
createdb hezarjob_local

# اجرای اسکریپت‌های SQL برای ایجاد جداول
psql -d hezarjob_local -f database_schema.sql
```

### 5. تنظیم متغیرهای محیطی
```bash
export GEMINI_API_KEY="your_api_key_here"
export DB_PASSWORD="your_db_password"
```

### 6. اجرای برنامه
```bash
python app.py
```

## 📁 ساختار پروژه

```
jobsAssistant/
├── app.py                 # فایل اصلی Flask
├── prompts.py            # پرامپت‌های سیستم AI
├── index.html           # صفحه اصلی چت
├── admin.html           # پنل مدیریت
├── shared_chat.html     # چت اشتراکی
├── stats.html          # آمار و گزارش‌ها
├── venv/               # محیط مجازی Python
└── README.md           # مستندات
```

## 🔧 پیکربندی

### تنظیمات پایگاه داده
در فایل `app.py` تنظیمات اتصال به پایگاه داده را تغییر دهید:
```python
DB_USER = "your_username"
DB_PASS = "your_password"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "hezarjob_local"
```

### تنظیمات AI
- مدل‌های پشتیبانی شده: Gemini Flash, Gemini Pro, Gemini 2.0
- مدل embedding: paraphrase-multilingual-mpnet-base-v2

## 📊 ویژگی‌های مدیریتی

### پنل مدیریت (`/admin`)
- مدیریت پرامپت‌های سیستم
- تنظیم کلیدهای API
- مشاهده آمار کاربران
- مدیریت مدل‌های AI

### آمار و گزارش‌ها (`/stats`)
- تعداد کاربران فعال
- آمار گفتگوها
- عملکرد سیستم

## 🔒 امنیت

- فایل‌های حساس در `.gitignore` قرار دارند
- کلیدهای API از طریق پایگاه داده مدیریت می‌شوند
- اعتبارسنجی ورودی‌های کاربر

## 🤝 مشارکت

1. Fork کنید
2. شاخه جدید ایجاد کنید (`git checkout -b feature/amazing-feature`)
3. تغییرات را commit کنید (`git commit -m 'Add amazing feature'`)
4. Push کنید (`git push origin feature/amazing-feature`)
5. Pull Request ایجاد کنید


## 🙏 تشکر

- تیم Google AI برای Gemini
- جامعه Sentence Transformers
- توسعه‌دهندگان Flask و PostgreSQL

---

**نکته**: این پروژه برای استفاده آموزشی و تجاری طراحی شده است. لطفاً قبل از استفاده تجاری، مجوزهای لازم را بررسی کنید.
