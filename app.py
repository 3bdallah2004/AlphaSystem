import os
import io
import csv
import json
import html
import re
import sqlite3
from contextlib import contextmanager
from urllib.parse import urlparse

import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Alpha | نظام إدارة التحقيقات",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = "alpha_database.db"
CASE_TYPES = ["عام", "سرقة", "احتيال مالي", "جرائم إلكترونية", "اعتداء", "فقدان أو اختفاء", "أخرى"]
MIN_CASE_TEXT_LEN = 20

WEBHOOK_URL = os.getenv(
    "ALPHA_WEBHOOK_URL",
    "http://localhost:5678/webhook/d28e7f69-3f04-43a6-abbd-89b43204c62e",
)

components.html(
    """<script>
    try {
        const d = window.parent.document.documentElement;
        d.lang = 'ar';
        d.setAttribute('translate', 'no');
        d.classList.add('notranslate');
    } catch (e) {}
    </script>""",
    height=0,
)

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS investigations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_name TEXT,
                case_number TEXT,
                case_type TEXT,
                location TEXT,
                date TEXT,
                case_text TEXT,
                report_text TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(investigations)")}
        if "case_name" not in existing:
            conn.execute("ALTER TABLE investigations ADD COLUMN case_name TEXT")

init_db()

def save_to_db(case_name, case_number, case_type, location, date, case_text, report_text):
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO investigations
               (case_name, case_number, case_type, location, date, case_text, report_text)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (case_name, case_number, case_type, location, date, case_text, report_text),
        )
        return cur.lastrowid

def update_in_db(inv_id, case_name, case_number, case_type, location, date, case_text):
    with db() as conn:
        conn.execute(
            """UPDATE investigations
               SET case_name=?, case_number=?, case_type=?, location=?, date=?, case_text=?
               WHERE id=?""",
            (case_name, case_number, case_type, location, date, case_text, inv_id),
        )

def update_report_in_db(inv_id, report_text):
    with db() as conn:
        conn.execute("UPDATE investigations SET report_text=? WHERE id=?", (report_text, inv_id))

def delete_from_db(inv_id):
    with db() as conn:
        conn.execute("DELETE FROM investigations WHERE id=?", (inv_id,))

def get_saved_investigations(search_query="", type_filter="الكل"):
    sql = "SELECT id, case_name, case_number, case_type, timestamp FROM investigations"
    where, params = [], []
    if search_query:
        like = f"%{search_query}%"
        where.append("(case_name LIKE ? OR case_number LIKE ? OR case_text LIKE ? OR report_text LIKE ?)")
        params += [like, like, like, like]
    if type_filter and type_filter != "الكل":
        where.append("case_type = ?")
        params.append(type_filter)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

def case_number_exists(case_number):
    if not case_number:
        return False
    with db() as conn:
        row = conn.execute("SELECT 1 FROM investigations WHERE case_number = ? LIMIT 1", (case_number,)).fetchone()
    return row is not None

def export_cases_csv():
    with db() as conn:
        rows = conn.execute(
            "SELECT id, case_name, case_number, case_type, location, date, case_text, report_text, timestamp "
            "FROM investigations ORDER BY id DESC"
        ).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "اسم القضية", "رقم القضية", "التصنيف", "الموقع", "تاريخ الحادثة",
                     "نص البلاغ", "التقرير", "تاريخ الحفظ"])
    for r in rows:
        writer.writerow(list(r))
    return buf.getvalue().encode("utf-8-sig")

