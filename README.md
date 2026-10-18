# 🚀 Alpha System | نظام إدارة التحقيقات الجنائية الذكي

نظام متكامل لإدارة وتحليل البيانات والجرائم الجنائية، يعتمد على **Python (Streamlit)** للواجهات البرمجية وتكامل الخدمات باستخدام **n8n** وقواعد البيانات **PostgreSQL**.

---

## 🎬 فيديو العرض التوضيحي (Live Demo)

شاهد العرض الحي لطريقة تشغيل وعمل النظام:

[![شاهد فيديو الديمو](https://img.youtube.com/vi/70hwSCwHCR8/maxresdefault.jpg)](https://www.youtube.com/watch?v=70hwSCwHCR8)

---

## ⚡ التشغيل السريع بضغطة زر (Windows)

إذا كنت تستخدم نظام **Windows**، يمكنك تشغيل كافة الخدمات والنظام بضغطة زر واحدة دون الحاجة لتطبيق الأوامر يدوياً:

1. تأكد من أن برنامج **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** يعمل في الخلفية.
2. اضغط مرتين (Double Click) على الملف التنفيذي:
   ```text
   run_alpha.bat

   🛠️ التشغيل اليدوي (Manual Setup)
1️⃣ المتطلبات الأساسية
Git

Docker Desktop

Python 3.10+

2️⃣ تنزيل المشروع وتغيير المجلد
Bash
git clone [https://github.com/3bdallah2004/AlphaSystem.git](https://github.com/3bdallah2004/AlphaSystem.git)
cd AlphaSystem
3️⃣ تشغيل خدمات Docker
Bash
docker compose up -d
4️⃣ تثبيت الحزم وتشغيل Streamlit
Bash
pip install streamlit requests pandas
streamlit run app.py
سيفتح النظام تلقائياً على العنوان: http://localhost:8501

📂 هيكلية الملفات (Project Structure)
Plaintext
AlphaSystem/
├── app.py                # واجهة التطبيق الرئيسية (Streamlit)
├── docker-compose.yml    # إعدادات Docker & PostgreSQL & n8n
├── run_alpha.bat         # ملف التشغيل السريع لـ Windows
├── .gitignore            # الملفات المستبعدة من رفع Git
└── README.md             # دليل الاستخدام والتوثيق
👤 المطور
عبد الله الحاج علي - @3bdallah2004


---

### 📝 كيفية وضعه في المستودع الآن:
1. اذهب لصفحة مشروعك على GitHub وادخل إلى ملف **`README.md`** (أو أنشئه إن لم يكن موجوداً).
2. احذف كل ما بداخله والصق الكود أعلاه كاملاً.
3. اضغط على **`Commit changes...`** في الأسفل للحفظ.

هكذا أصبح مشروعك جاهزاً وموثقاً بالكامل، ومدعوماً بفيديو توضيحي وطريقة تشغيل فائقة السهولة! بالتوفيق في العرض يا عبد الله.
http://googleusercontent.com/youtube_content/1