def get_case(inv_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM investigations WHERE id=?", (inv_id,)).fetchone()
    return dict(row) if row else None

def get_stats():
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM investigations").fetchone()[0]
        top = conn.execute(
            "SELECT case_type, COUNT(*) AS c FROM investigations GROUP BY case_type ORDER BY c DESC LIMIT 1"
        ).fetchone()
        last = conn.execute("SELECT timestamp FROM investigations ORDER BY id DESC LIMIT 1").fetchone()
    return total, (top["case_type"] if top else "—"), (str(last["timestamp"])[:16] if last else "—")

def extract_output(response):
    try:
        data = response.json()
    except ValueError:
        return response.text.strip() or "لم يُرجع الخادم محتوى نصياً."

    output_keys = ["output", "المخرجات", "report", "result", "response", "text", "message"]

    def pick(item):
        found = next((item[k] for k in output_keys if item.get(k) is not None), None)
        if found is None:
            return json.dumps(item, ensure_ascii=False, indent=2) if item else None
        return found if isinstance(found, str) else json.dumps(found, ensure_ascii=False, indent=2)

    if isinstance(data, list):
        parts = []
        for item in data:
            if isinstance(item, dict):
                p = pick(item)
                if p:
                    parts.append(p)
            else:
                parts.append(str(item))
        return "\n\n".join(parts) or "لم يتم العثور على تقرير في الاستجابة."

    if isinstance(data, dict):
        return pick(data) or "لم يتم العثور على تقرير في الاستجابة."

    return str(data)

def send_to_n8n(payload):
    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=(10, 120))
    except requests.exceptions.ConnectionError:
        return False, "تعذر الوصول إلى n8n. تأكد أنه يعمل وأن الرابط صحيح."
    except requests.exceptions.Timeout:
        return False, "انتهت مهلة الانتظار. التحليل أخذ وقتاً أطول من المسموح."
    except requests.exceptions.RequestException as exc:
        return False, f"خطأ في الاتصال: {exc}"

    if 200 <= r.status_code < 300:
        return True, extract_output(r)

    return False, f"رمز HTTP: {r.status_code}\n{r.text or ''}"

def check_n8n():
    p = urlparse(WEBHOOK_URL)
    base = f"{p.scheme}://{p.netloc}"
    try:
        r = requests.get(base, timeout=6)
        return True, f"خادم n8n يعمل (HTTP {r.status_code})"
    except requests.exceptions.RequestException:
        return False, "تعذر الاتصال بخادم n8n."

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&display=swap');

:root {
    --bg: #0b1120; --panel: #111b2e; --border: #25344c;
    --text: #e7edf7; --muted: #94a3b8; --accent: #42d6c5;
}

html, body, [class*="css"], [data-testid="stAppViewContainer"] { font-family: 'Cairo', sans-serif; }

.stApp {
    background:
        radial-gradient(ellipse at top right, #142a40 0%, transparent 42%),
        linear-gradient(145deg, #080d18, #0b1120 55%, #101b2c);
    color: var(--text);
}
.block-container { max-width: 1400px; padding-top: 2rem; padding-bottom: 3rem; }

h1, h2, h3, h4, p, label { text-align: right; }

[data-testid="stMarkdownContainer"] { direction: rtl; text-align: right; }
[data-testid="stMarkdownContainer"] code, [data-testid="stMarkdownContainer"] pre { direction: ltr; text-align: left; }

.hero {
    padding: 26px 30px; border: 1px solid #2c455e; border-radius: 22px;
    background: linear-gradient(120deg, #15253a, #101827 65%, #102a35); margin-bottom: 22px;
}
.hero-label { color: var(--accent); font-size: 12px; letter-spacing: 2px; font-weight: 800; }
.hero-title { color: #f3f7ff; font-size: 30px; font-weight: 800; margin: 8px 0; line-height: 1.6; }
.hero-description { color: #a8b8ce; font-size: 15px; line-height: 2; }

.section-title { color: #f1f5f9; font-size: 20px; font-weight: 800; margin: 6px 0 4px; text-align: right; }
.section-subtitle { color: var(--muted); font-size: 13px; line-height: 1.9; margin-bottom: 14px; text-align: right; }

.info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 10px 0 18px; direction: rtl; }
.info-card { background: #152238; border: 1px solid #283d5a; border-radius: 12px; padding: 14px 18px; text-align: right; }
.info-card-label { color: #8da4c4; font-size: 12px; font-weight: 600; }
.info-card-value { color: #38cfc0; font-size: 16px; font-weight: 800; margin-top: 4px; word-break: break-word; }

.step-item { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 10px; direction: rtl; color: #cbd5e1; font-size: 14px; line-height: 1.8; }
.step-num { background: #1aa99c; color: #07141c; font-weight: 800; border-radius: 50%; min-width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; font-size: 13px; margin-top: 2px; }

div[data-testid="stTextArea"] textarea, div[data-testid="stTextInput"] input {
    background-color: #0b1424; color: #e7edf7; border: 1px solid #344760;
    border-radius: 10px; direction: rtl; text-align: right;
}
div[data-testid="stSelectbox"] div[data-baseweb="select"] { direction: rtl; }

.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
    width: 100%; min-height: 46px; border-radius: 11px; border: 1px solid #42d6c5;
    background: linear-gradient(100deg, #1aa99c, #38cfc0); color: #07141c;
    font-family: 'Cairo', sans-serif; font-weight: 800; transition: 0.2s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
    border-color: #85fff1; background: #58e4d5; color: #07141c; transform: translateY(-1px);
}

[data-testid="stMetric"] { background: #111b2e; border: 1px solid #25344c; border-radius: 14px; padding: 12px 18px; direction: rtl; text-align: right; }
[data-testid="stMetricLabel"] { justify-content: flex-end; }

[data-testid="stSidebar"] { background: #0c1423; border-left: 1px solid #24344a; }
[data-testid="stSidebar"] * { font-family: 'Cairo', sans-serif; }
hr { border-color: #26374d; }
</style>
""", unsafe_allow_html=True)

def flash(kind, message):
    st.session_state["flash"] = (kind, message)

def open_case(inv_id):
    rec = get_case(inv_id)
    if rec:
        st.session_state["current"] = rec
        st.session_state["edit_id"] = None

def start_edit(inv_id):
    rec = get_case(inv_id)
    if rec:
        st.session_state["current"] = rec
        st.session_state["edit_id"] = inv_id
        st.session_state["edit_case_name"] = rec["case_name"] or ""
        st.session_state["edit_case_number"] = rec["case_number"] or ""
        st.session_state["edit_case_type"] = rec["case_type"] if rec["case_type"] in CASE_TYPES else "عام"
        st.session_state["edit_location"] = rec["location"] or ""
        st.session_state["edit_date"] = rec["date"] or ""
        st.session_state["edit_case_text"] = rec["case_text"] or ""
        st.session_state["edit_reanalyze"] = False

def ask_delete(inv_id):
    st.session_state["confirm_delete"] = inv_id

def cancel_delete():
    st.session_state["confirm_delete"] = None

def do_delete(inv_id):
    delete_from_db(inv_id)
    cur = st.session_state.get("current")
    if cur and cur["id"] == inv_id:
        st.session_state["current"] = None
    st.session_state["edit_id"] = None
    st.session_state["confirm_delete"] = None
    flash("success", "تم حذف القضية نهائياً.")

def close_report():
    st.session_state["current"] = None

def cancel_edit():
    st.session_state["edit_id"] = None

SAMPLE_CASES = [
    {
        "name": "سرقة شحنة الأجهزة الطبية الحديثة", "num": "ALP-2026-882", "type": "سرقة",
        "loc": "المستودع المركزي - العاصمة", "date": "2026-10-17",
        "text": "وقعت الحادثة في تمام الساعة 03:30 صباحاً داخل المستودع المركزي للخدمات الطبية. تلقت غرفة العمليات بلاغاً يفيد باقتحام المستودع الرئيسي وسرقة شحنة من أجهزة التخطيط بالرنين المغناطيسي المحمولة تُقدّر قيمتها بـ 2.5 مليون دولار. أظهرت المعاينة إلغاء قفل الأمان باستخدام بطاقات الوصول المشفّرة التابعة لشركة الصيانة الخارجية، مع العثور على بقع زيت محرك حديثة وشريحة هاتف محمول مكسورة.",
    },
    {
        "name": "احتيال عبر منصة استثمار وهمية", "num": "ALP-2026-883", "type": "احتيال مالي",
        "loc": "عبر الإنترنت - عدة مدن", "date": "2026-10-12",
        "text": "تقدّم 14 مواطناً بشكاوى متطابقة ضد منصة تدّعي الاستثمار في العملات الرقمية بعوائد شهرية مضمونة 18%. حوّل المشتكون مبالغ بين 2,000 و40,000 دولار إلى حسابين مصرفيين مختلفين. توقفت المنصة عن الرد بعد 3 أسابيع من الإيداع وأُغلق الموقع. تبيّن أن الحسابين فُتحا بهويتين مستعارتين، وأن الإعلانات الترويجية نُشرت من حساب واحد على مواقع التواصل.",
    },
    {
        "name": "اختراق قاعدة بيانات عملاء شركة اتصالات", "num": "ALP-2026-884", "type": "جرائم إلكترونية",
        "loc": "مركز البيانات الرئيسي - المنطقة الصناعية", "date": "2026-10-09",
        "text": "رصد فريق الأمن السيبراني نشاطاً غير طبيعي في الساعة 02:10 فجراً، تمثّل في تحميل حجم كبير من البيانات إلى عنوان خارجي. تبيّن أن حساب موظف في قسم الدعم الفني استُخدم في الدخول من موقع جغرافي مختلف عن مكان عمله. تُقدّر البيانات المسرّبة بنحو 120 ألف سجل عميل تتضمن أسماء وأرقام هواتف. لم تُسجَّل طلبات فدية حتى الآن.",
    },
    {
        "name": "اعتداء أمام مجمع تجاري", "num": "ALP-2026-885", "type": "اعتداء",
        "loc": "موقف السيارات - المجمع التجاري الشرقي", "date": "2026-10-14",
        "text": "وردت مكالمة طوارئ الساعة 21:40 عن شجار بين شخصين في موقف السيارات انتهى بإصابة أحدهما بجرح في الرأس نُقل على إثره إلى المستشفى. أفاد شاهدان بأن الخلاف بدأ حول أولوية الوقوف. تُظهر كاميرا المراقبة المشتبه به وهو يغادر بمركبة رمادية، ولم يُلتقط رقم اللوحة بوضوح. المصاب في حالة مستقرة وأدلى بإفادة أولية.",
    },
    {
        "name": "اختفاء طالب جامعي", "num": "ALP-2026-886", "type": "فقدان أو اختفاء",
        "loc": "السكن الجامعي - الحرم الشمالي", "date": "2026-10-15",
        "text": "أبلغ زميل السكن عن عدم عودة الطالب (21 عاماً) منذ مساء الثلاثاء، وآخر ظهور له كان في المكتبة الجامعية الساعة 19:00. هاتفه مغلق منذ الساعة 22:15، وتركت حقيبته الشخصية وبطاقته الجامعية في غرفته. أفادت الأسرة بعدم وجود مشاكل سابقة، بينما ذكر أحد الأصدقاء أنه بدا قلقاً في الأسبوع الأخير بسبب ضغوط دراسية.",
    },
    {
        "name": "حريق مشبوه في مخزن قطع غيار", "num": "ALP-2026-887", "type": "أخرى",
        "loc": "المنطقة الصناعية الثانية", "date": "2026-10-11",
        "text": "اندلع حريق في الساعة 01:45 فجراً بمخزن لقطع غيار السيارات، وأُخمد خلال ساعتين دون إصابات. رجّح الدفاع المدني وجود أكثر من نقطة اشتعال، وعُثر على آثار مادة سريعة الاشتعال قرب الباب الخلفي. كانت الكاميرات معطّلة منذ 3 أيام. وتبيّن أن المخزن مؤمَّن بوثيقة جديدة رُفعت قيمتها قبل الحادث بشهر.",
    },
    {
        "name": "سرقة مركبات من معرض سيارات", "num": "ALP-2026-888", "type": "سرقة",
        "loc": "شارع المعارض - الجنوبي", "date": "2026-10-16",
        "text": "تبيّن صباحاً اختفاء 3 سيارات حديثة من ساحة المعرض بعد كسر القفل الخارجي. أظهرت التسجيلات دخول شاحنة سحب بيضاء قبل الفجر بدون لوحات. المفاتيح الإلكترونية كانت محفوظة في خزنة لم تُفتح، ما يشير إلى استخدام جهاز لنسخ الإشارة. يُشتبه بعلاقة أحد العاملين السابقين بالحادثة.",
    },
    {
        "name": "تلاعب في مناقصة توريد", "num": "ALP-2026-889", "type": "عام",
        "loc": "إدارة المشتريات - المبنى الإداري", "date": "2026-10-05",
        "text": "كشفت المراجعة الداخلية أن 3 شركات تقدمت لمناقصة توريد معدات مكتبية بعروض متقاربة جداً وبنفس الأخطاء الإملائية في المستندات. فازت إحدى الشركات بعرض أعلى بنسبة 12% من متوسط السوق. تبيّن أن مدير الشركة الفائزة تربطه صلة قرابة بأحد أعضاء لجنة التقييم، ولم يُفصح العضو عن ذلك.",
    },
]

def auto_fill_sample():
    idx = st.session_state.get("sample_idx", 0) % len(SAMPLE_CASES)
    s = SAMPLE_CASES[idx]
    st.session_state["form_name"] = s["name"]
    st.session_state["form_num"] = s["num"]
    st.session_state["form_type"] = s["type"]
    st.session_state["form_loc"] = s["loc"]
    st.session_state["form_date"] = s["date"]
    st.session_state["form_text"] = s["text"]
    st.session_state["sample_idx"] = idx + 1

def clear_form():
    for k, v in {"form_name": "", "form_num": "", "form_type": "عام",
                 "form_loc": "", "form_date": "", "form_text": ""}.items():
        st.session_state[k] = v

def val(x, default="غير محدد"):
    return x if x else default

def safe_filename(name):
    cleaned = re.sub(r"[^\w\- ]", "_", name or "report").strip()
    return cleaned[:80] or "report"

def info_grid(items):
    cells = "".join(
        '<div class="info-card"><div class="info-card-label">{}</div><div class="info-card-value">{}</div></div>'.format(
            html.escape(str(label)), html.escape(str(value))
        )
        for label, value in items
    )
    st.markdown(f'<div class="info-grid">{cells}</div>', unsafe_allow_html=True)

for key, default in {
    "current": None, "edit_id": None, "confirm_delete": None,
    "form_name": "", "form_num": "", "form_type": "عام", "form_loc": "", "form_date": "", "form_text": "",
}.items():
    st.session_state.setdefault(key, default)

if st.session_state.pop("_clear_form", False):
    for k, v in {"form_name": "", "form_num": "", "form_type": "عام", "form_loc": "", "form_date": "", "form_text": ""}.items():
        st.session_state[k] = v

with st.sidebar:
    st.markdown("## 🔎 ALPHA")
    st.caption("INVESTIGATION WORKSPACE")
    st.divider()

    st.markdown("### 📂 القضايا المحفوظة")
    search_query = st.text_input("بحث", placeholder="🔍 ابحث بالاسم أو الرقم أو النص...", label_visibility="collapsed")
    type_filter = st.selectbox("التصنيف", ["الكل"] + CASE_TYPES, label_visibility="collapsed")
    saved_cases = get_saved_investigations(search_query.strip(), type_filter)
    st.caption(f"عدد النتائج: {len(saved_cases)}")

    if saved_cases:
        labels = {}
        for c in saved_cases:
            title = c["case_name"] or f"قضية غير مسماة (#{c['case_number'] or c['id']})"
            labels[c["id"]] = f"{title} · {c['case_type'] or 'عام'} · {str(c['timestamp'])[:10]}"

        selected_id = st.selectbox(
            "اختر قضية:", list(labels.keys()), format_func=lambda i: labels[i], label_visibility="collapsed"
        )

        b1, b2 = st.columns(2)
        b1.button("👁️ عرض", on_click=open_case, args=(selected_id,))
        b2.button("✏️ تعديل", on_click=start_edit, args=(selected_id,))

        if st.session_state.get("confirm_delete") == selected_id:
            st.warning("⚠️ هل أنت متأكد من الحذف؟ لا يمكن التراجع.")
            d1, d2 = st.columns(2)
            d1.button("نعم، احذف", on_click=do_delete, args=(selected_id,), key="del_yes")
            d2.button("إلغاء", on_click=cancel_delete, key="del_no")
        else:
            st.button("🗑️ حذف القضية", on_click=ask_delete, args=(selected_id,))
    else:
        st.info("لا توجد قضايا مطابقة.")

    st.divider()
    st.markdown("### 📤 تصدير")
    st.download_button("📥 تصدير كل القضايا (CSV)", data=export_cases_csv(),
                       file_name="alpha_cases.csv", mime="text/csv", use_container_width=True)

    st.divider()
    st.markdown("### 🔌 حالة الاتصال")
    if st.button("اختبار الاتصال بـ n8n"):
        ok, msg = check_n8n()
        (st.success if ok else st.error)(msg)

st.markdown("""
<div class="hero">
    <div class="hero-label">ALPHA INTELLIGENCE PLATFORM</div>
    <div class="hero-title">نظام ألفا لإدارة التحقيقات وتحليل القضايا</div>
    <div class="hero-description">أدخل بيانات القضية، أرسلها للتحليل، ثم راجع التقرير المنظم واحفظه أو نزّله.</div>
</div>
""", unsafe_allow_html=True)

if st.session_state.get("flash"):
    kind, message = st.session_state.pop("flash")
    {"success": st.success, "warning": st.warning, "error": st.error}.get(kind, st.info)(message)

total, top_type, last_time = get_stats()
m1, m2, m3 = st.columns(3)
m1.metric("📁 عدد القضايا المحفوظة", total)
m2.metric("🏷️ أكثر تصنيف تكراراً", top_type)
m3.metric("🕒 آخر قضية أُضيفت", last_time)

report_slot = st.container()

if st.session_state.get("edit_id"):
    st.markdown('<div class="section-title">✏️ تعديل بيانات القضية</div>'
                '<div class="section-subtitle">عدّل البيانات ثم احفظ. يمكنك اختيار إعادة التحليل لتحديث التقرير بناءً على التعديلات.</div>',
                unsafe_allow_html=True)

    with st.form("edit_case_form"):
        e_name = st.text_input("اسم القضية (العنوان)", key="edit_case_name")
        e_num = st.text_input("رقم القضية", key="edit_case_number")
        e_type = st.selectbox("تصنيف القضية", CASE_TYPES, key="edit_case_type")
        e_loc = st.text_input("موقع الحادثة", key="edit_location")
        e_date = st.text_input("تاريخ الحادثة", key="edit_date")
        e_text = st.text_area("تفاصيل الأحداث والبلاغ", key="edit_case_text", height=250)
        e_re = st.checkbox("🔄 إعادة إرسال القضية للتحليل وتحديث التقرير بعد الحفظ", key="edit_reanalyze")

        c_save, c_cancel = st.columns(2)
        save_changes = c_save.form_submit_button("💾 حفظ التعديلات", use_container_width=True)
        cancel = c_cancel.form_submit_button("❌ إلغاء", use_container_width=True)

    if cancel:
        cancel_edit()
        st.rerun()

    if save_changes:
        inv_id = st.session_state["edit_id"]
        if len(e_text.strip()) < MIN_CASE_TEXT_LEN:
            st.warning("تفاصيل القضية قصيرة جداً. أضف معلومات أكثر.")
        else:
            update_in_db(inv_id, e_name.strip() or "قضية بدون اسم", e_num.strip(), e_type,
                         e_loc.strip(), e_date.strip(), e_text.strip())
            message = "تم تحديث بيانات القضية بنجاح."
            kind = "success"
            if e_re:
                with st.spinner("جارٍ إعادة التحليل..."):
                    ok, result = send_to_n8n({
                        "case_name": e_name.strip() or "قضية بدون اسم", "case_text": e_text.strip(),
                        "case_number": e_num.strip(), "case_type": e_type,
                        "incident_location": e_loc.strip(), "incident_date": e_date.strip(),
                    })
                if ok:
                    update_report_in_db(inv_id, result)
                    message += " وتم تحديث التقرير."
                else:
                    kind = "warning"
                    message += f" لكن فشلت إعادة التحليل، والتقرير القديم ما زال كما هو.\n\n{result}"
            st.session_state["current"] = get_case(inv_id)
            st.session_state["edit_id"] = None
            flash(kind, message)
            st.rerun()

else:
    has_report = st.session_state.get("current") is not None
    with st.expander("➕ إدخال قضية جديدة", expanded=not has_report):
        left, right = st.columns([1.5, 1], gap="large")

        with left:
            s1, s2 = st.columns([2, 1])
            s1.button("🎲 تعبئة قضية نموذجية (كل ضغطة قضية جديدة)", on_click=auto_fill_sample)
            s2.button("🧹 تفريغ الحقول", on_click=clear_form)
            next_no = st.session_state.get("sample_idx", 0) % len(SAMPLE_CASES) + 1
            st.caption(f"القضية النموذجية التالية: {next_no} من {len(SAMPLE_CASES)}")

            with st.form("case_form"):
                case_name = st.text_input("اسم القضية أو عنوانها *", key="form_name",
                                           placeholder="مثال: سرقة شحنة الأجهزة الطبية")
                f1, f2 = st.columns(2)
                case_number = f1.text_input("رقم القضية (اختياري)", key="form_num", placeholder="ALP-2026-001")
                case_type = f2.selectbox("تصنيف القضية", CASE_TYPES, key="form_type")
                f3, f4 = st.columns(2)
                incident_location = f3.text_input("موقع الحادثة (اختياري)", key="form_loc",
                                                   placeholder="مثال: المستودع المركزي")
                incident_date = f4.text_input("تاريخ الحادثة (اختياري)", key="form_date", placeholder="2026-10-17")
                case_input = st.text_area("تفاصيل البلاغ أو القضية *", key="form_text", height=240,
                                           placeholder="اكتب الوقائع بوضوح: متى؟ أين؟ ماذا حدث؟ من الأشخاص المعنيون؟ ما الأدلة؟")
                submitted = st.form_submit_button("🚀 تحليل القضية وحفظ التقرير", use_container_width=True)

        with right:
            st.markdown('<div class="section-title">📋 كيف تستخدم النظام؟</div>', unsafe_allow_html=True)
            for i, step in enumerate([
                "أدخل اسم القضية وتفاصيل البلاغ (الحقول المعلّمة بـ * مطلوبة).",
                "اضغط «تحليل القضية وحفظ التقرير» وانتظر حتى يصلك التقرير.",
                "راجع التقرير أعلى الصفحة ونزّله بصيغة TXT أو Markdown.",
                "ارجع لأي قضية من القائمة الجانبية لعرضها أو تعديلها أو حذفها.",
            ], start=1):
                st.markdown(f'<div class="step-item"><div class="step-num">{i}</div><div>{step}</div></div>',
                            unsafe_allow_html=True)

            st.markdown('<div class="section-title" style="margin-top:18px">🕘 آخر القضايا</div>', unsafe_allow_html=True)
            recent = get_saved_investigations()[:5]
            if not recent:
                st.caption("لا توجد قضايا بعد.")
            for c in recent:
                r1, r2 = st.columns([3, 1])
                r1.markdown(f"**{c['case_name'] or 'قضية بدون اسم'}**  \n{c['case_type'] or 'عام'} · {str(c['timestamp'])[:10]}")
                r2.button("عرض", key=f"recent_{c['id']}", on_click=open_case, args=(c["id"],))

    if submitted:
        text = case_input.strip()
        if not case_name.strip():
            st.warning("يرجى إدخال اسم القضية أو عنوانها.")
        elif not text:
            st.warning("يرجى إدخال تفاصيل القضية قبل بدء التحليل.")
        elif len(text) < MIN_CASE_TEXT_LEN:
            st.warning("تفاصيل القضية قصيرة جداً. اكتب وقائع أكثر ليكون التحليل مفيداً.")
        else:
            payload = {
                "case_name": case_name.strip(),
                "case_text": text,
                "case_number": case_number.strip(),
                "case_type": case_type,
                "incident_location": incident_location.strip(),
                "incident_date": incident_date.strip(),
            }
            duplicate_number = case_number_exists(case_number.strip())
            with st.spinner("جارٍ إرسال البيانات وتحليلها... قد يستغرق ذلك حتى دقيقتين."):
                ok, result = send_to_n8n(payload)

            if ok:
                new_id = save_to_db(case_name.strip(), case_number.strip(), case_type,
                                    incident_location.strip(), incident_date.strip(), text, result)
                st.session_state["current"] = get_case(new_id)
                st.session_state["_clear_form"] = True
                if duplicate_number:
                    flash("warning", "تم الحفظ، لكن رقم القضية مستخدم في قضية أخرى مسبقاً. راجع الأرقام.")
                else:
                    flash("success", "تم تحليل القضية وحفظها في السجل بنجاح. التقرير معروض أدناه.")
                st.rerun()
            else:
                st.error("فشل إرسال القضية للتحليل. بياناتك ما زالت في النموذج ولم تُحفظ.")
                with st.expander("🔍 تفاصيل الخطأ"):
                    st.code(result)

def render_value(value):
    if isinstance(value, str):
        st.markdown(value.replace("\n", "  \n"))
    elif isinstance(value, list) and all(isinstance(v, (str, int, float)) for v in value):
        st.markdown("\n".join(f"- {v}" for v in value))
    else:
        st.json(value)

def render_report_body(report):
    text = str(report).strip()
    parsed = None
    if text[:1] in ("{", "["):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None

    if isinstance(parsed, dict):
        for key, value in parsed.items():
            with st.expander(str(key), expanded=True):
                render_value(value)
    elif parsed is not None:
        st.json(parsed)
    else:
        st.markdown(text.replace("\n", "  \n"))

def reanalyze_current():
    cur = st.session_state.get("current")
    if not cur:
        return
    ok, result = send_to_n8n({
        "case_name": cur["case_name"] or "قضية بدون اسم", "case_text": cur["case_text"] or "",
        "case_number": cur["case_number"] or "", "case_type": cur["case_type"] or "عام",
        "incident_location": cur["location"] or "", "incident_date": cur["date"] or "",
    })
    if ok:
        update_report_in_db(cur["id"], result)
        st.session_state["current"] = get_case(cur["id"])
        flash("success", "تم تحديث التقرير بنجاح.")
    else:
        flash("error", f"فشلت إعادة التحليل:\n\n{result}")

with report_slot:
    cur = st.session_state.get("current")
    if cur and not st.session_state.get("edit_id"):
        st.divider()
        st.markdown('<div class="section-title">📄 التقرير الجنائي ومعلومات القضية</div>', unsafe_allow_html=True)

        info_grid([
            ("اسم القضية", val(cur["case_name"], "غير مسمى")),
            ("رقم القضية", val(cur["case_number"])),
            ("التصنيف", val(cur["case_type"], "عام")),
            ("الموقع", val(cur["location"])),
            ("تاريخ الحادثة", val(cur["date"])),
            ("تاريخ الحفظ", str(cur["timestamp"])[:16]),
        ])

        tab_report, tab_text = st.tabs(["📄 التقرير التحليلي", "📝 نص البلاغ الأصلي"])
        with tab_report:
            with st.container(border=True):
                render_report_body(cur["report_text"] or "لا يوجد تقرير لهذه القضية.")
        with tab_text:
            with st.container(border=True):
                st.markdown((cur["case_text"] or "لا يوجد نص مسجل.").replace("\n", "  \n"))

        fname = safe_filename(cur["case_name"])
        a1, a2, a3 = st.columns(3)
        a1.download_button("📥 تحميل التقرير (TXT)", data=(cur["report_text"] or "").encode("utf-8"),
                             file_name=f"{fname}_report.txt", mime="text/plain", use_container_width=True)
        a2.button("🔄 إعادة تحليل القضية", on_click=reanalyze_current, use_container_width=True)
        a3.button("❌ إغلاق التقرير", on_click=close_report, use_container_width=True)