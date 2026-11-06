"""SAPakim - פורטל הזמנות ספקים ושו"ב ארגוני (Streamlit + Neon PostgreSQL / SQLite)

מבנה הקובץ:
  1. קונפיגורציה וקבועים
  2. עיצוב רשמי ויישור דו-כיווני (RTL CSS)
  3. מסד נתונים (Neon PostgreSQL קבוע / SQLite מקומי)
  4. פונקציות עזר וחישוב ימי פיגור אוטומטי
  5. מסכים: כניסה / מנהל ומדורים / ספק (עם נעילת תאריך מקורי והחלה אוטומטית)
  6. main()
"""
import json
import re
import secrets
import sqlite3
import urllib.parse
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="SAPakim - מערכת שו\"ב הזמנות וספקים",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==================== 1. קונפיגורציה וקבועים ====================
DB_PATH = "sapakim_cloud.db"
APP_URL = "https://sapakim-kukmcxaux8yf9tfjrygif9.streamlit.app"
MAX_LOGIN_ATTEMPTS = 5
DONE_STATUS = "סופק"
NO_ETA = "אין צפי"
DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y")

STATUS_OPTIONS = [
    "טרם עודכן",
    "תקין - בייצור",
    "בטיפול - שבוע הבא",
    "בטיפול מיידי",
    "מוכן לאספקה",
    'ממתין לבק"מ',
    "חסר שרטוט / דרוש מענה מדור",
    "מעוכב - חוסר חומר גלם",
    "עיכוב / בפיגור",
    DONE_STATUS,
]
ALERT_WORDS = ("שרטוט", "עיכוב", "מעוכב", "פיגור", "חוסר")

# ביטויים גנריים ישנים שיימחקו אוטומטית מתגובות הספק כדי שהספק יזין מידע אמיתי
OBSOLETE_NOTES = (
    "כל השאר אבדוק ואעדכן",
    "כל השאר אבדוק",
    "כל השאר סופק",
)

STAFF_KEYS = [
    ("BH-ADMIN-9920", "admin", "רועי - מנהל מערכת ראשי"),
    ("NAMER-7741", "mador", 'מדור נמ"ר'),
    ("MERKAVA-5582", "mador", "מדור מרכבה"),
    ("MANHAR-3319", "mador", 'מנה"ר רכש'),
]

EXCEL_ALIASES = {
    "order": ["מספר הזמנה", "הזמנה"],
    "line": ["שורה", "מספר שורה"],
    "supplier": ["חברה", "שם ספק", "ספק"],
    "contact": ["איש קשר", "איש_קשר", "נציג"],
    "phone": ["מספר טלפון", "טלפון", "פרטי התקשרות", "נייד"],
    "part": ['מק"ט', "מקט"],
    "desc": ["שם פריט", "פרט", "תיאור"],
    "qty": ["כמה הוזמנו", "כמות"],
    "due": ["תאריך אספקה", "אספקה"],
    "internal": ["סטטוס אחרון"],
    "expected": ["צפי ספק", "צפי_אספקה_מעודכן"],
    "status": ["סטטוס עדכני"],
    "note": ["תגובת ספק"],
    "updated": ["תאריך_עדכון_אחרון", "תאריך עדכון"],
    "mador": ["מענה מדור"],
}

KEEP_IF_EMPTY = [
    "part_number", "item_description", "contact_person", "supplier_phone", "due_date",
    "internal_status", "supplier_status", "expected_date", "supplier_note", "mador_response",
]

EXPORT_MAP = {
    "מספר הזמנה": "order_number",
    "שורה": "line_number",
    "שם פריט": "item_description",
    'מק"ט': "part_number",
    "תאריך אספקה מקורי": "due_date",
    "פיגור בימים": "delay_days_display",
    "חברה": "supplier_name",
    "סטטוס אחרון": "internal_status",
    "איש קשר": "contact_person",
    "מספר טלפון": "supplier_phone",
    "צפי ספק": "expected_date",
    "סטטוס עדכני": "supplier_status",
    "תגובת ספק": "supplier_note",
    "מענה מדור": "mador_response",
    "תאריך_עדכון_אחרון": "last_updated",
}

# ==================== 2. עיצוב רשמי ויישור קפדני לימין (RTL) ====================
CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700&display=swap');

    :root, html, body, .stApp {
        color-scheme: light !important;
        font-family: 'Rubik', sans-serif !important;
        direction: rtl !important;
        text-align: right !important;
        background: linear-gradient(180deg, #fffbeb 0%, #f8fafc 35%, #f1f5f9 100%) !important;
        color: #0f172a !important;
    }
    header[data-testid="stHeader"] {
        background-color: rgba(255, 251, 235, 0.92) !important;
        backdrop-filter: blur(6px);
        border-bottom: 1px solid #fde68a;
        height: 3.2rem !important; z-index: 999 !important;
    }
    .block-container {
        max-width: 1280px !important; margin: 0 auto !important;
        padding-top: 4.2rem !important; padding-bottom: 3rem !important;
        direction: rtl !important; text-align: right !important;
    }

    /* יישור לימין קפדני לכל סוגי הטקסט (כולל משולב עברית-אנגלית-מספרים) */
    p, span, label, div, h1, h2, h3, h4, h5, h6, li, th, td,
    .stMarkdown, .stText, .stCaption, [data-testid="stMarkdownContainer"] {
        color: #0f172a;
        direction: rtl !important;
        text-align: right !important;
        unicode-bidi: plaintext !important;
    }

    /* יישור לימין בתוך טבלאות st.dataframe ו-st.data_editor */
    [data-testid="stDataFrame"] *, [data-testid="stDataEditor"] *, .dvn-scroller * {
        direction: rtl !important;
        text-align: right !important;
    }

    .header-box {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 65%, #78350f 100%);
        padding: 1.3rem 1.8rem; border-radius: 16px; border-bottom: 4px solid #f59e0b;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12); margin-bottom: 1.4rem;
        direction: rtl !important; text-align: right !important;
    }
    .header-title {
        font-size: 1.45rem !important; font-weight: 700 !important; color: #fff !important;
        margin: 0 !important; direction: rtl !important; text-align: right !important;
    }
    .header-sub {
        font-size: 0.9rem !important; color: #fcd34d !important; margin-top: 0.35rem !important;
        font-weight: 500; direction: rtl !important; text-align: right !important;
    }

    div[data-testid="metric-container"] {
        background: #fff !important; padding: 0.9rem 1.1rem !important; border-radius: 14px !important;
        border: 1px solid #e2e8f0 !important; border-right: 5px solid #d97706 !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04) !important;
        direction: rtl !important; text-align: right !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important; font-weight: 700 !important;
        direction: rtl !important; text-align: right !important;
    }
    div[data-testid="stMetricLabel"] p {
        font-size: 0.85rem !important; font-weight: 600 !important; color: #475569 !important;
        direction: rtl !important; text-align: right !important;
    }

    input, textarea, select, [data-baseweb="select"] > div, [data-baseweb="input"] input {
        background-color: #fff !important; color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important; border-color: #cbd5e1 !important;
        font-weight: 500 !important; direction: rtl !important; text-align: right !important;
    }
    [data-baseweb="select"] svg { fill: #0f172a !important; }
    label[data-testid="stWidgetLabel"] p, .stRadio label p, .stCheckbox label p {
        color: #0f172a !important; font-weight: 600 !important; font-size: 0.9rem !important;
        direction: rtl !important; text-align: right !important;
    }

    [data-baseweb="popover"]:has([role="listbox"]), [data-baseweb="popover"]:has([role="listbox"]) *,
    [data-baseweb="menu"], [data-baseweb="menu"] *,
    [role="listbox"], [role="listbox"] *,
    [data-testid="stSelectboxVirtualDropdown"], [data-testid="stSelectboxVirtualDropdown"] * {
        background-color: #ffffff !important;
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
        color-scheme: light !important;
        opacity: 1 !important;
        font-family: 'Rubik', sans-serif !important;
        font-size: 16px !important;
        direction: rtl !important;
        text-align: right !important;
    }
    [role="option"], [role="option"] * { min-height: 44px; }

    [data-testid="stDateInputField"] {
        background-color: #ffffff !important; border: 1px solid #cbd5e1 !important; color-scheme: light !important;
    }
    [data-testid="stDateInputField"] * {
        color: #0f172a !important; -webkit-text-fill-color: #0f172a !important;
        font-family: 'Rubik', sans-serif !important; font-size: 16px !important;
    }

    [data-testid="stDateInputCalendar"] {
        background-color: #ffffff !important; color-scheme: light !important;
        border: 1px solid #cbd5e1 !important; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.18) !important;
    }
    [data-testid="stDateInputCalendar"] * {
        color: #0f172a !important; -webkit-text-fill-color: #0f172a !important;
        opacity: 1 !important; font-family: 'Rubik', sans-serif !important;
    }
    [data-testid="stDateInputCalendar"] [aria-disabled="true"],
    [data-testid="stDateInputCalendar"] [data-outside-month="true"] {
        color: #94a3b8 !important; -webkit-text-fill-color: #94a3b8 !important;
    }
    [data-testid="stDateInputCalendar"] [role="button"]:hover { background-color: #fef3c7 !important; }
    [data-testid="stDateInputCalendar"] [data-selected="true"], [data-testid="stDateInputCalendar"] [aria-selected="true"] [role="button"],
    [data-testid="stDateInputCalendar"] [data-selected="true"] * {
        background-color: #d97706 !important; color: #ffffff !important; -webkit-text-fill-color: #ffffff !important;
    }

    .order-card-header {
        background: linear-gradient(90deg, #fef3c7 0%, #fffbeb 100%); padding: 0.75rem 1rem;
        border-radius: 10px; border-right: 5px solid #d97706; margin-bottom: 0.7rem; font-size: 0.92rem;
        direction: rtl !important; text-align: right !important;
    }
    .order-card-header, .order-card-header strong, .order-card-header span { color: #78350f !important; }
    .locked-badge {
        background: #e2e8f0; color: #1e293b !important; padding: 0.3rem 0.65rem; border-radius: 8px;
        font-size: 0.82rem; font-weight: 600; display: inline-block; margin-left: 0.4rem; margin-bottom: 0.4rem;
    }
    .delay-badge-red {
        background: #fee2e2; color: #991b1b !important; border: 1px solid #fca5a5;
        padding: 0.3rem 0.65rem; border-radius: 8px; font-size: 0.82rem; font-weight: 700;
        display: inline-block; margin-left: 0.4rem; margin-bottom: 0.4rem;
    }
    .delay-badge-green {
        background: #dcfce7; color: #166534 !important; border: 1px solid #86efac;
        padding: 0.3rem 0.65rem; border-radius: 8px; font-size: 0.82rem; font-weight: 700;
        display: inline-block; margin-left: 0.4rem; margin-bottom: 0.4rem;
    }

    button[kind^="primary"], button[data-testid^="stBaseButton-primary"] {
        background: linear-gradient(135deg, #d97706 0%, #b45309 100%) !important;
        border: none !important; font-weight: 600 !important; border-radius: 10px !important;
        box-shadow: 0 3px 10px rgba(180, 83, 9, 0.25) !important;
    }
    button[kind^="primary"] *, button[data-testid^="stBaseButton-primary"] * { color: #fff !important; }
    button[kind^="secondary"], button[data-testid^="stBaseButton-secondary"] {
        background-color: #fff !important; border: 1.5px solid #cbd5e1 !important;
        font-weight: 600 !important; border-radius: 10px !important;
    }
    button[kind^="secondary"] *, button[data-testid^="stBaseButton-secondary"] * { color: #0f172a !important; }

    .watermark {
        text-align: center !important; font-size: 0.78rem; color: #64748b !important;
        margin-top: 2.2rem; font-weight: 600; letter-spacing: 0.5px;
    }

    @media (max-width: 768px) {
        .block-container { padding: 3.8rem 0.6rem 3rem 0.6rem !important; }
        .header-box { padding: 0.95rem 1.1rem; border-radius: 12px; }
        .header-title { font-size: 1.18rem !important; }
        input, select, textarea { font-size: 16px !important; }
    }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ==================== 3. מסד נתונים (Neon PostgreSQL / SQLite) ====================
def _read_database_url():
    try:
        url = str(st.secrets.get("DATABASE_URL", "")).strip()
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    except Exception:
        return ""


DATABASE_URL = _read_database_url()
USE_PG = bool(DATABASE_URL)
PK_DEF = "SERIAL PRIMARY KEY" if USE_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"


def _py(value):
    if isinstance(value, dict):
        return {k: _py(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_py(v) for v in value)
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        return value.item()
    return value


class Db:
    """עוטף אחיד ל-SQLite ול-Neon Postgres."""

    def __init__(self):
        if USE_PG:
            import psycopg2
            import psycopg2.extras
            self.raw = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor, connect_timeout=15)
        else:
            self.raw = sqlite3.connect(DB_PATH, check_same_thread=False)
            self.raw.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        params = _py(params)
        if USE_PG:
            if isinstance(params, dict):
                sql = re.sub(r":(\w+)", r"%(\1)s", sql)
            else:
                sql = sql.replace("?", "%s")
        cur = self.raw.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


def get_db():
    return Db()


def query_df(conn, sql, params=()):
    cur = conn.execute(sql, params)
    rows = cur.fetchall()
    return pd.DataFrame([dict(r) for r in rows], columns=[d[0] for d in cur.description])


@st.cache_resource
def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS access_keys (
            access_key TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            contact_person TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            UNIQUE(role, entity_name)
        )''')
    conn.execute(f'''
        CREATE TABLE IF NOT EXISTS orders (
            id {PK_DEF},
            order_number TEXT NOT NULL,
            line_number TEXT NOT NULL,
            part_number TEXT DEFAULT '',
            item_description TEXT DEFAULT '',
            quantity TEXT DEFAULT '1',
            supplier_name TEXT DEFAULT 'ספק כללי',
            contact_person TEXT DEFAULT '',
            supplier_phone TEXT DEFAULT '',
            mador_name TEXT DEFAULT 'מדור נמ"ר',
            due_date TEXT DEFAULT '',
            internal_status TEXT DEFAULT '',
            supplier_status TEXT DEFAULT 'טרם עודכן',
            expected_date TEXT DEFAULT '',
            supplier_note TEXT DEFAULT '',
            mador_response TEXT DEFAULT '',
            needs_attention INTEGER DEFAULT 0,
            last_updated TEXT DEFAULT '',
            UNIQUE(order_number, line_number)
        )''')
    conn.commit()

    if not USE_PG:
        for sql in [
            "ALTER TABLE orders ADD COLUMN contact_person TEXT DEFAULT ''",
            "ALTER TABLE orders ADD COLUMN internal_status TEXT DEFAULT ''",
            "ALTER TABLE access_keys ADD COLUMN contact_person TEXT DEFAULT ''",
        ]:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass

    # ניקוי חד-פעמי של ההערה הגנרית הישנה "כל השאר אבדוק ואעדכן" משורות קיימות במסד
    for obs in OBSOLETE_NOTES:
        conn.execute("UPDATE orders SET supplier_note='' WHERE TRIM(supplier_note)=?", (obs,))

    # מילוי אוטומטי של תאריך האספקה המקורי לתוך צפי הספק לשורות שבהן הצפי עדיין ריק
    conn.execute("""
        UPDATE orders
        SET expected_date = due_date
        WHERE (expected_date IS NULL OR TRIM(expected_date) = '')
          AND due_date IS NOT NULL AND TRIM(due_date) != ''
    """)

    conn.execute("DELETE FROM access_keys WHERE role IN ('admin', 'mador')")
    for key, role, name in STAFF_KEYS:
        conn.execute("INSERT INTO access_keys (access_key, role, entity_name) VALUES (?, ?, ?)", (key, role, name))
    conn.commit()
    conn.close()
    return True


def get_or_create_key(conn, entity_name, contact_person="", phone=""):
    entity_name = clean_str(entity_name) or "ספק כללי"
    phone = clean_display_phone(phone)
    contact_person = clean_str(contact_person)

    row = conn.execute(
        "SELECT access_key, phone, contact_person FROM access_keys WHERE role='supplier' AND entity_name=?",
        (entity_name,),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE access_keys SET phone=?, contact_person=? WHERE access_key=?",
            (phone or row["phone"], contact_person or row["contact_person"], row["access_key"]),
        )
        return row["access_key"]

    new_key = f"SUP-{secrets.token_hex(3).upper()}"
    conn.execute(
        "INSERT INTO access_keys (access_key, role, entity_name, contact_person, phone) VALUES (?, 'supplier', ?, ?, ?)",
        (new_key, entity_name, contact_person, phone),
    )
    return new_key


def save_supplier_updates(conn, supplier_name, updates):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    due_by_id = {int(r["id"]): r["due_date"] for r in
                 conn.execute("SELECT id, due_date FROM orders WHERE supplier_name=?", (supplier_name,)).fetchall()}
    for order_id, status, expected, note in updates:
        clean_nt = clean_supplier_note(note)
        flag = needs_attention(status, clean_nt, expected, due_by_id.get(int(order_id), ""))
        conn.execute(
            """UPDATE orders
               SET supplier_status=?, expected_date=?, supplier_note=?, needs_attention=?, last_updated=?
               WHERE id=? AND supplier_name=?""",
            (status, expected, clean_nt, int(flag), now, int(order_id), supplier_name),
        )
    conn.commit()


def delete_orders_by_ids(conn, order_ids):
    for oid in order_ids:
        conn.execute("DELETE FROM orders WHERE id=?", (int(oid),))
    conn.commit()


# ==================== 4. פונקציות עזר וחישוב פיגור בימים ====================
def clean_str(val):
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "null") else s


def clean_supplier_note(val):
    """מסנן משפטים גנריים ישנים כגון 'כל השאר אבדוק ואעדכן'."""
    s = clean_str(val)
    for obs in OBSOLETE_NOTES:
        if s == obs or s.startswith(obs):
            return ""
    return s


def find_col(columns, candidates):
    for cand in candidates:
        for col in columns:
            if cand == str(col).strip() or cand in str(col).strip():
                return col
    return None


def clean_display_phone(raw):
    s = clean_str(raw).split(".")[0]
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) < 8 or digits == "0":
        return ""
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    elif len(digits) == 9 and digits.startswith("5"):
        digits = "0" + digits
    return digits


def format_wa_phone(raw):
    disp = clean_display_phone(raw)
    return "972" + disp[1:] if disp.startswith("05") and len(disp) == 10 else None


def parse_date(value):
    text = clean_str(value).split(" ")[0]
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def format_date_il(value):
    """מציג תאריך בפורמט ישראלי אחיד DD/MM/YYYY."""
    d = parse_date(value)
    return d.strftime("%d/%m/%Y") if d else clean_str(value)


def calc_delay_days_int(due_str, status=""):
    """מחשב פיגור בימים ביחס לתאריך האספקה המקורי (חיובי = בפיגור, 0 או שלילי = בזמן)."""
    if str(status or "").strip() == DONE_STATUS:
        return 0
    due_d = parse_date(due_str)
    if not due_d:
        return None
    return (date.today() - due_d).days


def format_delay_days(due_str, status=""):
    """מחזיר תצוגה ברורה של פיגור בימים ביחס לתאריך האספקה המקורי."""
    if str(status or "").strip() == DONE_STATUS:
        return "✅ סופק"
    diff = calc_delay_days_int(due_str, status)
    if diff is None:
        return "ללא תאריך יעד"
    if diff > 0:
        return f"🔴 {diff} ימים בפיגור"
    if diff == 0:
        return "🟡 מועד אספקה היום"
    return f"🟢 עוד {abs(diff)} ימים"


def enrich_delay_columns(df):
    """מוסיף ל-DataFrame עמודת מספר ימי פיגור ועמודת תצוגת פיגור בימים."""
    df = df.copy()
    if df.empty:
        df["delay_days_num"] = []
        df["delay_days_display"] = []
        return df
    df["delay_days_num"] = [
        calc_delay_days_int(r["due_date"], r["supplier_status"]) for _, r in df.iterrows()
    ]
    df["delay_days_display"] = [
        format_delay_days(r["due_date"], r["supplier_status"]) for _, r in df.iterrows()
    ]
    return df


def encode_eta(picked_date, no_eta, fallback_due=""):
    if no_eta:
        return NO_ETA
    if picked_date is None or pd.isna(picked_date):
        return format_date_il(fallback_due)
    return picked_date.strftime("%d/%m/%Y")


def attention_reason(status, note, expected, due):
    status = str(status or "").strip()
    reasons = []
    if str(note or "").strip():
        reasons.append("יש הערת ספק")
    if any(w in status for w in ALERT_WORDS):
        reasons.append(f"סטטוס: {status}")
    if status != DONE_STATUS:
        if clean_str(expected) == NO_ETA:
            reasons.append("אין צפי אספקה")
        else:
            eta, due_date = parse_date(expected), parse_date(due)
            if eta and due_date and eta > due_date:
                reasons.append(f"צפי ספק מאוחר ב-{(eta - due_date).days} ימים מתאריך המקור")
    return " | ".join(reasons)


def needs_attention(status, note, expected, due):
    return bool(attention_reason(status, note, expected, due))


def not_done(series):
    return ~series.astype(str).str.strip().eq(DONE_STATUS)


# ==================== 5א. מסך כניסה ====================
def render_login(conn):
    _, center, _ = st.columns([0.8, 2, 0.8])
    with center:
        st.markdown("""
        <div class="header-box" style="text-align: center !important;">
            <div class="header-title" style="text-align: center !important;">🛡️ פורטל SAPakim - חט"ל</div>
            <div class="header-sub" style="text-align: center !important;">מערכת שו"ב ארגונית לבקרת הזמנות, מעקב פיגורים ותקשורת ספקים</div>
        </div>""", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("##### הזדהות וכניסה למערכת")
            st.caption("אנא הזן את מפתח הגישה האישי (Access Key) שהונפק עבורך.")

            if st.session_state.failed_attempts >= MAX_LOGIN_ATTEMPTS:
                st.error("הגעת למספר הניסיונות המקסימלי. אנא רענן את הדף או פנה למנהל המערכת.")
                st.stop()

            key_input = st.text_input("מפתח גישה סודי:", type="password", placeholder="••••••••••••").strip().upper()
            if st.button("התחבר למערכת 🔒", type="primary", use_container_width=True):
                if not login_with_key(conn, key_input):
                    st.session_state.failed_attempts += 1
                    st.error(f"מפתח גישה שגוי או שאינו מורשה (ניסיון {st.session_state.failed_attempts}/{MAX_LOGIN_ATTEMPTS}).")
                else:
                    st.rerun()
        st.markdown('<div class="watermark">Powered by BEN HUR</div>', unsafe_allow_html=True)


def login_with_key(conn, key):
    row = conn.execute("SELECT * FROM access_keys WHERE UPPER(access_key)=?", (key,)).fetchone()
    if row:
        st.session_state.user = dict(row)
        st.session_state.failed_attempts = 0
        return True
    return False


def render_top_bar(conn, user):
    # אם זה ספק - נשלוף את שם איש הקשר שלו ונציג אותו בכותרת העליונה בלבד!
    contact_str = clean_str(user.get("contact_person", ""))
    if user["role"] == "supplier" and not contact_str:
        r_c = conn.execute(
            "SELECT contact_person FROM orders WHERE supplier_name=? AND contact_person != '' LIMIT 1",
            (user["entity_name"],),
        ).fetchone()
        if r_c:
            contact_str = clean_str(r_c["contact_person"])

    if user["role"] == "supplier":
        sub_text = f"👤 איש קשר: {contact_str}" if contact_str else "פורטל עדכון סטטוס הזמנות ספק"
    else:
        sub_text = f"מחובר בהרשאת: {user['role']}"

    c1, c2 = st.columns([4.5, 1])
    with c1:
        st.markdown(f"""
        <div class="header-box">
            <div class="header-title">🛡️ SAPakim | שלום, {user['entity_name']}</div>
            <div class="header-sub">{sub_text}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        if st.button("התנתק 🚪", use_container_width=True):
            st.session_state.user = None
            st.session_state.submitted = False
            st.query_params.clear()
            st.rerun()


# ==================== 5ב. ממשק מנהל ומדורים ====================
def render_staff(conn, user):
    if USE_PG:
        st.success("🟢 מחובר למסד הנתונים הקבוע בענן (Neon PostgreSQL) – כל ההזמנות, ימי הפיגור ותגובות הספקים שמורים ומגובים.")
    else:
        st.warning("⚠️ המערכת עובדת עם מסד נתונים זמני. הגדירו DATABASE_URL של Neon ב-Secrets לחיבור קבוע.")
    tab_orders, tab_wa, tab_upload = st.tabs([
        "📊 הזמנות, פיגורים ומענה מדור",
        "💬 שיגור וואטסאפ אוטומטי",
        "📥 טעינת אקסל (VLOOKUP חכם)",
    ])
    with tab_orders:
        render_orders_tab(conn, user)
    with tab_wa:
        render_whatsapp_tab(conn)
    with tab_upload:
        render_upload_tab(conn)


def render_orders_tab(conn, user):
    is_admin = (user["role"] == "admin")
    df = query_df(conn, "SELECT * FROM orders ORDER BY needs_attention DESC, supplier_name, order_number")
    if df.empty:
        st.info("אין עדיין הזמנות במערכת. עבור ללשונית 'טעינת אקסל' כדי להעלות קובץ.")
        return

    df = enrich_delay_columns(df)
    overdue_mask = df["delay_days_num"].fillna(0) > 0
    avg_delay = int(df.loc[overdue_mask, "delay_days_num"].mean()) if overdue_mask.any() else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric('סה"כ שורות הזמנה', len(df))
    k2.metric("שורות בפיגור מתאריך המקור", int(overdue_mask.sum()))
    k3.metric("ממוצע ימי פיגור", f"{avg_delay} ימים")
    k4.metric("⚠️ ממתינות למענה מדור", int((df["needs_attention"] == 1).sum()))

    f1, f2 = st.columns([1.5, 1])
    search = f1.text_input('🔍 חיפוש מהיר (לפי ספק, איש קשר, טלפון, הזמנה או מק"ט):', "")
    mode = f2.radio("תצוגה:", ["💻 טבלה מלאה", "📱 כרטיסיות (לנייד)"], horizontal=True)
    only_open = st.checkbox("הצג רק שורות פתוחות / בפיגור (הסתר שורות שסופקו)", value=False)

    view = df.copy()
    if search:
        mask = view.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
        view = view[mask]
    if only_open:
        view = view[not_done(view["supplier_status"])]

    if mode.startswith("📱"):
        render_staff_cards(conn, view, is_admin)
    else:
        render_staff_table(conn, view, is_admin)

    st.download_button(
        "📥 הורד דוח אקסל מלא (כולל עמודת פיגור בימים, אנשי קשר וטלפונים)",
        data=export_excel(df), file_name="suppliers_updated.xlsx", use_container_width=True,
    )

    if is_admin:
        render_admin_delete_panel(conn, df)


def render_staff_cards(conn, view, is_admin=False):
    st.caption("🔒 נתוני הספק נעולים. לחץ על הזמנה לצפייה בימי הפיגור, באיש הקשר ולהזנת מענה מדור.")
    for _, r in view.iterrows():
        icon = "⚠️" if r["needs_attention"] == 1 else "📦"
        with st.expander(f"{icon} {r['supplier_name']} | הזמנה {r['order_number']} שורה {r['line_number']} | {r['delay_days_display']}"):
            st.markdown(f"""
            <div class="order-card-header">
                <strong>פריט:</strong> {r['item_description']} | <strong>מק"ט:</strong> {r['part_number']} | <strong>תאריך מקורי:</strong> {r['due_date'] or '-'}<br>
                <strong>⏳ סטטוס פיגור:</strong> {r['delay_days_display']} | <strong>👤 איש קשר:</strong> {r['contact_person'] or '-'} | <strong>📞 טלפון:</strong> {r['supplier_phone'] or 'חסר'}
            </div>""", unsafe_allow_html=True)
            if r["needs_attention"] == 1:
                reason = attention_reason(r["supplier_status"], r["supplier_note"], r["expected_date"], r["due_date"])
                if reason:
                    st.warning(f"⚠️ סיבת הסימון: {reason}")
            st.markdown(f"🔒 **סטטוס עדכני:** `{r['supplier_status']}` | **צפי ספק:** `{r['expected_date'] or r['due_date'] or 'לא הוזן'}`")
            st.markdown(f"🔒 **תגובת / הערת ספק:** {r['supplier_note'] or 'אין הערות'}")

            reply = st.text_area("✍️ מענה מדור לספק:", value=r["mador_response"], key=f"mresp_{r['id']}")
            c_save, c_del = st.columns([3, 1]) if is_admin else (st.container(), None)
            with c_save:
                if st.button("💾 שמור מענה לשורה זו", key=f"msave_{r['id']}", type="primary", use_container_width=True):
                    now = datetime.now().strftime("%d/%m/%Y %H:%M")
                    conn.execute("UPDATE orders SET mador_response=?, needs_attention=0, last_updated=? WHERE id=?", (reply, now, r["id"]))
                    conn.commit()
                    st.success("מענה המדור נשמר!")
                    st.rerun()
            if is_admin and c_del is not None:
                with c_del:
                    if st.button("🗑️ מחק שורה", key=f"mdel_{r['id']}", use_container_width=True):
                        delete_orders_by_ids(conn, [r["id"]])
                        st.success(f"הזמנה {r['order_number']} שורה {r['line_number']} נמחקה!")
                        st.rerun()


def render_staff_table(conn, view, is_admin=False):
    if is_admin:
        st.caption('🔒 **אבטחת מידע:** עמודות דיווח הספק נעולות. עמודת "⏳ פיגור בימים" מחושבת אוטומטית ביחס לתאריך האספקה המקורי.')
    else:
        st.caption('🔒 **אבטחת מידע:** עמודות דיווח הספק נעולות. המדור יכול לעדכן איש קשר, טלפון, מק"ט ומענה מדור.')

    view = view.copy()
    view["attention"] = [
        attention_reason(r["supplier_status"], r["supplier_note"], r["expected_date"], r["due_date"]) if r["needs_attention"] == 1 else ""
        for _, r in view.iterrows()
    ]
    if is_admin:
        view["delete_row"] = False

    base_cols = [
        "id", "attention", "supplier_name", "contact_person", "supplier_phone",
        "order_number", "line_number", "part_number", "item_description",
        "due_date", "delay_days_display", "supplier_status", "expected_date",
        "supplier_note", "mador_response",
    ]
    cols = base_cols + (["delete_row"] if is_admin else [])

    T = st.column_config.TextColumn
    col_cfg = {
        "id": None,
        "attention": T("⚠️ סיבת סימון", disabled=True),
        "supplier_name": T("חברה", disabled=True),
        "contact_person": T("👤 איש קשר"),
        "supplier_phone": T("📞 מספר טלפון"),
        "order_number": T("מספר הזמנה", disabled=True),
        "line_number": T("שורה", disabled=True),
        "part_number": T('מק"ט'),
        "item_description": T("שם פריט"),
        "due_date": T("תאריך אספקה מקורי"),
        "delay_days_display": T("⏳ פיגור בימים", disabled=True),
        "supplier_status": T("🔒 סטטוס עדכני", disabled=True),
        "expected_date": T("🔒 צפי ספק", disabled=True),
        "supplier_note": T("🔒 תגובת ספק", disabled=True),
        "mador_response": T("✍️ מענה מדור לספק (ערוך כאן)"),
    }
    if is_admin:
        col_cfg["delete_row"] = st.column_config.CheckboxColumn("🗑️ מחק שורה", default=False)

    edited = st.data_editor(
        view[cols],
        column_config=col_cfg,
        use_container_width=True, hide_index=True,
    )

    btn_col1, btn_col2 = st.columns([2, 1]) if is_admin else (st.container(), None)
    with btn_col1:
        if st.button("💾 שמור תשובות מדור ועדכוני אנשי קשר", type="primary", use_container_width=True):
            now = datetime.now().strftime("%d/%m/%Y %H:%M")
            for _, r in edited.iterrows():
                phone = clean_display_phone(r["supplier_phone"])
                contact = clean_str(r["contact_person"])
                conn.execute(
                    """UPDATE orders
                       SET contact_person=?, supplier_phone=?, part_number=?, item_description=?,
                           due_date=?, mador_response=?, needs_attention=0, last_updated=?
                       WHERE id=?""",
                    (contact, phone, r["part_number"], r["item_description"], r["due_date"], r["mador_response"], now, r["id"]),
                )
                if phone or contact:
                    conn.execute(
                        """UPDATE access_keys
                           SET phone=COALESCE(NULLIF(?, ''), phone), contact_person=COALESCE(NULLIF(?, ''), contact_person)
                           WHERE role='supplier' AND entity_name=?""",
                        (phone, contact, r["supplier_name"]),
                    )
            conn.commit()
            st.success("הנתונים ותשובות המדור נשמרו בהצלחה!")
            st.rerun()

    if is_admin and btn_col2 is not None:
        with btn_col2:
            to_delete = edited[edited["delete_row"] == True]["id"].tolist()
            if st.button(f"🗑️ מחק שורות שסומנו ({len(to_delete)})", use_container_width=True):
                if not to_delete:
                    st.warning("לא סומנו שורות למחיקה בטבלה.")
                else:
                    delete_orders_by_ids(conn, to_delete)
                    st.success(f"נמחקו {len(to_delete)} שורות הזמנה בהצלחה!")
                    st.rerun()


def render_admin_delete_panel(conn, df):
    st.divider()
    with st.expander("🗑️ ניהול מחיקת הזמנות שהסתיימו / קיבלו מענה (הרשאת מנהל מערכת בלבד)"):
        st.caption("כאן תוכל למחוק הזמנות שהתקבלו או שהטיפול בהן הסתיים.")
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**1. מחיקת הזמנה שלמה או שורות נבחרות:**")
            df_opts = df.copy()
            df_opts["label"] = [
                f"הזמנה {r['order_number']} | שורה {r['line_number']} | {r['supplier_name']} ({r['supplier_status']})"
                for _, r in df_opts.iterrows()
            ]
            label_to_id = dict(zip(df_opts["label"], df_opts["id"]))
            selected_labels = st.multiselect("בחר הזמנות / שורות למחיקה:", options=df_opts["label"].tolist())
            if selected_labels and st.button(f"🗑️ מחק לצמיתות {len(selected_labels)} שורות שנבחרו", key="del_selected_admin"):
                ids = [label_to_id[lbl] for lbl in selected_labels]
                delete_orders_by_ids(conn, ids)
                st.success(f"נמחקו {len(ids)} שורות מהמערכת!")
                st.rerun()

        with c2:
            st.markdown("**2. ניקוי מהיר לפי סטטוס (סופק / טופל):**")
            done_ids = df[df["supplier_status"].astype(str).str.strip() == DONE_STATUS]["id"].tolist()
            st.write(f"שורות המסומנות כעת בסטטוס **'{DONE_STATUS}'**: `{len(done_ids)}` שורות.")
            confirm_done = st.checkbox("אני מאשר מחיקה של כל השורות שסופקו", key="confirm_del_done")
            if st.button(f"🧹 מחק את כל השורות שסופקו ({len(done_ids)})", disabled=not (confirm_done and done_ids)):
                delete_orders_by_ids(conn, done_ids)
                st.success(f"נמחקו {len(done_ids)} שורות שסופקו!")
                st.rerun()


def export_excel(df):
    df_enriched = enrich_delay_columns(df)
    export_df = pd.DataFrame({heb: df_enriched[col] for heb, col in EXPORT_MAP.items()})
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Sheet")
    return out.getvalue()


# ---------- וואטסאפ ----------
SUPPLIERS_SQL = '''
    SELECT
        u.entity_name AS supplier_name,
        COALESCE(NULLIF(MAX(o.contact_person), ''), NULLIF(u.contact_person, ''), '') AS contact_person,
        COALESCE(NULLIF(MAX(o.supplier_phone), ''), NULLIF(u.phone, ''), '') AS phone,
        u.access_key,
        COUNT(o.id) AS total_orders,
        COALESCE(CAST(SUM(CASE WHEN TRIM(COALESCE(o.supplier_status, '')) != 'סופק' THEN 1 ELSE 0 END) AS INTEGER), 0) AS open_or_delayed_orders
    FROM access_keys u
    LEFT JOIN orders o ON o.supplier_name = u.entity_name
    WHERE u.role = 'supplier'
    GROUP BY u.entity_name, u.access_key, u.contact_person, u.phone
    ORDER BY open_or_delayed_orders DESC, u.entity_name
'''


def build_whatsapp_message(conn, sup, sender):
    name = sup["supplier_name"]
    rows = conn.execute(
        "SELECT order_number, line_number, item_description, due_date FROM orders "
        "WHERE supplier_name=? AND TRIM(COALESCE(supplier_status, '')) != ?", (name, DONE_STATUS)).fetchall()
    if not rows:
        rows = conn.execute(
            "SELECT order_number, line_number, item_description, due_date FROM orders WHERE supplier_name=?", (name,)).fetchall()
    lines = "\n".join(
        f"• הזמנה {o['order_number']} שורה {o['line_number']} - {o['item_description']} (יעד מקורי: {o['due_date'] or '-'})"
        for o in rows[:10]
    )
    greeting = sup["contact_person"] or name
    link = f"{APP_URL}/?key={sup['access_key']}"
    return (
        f"היי {greeting}, מה נשמע?\n"
        f"זה {sender} מהחט\"ל. אני עובר על דו\"ח ההזמנות הפתוחות שלנו מול {name} וראיתי שיש לנו פער בלוח הזמנים בפריטים הבאים:\n"
        f"{lines}\n\n"
        f"כדי לעדכן סטטוס וצפי אספקה בלחיצה אחת (ולכתוב לנו אם נדרש מענה מהמדור), היכנסו לקישור האישי שלכם:\n"
        f"{link}\n"
        f"(מפתח גישה אישי: {sup['access_key']})\n"
        f"תודה מראש על שיתוף הפעולה, {sender}."
    )


def build_selenium_script(targets):
    return f"""import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

targets = {targets!r}

options = webdriver.ChromeOptions()
options.add_argument(r"user-data-dir=C:\\selenium_whatsapp_profile")
driver = webdriver.Chrome(options=options)
driver.get("https://web.whatsapp.com")
input(">>> וודא שוואטסאפ ווב פתוח וטעון, ולחץ ENTER להתחלת שליחה אוטומטית מלאה...")

for sup_name, contact_name, url in targets:
    print(f"שולח אל {{contact_name or sup_name}} ({{sup_name}})...")
    driver.get(url)
    try:
        send_btn = WebDriverWait(driver, 35).until(
            EC.element_to_be_clickable((By.XPATH, '//span[@data-icon="send"]/ancestor::button | //button[@aria-label="שליחה"] | //span[@data-icon="send"]'))
        )
        time.sleep(2)
        send_btn.click()
        print("נשלח בהצלחה!")
        time.sleep(5)
    except Exception as e:
        print(f"דילוג / שגיאה: {{e}}")
        time.sleep(3)

print("כל ההודעות נשלחו בהצלחה!")
driver.quit()
"""


def render_launcher(items):
    urls_js = json.dumps([i[3] for i in items])
    buttons = "".join(
        f'''<a href="{url}" target="_blank" style="display:inline-block;background:#16a34a;color:#fff;padding:10px 16px;
            margin:5px;border-radius:10px;text-decoration:none;font-family:Rubik,sans-serif;font-weight:600;font-size:14px;
            box-shadow:0 2px 6px rgba(0,0,0,0.12);">💬 שלח אל: {contact or sup} ({sup} - {phone})</a>'''
        for sup, contact, phone, url in items
    )
    html = f"""
    <div dir="rtl" style="font-family:Rubik,sans-serif;background:#fffbeb;border:2px solid #f59e0b;border-radius:14px;padding:16px;text-align:right;">
        <button onclick="launchAll()" style="width:100%;background:linear-gradient(135deg,#d97706,#b45309);color:#fff;border:none;
            padding:14px;border-radius:12px;font-size:16px;font-weight:700;cursor:pointer;">
            🚀 שגר עכשיו בלחיצה אחת לכל {len(items)} הספקים שנבחרו!
        </button>
        <div id="status_msg" style="font-size:13px;color:#78350f;margin:6px 0 12px;font-weight:600;">
            💡 הכפתור הכתום פותח את כל השיחות. אפשר גם ללחוץ על הכפתורים הירוקים ספק-אחר-ספק:
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;">{buttons}</div>
    </div>
    <script>
    function launchAll() {{
        var urls = {urls_js};
        document.getElementById('status_msg').innerText =
            'פותח כעת ' + urls.length + ' שיחות וואטסאפ... (אם נפתח רק אחד, אשר Pop-ups בשורת הכתובת של כרום)';
        urls.forEach(function(u) {{ window.open(u, '_blank'); }});
    }}
    </script>"""
    components.html(html, height=160 + (len(items) // 2) * 55, scrolling=True)


def render_whatsapp_tab(conn):
    st.markdown("##### 💬 מערך שיגור הודעות וואטסאפ אוטומטי לספקים ואנשי קשר")
    df_sups = query_df(conn, SUPPLIERS_SQL)
    df_sups["wa_ready"] = df_sups["phone"].apply(lambda p: "✅ תקין" if format_wa_phone(p) else "❌ חסר נייד")

    with st.container(border=True):
        c1, c2 = st.columns([2, 1])
        with c1:
            filter_mode = st.radio("1️⃣ בחר אוכלוסיית ספקים לשליחה:", [
                "📱 ספקים עם מספר נייד תקין לוואטסאפ (מומלץ לשליחה מיידית)",
                "🔴 כל הספקים עם הזמנות פתוחות / בעיכוב",
                "📋 כל הספקים במערכת",
            ])
        sender = c2.text_input("שם השולח בהודעה:", value="רועי")

        if filter_mode.startswith("📱"):
            pool = df_sups[df_sups["phone"].apply(lambda p: format_wa_phone(p) is not None)].copy()
        elif filter_mode.startswith("🔴"):
            pool = df_sups[df_sups["open_or_delayed_orders"] > 0].copy()
        else:
            pool = df_sups.copy()

        pool["label"] = [
            f"{r['supplier_name']} | 👤 {r['contact_person'] or 'ללא איש קשר'} | 📞 {r['phone'] or 'ללא טלפון'}"
            for _, r in pool.iterrows()
        ]

        select_mode = st.radio(
            "2️⃣ בחר אופן סימון ספקים:",
            [f"✅ כל הספקים ברשימה זו ({len(pool)} ספקים)", "🎯 בחירה ידנית של ספקים בודדים"],
            horizontal=True,
        )
        if select_mode.startswith("✅"):
            chosen = pool
        else:
            labels = st.multiselect("בחר ספק / איש קשר מהרשימה:", options=pool["label"].tolist(), default=pool["label"].tolist())
            chosen = pool[pool["label"].isin(labels)]

    items, script_targets = [], []
    for _, sup in chosen.iterrows():
        wa_phone = format_wa_phone(sup["phone"])
        if not wa_phone:
            continue
        text = urllib.parse.quote(build_whatsapp_message(conn, sup, sender))
        items.append((sup["supplier_name"], sup["contact_person"], sup["phone"], f"https://wa.me/{wa_phone}?text={text}"))
        script_targets.append((sup["supplier_name"], sup["contact_person"],
                               f"https://web.whatsapp.com/send?phone={wa_phone}&text={text}"))

    if not chosen.empty:
        st.markdown(f"##### 3️⃣ לוח שיגור ישיר ({len(items)} ספקים עם מספר נייד תקין):")
        if not items:
            st.warning("לספקים שסימנת אין מספר נייד תקין. גש ללשונית '📥 טעינת אקסל' וטען את הקובץ שלך!")
        else:
            render_launcher(items)
            st.download_button(
                "🤖 הורד רובוט שליחה אוטומטי מלא למחשב (שולח לבד ב-Chrome בלי ללחוץ Send)",
                data=build_selenium_script(script_targets).encode("utf-8"),
                file_name="auto_send_sapakim.py", mime="text/x-python", use_container_width=True,
            )

    st.divider()
    with st.expander("🔑 טבלת ריכוז ספקים, אנשי קשר, טלפונים ומפתחות גישה", expanded=True):
        st.dataframe(
            df_sups.rename(columns={
                "supplier_name": "חברה", "contact_person": "איש קשר", "phone": "מספר טלפון",
                "access_key": "מפתח גישה", "total_orders": 'סה"כ שורות',
                "open_or_delayed_orders": "שורות פתוחות", "wa_ready": "סטטוס וואטסאפ",
            }),
            use_container_width=True, hide_index=True,
        )


# ---------- טעינת אקסל (VLOOKUP חכם ללא דריסת תשובות קיימות) ----------
def render_upload_tab(conn):
    st.markdown("##### 📥 טעינת קובץ אקסל (`suppliers.xlsx`) - מנגנון VLOOKUP חכם למסד הנתונים")
    st.info(
        "💡 **איך עובד הסנכרון החכם (VLOOKUP)?**\n"
        "• **שורות והזמנות חדשות** מתווספות אוטומטית למסד הנתונים (תאריך האספקה המקורי מוגדר כברירת מחדל לצפי).\n"
        "• **שורות קיימות** מתעדכנות בפרטים החדשים **מבלי למחוק או לדרוס** תגובות ספקים, צפי אספקה או מענה מדור שכבר הוזנו באתר!\n"
        "• **ניקוי אוטומטי:** משפטים גנריים ישנים כמו 'כל השאר אבדוק ואעדכן' מנוקים אוטומטית כדי שהספק יזין סטטוס אמיתי."
    )
    uploaded = st.file_uploader("בחר קובץ Excel או CSV", type=["xlsx", "xls", "csv"])
    if uploaded and st.button("טען וסנכרן הזמנות למסד הנתונים (ללא מחיקת קיימים) ⚡", type="primary", use_container_width=True):
        df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
        df.columns = [str(c).strip() for c in df.columns]
        result = import_orders(conn, df)
        st.success(
            f"✅ הסנכרון למסד הנתונים הושלם! עובדו {result['rows']} שורות הזמנה "
            f"({result['contacts']} עם איש קשר, {result['phones']} עם טלפון) ללא מחיקת היסטוריה קיימת!"
        )


def import_orders(conn, df):
    cols = df.columns.tolist()
    col = {key: find_col(cols, aliases) for key, aliases in EXCEL_ALIASES.items()}

    def get(row, key):
        return clean_str(row[col[key]]) if col[key] else ""

    rows = contacts = phones = 0
    for _, r in df.iterrows():
        order_num = get(r, "order").split(".")[0]
        if not order_num:
            continue

        supplier = get(r, "supplier") or "ספק כללי"
        contact = get(r, "contact")
        phone = clean_display_phone(r[col["phone"]]) if col["phone"] else ""
        internal = get(r, "internal")

        if not phone or not contact:
            mem = conn.execute("SELECT phone, contact_person FROM access_keys WHERE role='supplier' AND entity_name=?", (supplier,)).fetchone()
            if mem:
                phone = phone or mem["phone"]
                contact = contact or mem["contact_person"]
        contacts += bool(contact)
        phones += bool(phone)

        get_or_create_key(conn, supplier, contact, phone)

        due_val = format_date_il(get(r, "due").split(" ")[0])
        exp_val = format_date_il(get(r, "expected").split(" ")[0]) or due_val
        note_val = clean_supplier_note(get(r, "note"))

        data = {
            "order_number": order_num,
            "line_number": get(r, "line").split(".")[0] or "10",
            "part_number": get(r, "part").split(".")[0],
            "item_description": get(r, "desc"),
            "quantity": get(r, "qty").split(".")[0] or "1",
            "supplier_name": supplier,
            "contact_person": contact,
            "supplier_phone": phone,
            "due_date": due_val,
            "internal_status": internal,
            "supplier_status": get(r, "status"),
            "expected_date": exp_val,
            "supplier_note": note_val,
            "mador_response": get(r, "mador"),
            "last_updated": get(r, "updated"),
        }
        names = ", ".join(data)
        placeholders = ", ".join(f":{k}" for k in data)
        protected_by_db = {"supplier_status", "expected_date", "supplier_note", "mador_response"}
        update_clauses = []
        for c in KEEP_IF_EMPTY:
            if c in protected_by_db:
                update_clauses.append(
                    f"{c}=CASE WHEN orders.{c} IS NOT NULL AND orders.{c}!='' AND orders.{c}!='טרם עודכן' "
                    f"THEN orders.{c} WHEN excluded.{c}!='' THEN excluded.{c} ELSE orders.{c} END"
                )
            else:
                update_clauses.append(f"{c}=CASE WHEN excluded.{c}!='' THEN excluded.{c} ELSE orders.{c} END")
        keep = ", ".join(update_clauses)

        conn.execute(
            f"""INSERT INTO orders ({names}) VALUES ({placeholders})
                ON CONFLICT(order_number, line_number) DO UPDATE SET supplier_name=excluded.supplier_name, {keep}""",
            data,
        )
        rows += 1

    conn.execute("""UPDATE orders SET supplier_status = COALESCE(NULLIF(internal_status, ''), 'טרם עודכן')
                    WHERE supplier_status = '' OR supplier_status IS NULL""")

    conn.execute("""UPDATE orders SET expected_date = due_date
                    WHERE (expected_date IS NULL OR TRIM(expected_date) = '') AND due_date != ''""")

    pending = conn.execute(
        "SELECT id, supplier_status, supplier_note, expected_date, due_date FROM orders "
        "WHERE COALESCE(mador_response, '') = '' AND needs_attention = 0").fetchall()
    for r in pending:
        if needs_attention(r["supplier_status"], r["supplier_note"], r["expected_date"], r["due_date"]):
            conn.execute("UPDATE orders SET needs_attention=1 WHERE id=?", (r["id"],))

    for order_col, key_col in (("contact_person", "contact_person"), ("supplier_phone", "phone")):
        conn.execute(f"""
            UPDATE orders SET {order_col} = (
                SELECT {key_col} FROM access_keys
                WHERE access_keys.entity_name = orders.supplier_name AND access_keys.role='supplier')
            WHERE {order_col} = '' OR {order_col} IS NULL""")
    conn.commit()
    return {"rows": rows, "contacts": contacts, "phones": phones}


# ==================== 5ג. מסך ספק (נעילת תאריך מקורי + החלה אוטומטית + ללא איש קשר בשורות) ====================
def render_supplier(conn, user):
    st.markdown(f"##### 📦 ההזמנות הפתוחות של: {user['entity_name']}")
    df = query_df(conn, "SELECT * FROM orders WHERE supplier_name=?", (user["entity_name"],))
    df["_line"] = pd.to_numeric(df["line_number"], errors="coerce")
    df = df.sort_values(["order_number", "_line"]).drop(columns="_line")

    if df.empty:
        st.warning("לא נמצאו הזמנות פתוחות המשויכות אליכם כרגע.")
        return

    df = enrich_delay_columns(df)

    if st.session_state.submitted:
        render_done_screen(df)
        return

    # כלי מילוי אוטומטי מהיר לספק (במקום לכתוב "כל השאר אבדוק ואעדכן")
    with st.expander("⚡ עדכון מהיר אוטומטי לכל השורות (לחץ כאן להחלת סטטוס או הערה גורפת על כל ההזמנות)"):
        st.caption("רוצים לעדכן סטטוס או הערה זהה לכל השורות שלכם בלחיצה אחת? בחרו כאן והמערכת תמלא אוטומטית:")
        b1, b2, b3 = st.columns([1.5, 2, 1])
        bulk_st = b1.selectbox("בחר סטטוס להחלה גורפת:", ["(ללא שינוי)"] + STATUS_OPTIONS, key="bulk_st_sel")
        bulk_nt = b2.text_input("הערה גורפת לכל השורות (אופציונלי):", placeholder="למשל: בייצור, יסופק במועד...", key="bulk_nt_inp")
        with b3:
            st.write("")
            if st.button("⚡ החל על כל השורות", type="primary", use_container_width=True):
                now = datetime.now().strftime("%d/%m/%Y %H:%M")
                for _, r in df.iterrows():
                    new_s = r["supplier_status"] if bulk_st == "(ללא שינוי)" else bulk_st
                    new_n = clean_supplier_note(bulk_nt) if bulk_nt.strip() else r["supplier_note"]
                    exp_d = r["expected_date"] or r["due_date"]
                    flag = needs_attention(new_s, new_n, exp_d, r["due_date"])
                    conn.execute(
                        "UPDATE orders SET supplier_status=?, supplier_note=?, expected_date=?, needs_attention=?, last_updated=? WHERE id=?",
                        (new_s, new_n, exp_d, int(flag), now, int(r["id"])),
                    )
                    # עדכון ה-Session State כדי שהשדות בטופס יתרעננו מיד
                    st.session_state[f"st_{r['id']}"] = new_s
                    st.session_state[f"nt_{r['id']}"] = new_n
                conn.commit()
                st.success("העדכון הוחל אוטומטית על כל השורות! ניתן לדייק שורות בודדות למטה וללחוץ על שמירה.")
                st.rerun()

    view = st.radio("בחר אופן תצוגה:", ["📱 תצוגת כרטיסיות (לנייד)", "💻 תצוגת טבלה מרוכזת (למחשב)"], horizontal=True)
    if view.startswith("📱"):
        updates = render_supplier_cards(df)
    else:
        updates = render_supplier_table(df)

    if updates is not None:
        save_supplier_updates(conn, user["entity_name"], updates)
        st.session_state.submitted = True
        st.rerun()


def render_supplier_cards(df):
    """מסך ספק בכרטיסיות: ללא איש קשר בשורה, עם פיגור בימים, ותאריך מקורי נעול עד לחיצה על 'שנה תאריך'."""
    st.caption(
        "🔒 **הנחיות דיווח:** תאריך האספקה המקורי מופיע כברירת מחדל ונעול. "
        "רק אם ברצונכם לעדכן מועד אספקה שונה, סמנו את הכפתור **'📅 שנה תאריך אספקה'** באותה שורה."
    )
    updates = []
    for _, row in df.iterrows():
        oid = int(row["id"])
        orig_due_str = format_date_il(row["due_date"])
        orig_due_date = parse_date(row["due_date"])
        saved_exp_str = clean_str(row["expected_date"])
        saved_exp_date = parse_date(saved_exp_str)

        with st.container(border=True):
            delay_cls = "delay-badge-red" if (row["delay_days_num"] or 0) > 0 else "delay-badge-green"
            st.markdown(f"""
            <div class="order-card-header">
                <strong>🔒 הזמנה: {row['order_number']} | שורה: {row['line_number']}</strong><br>
                <span>{row['item_description'] or 'ללא תיאור'}</span>
            </div>
            <div>
                <span class="locked-badge">🔒 מק"ט: {row['part_number'] or '-'}</span>
                <span class="locked-badge">🔒 תאריך אספקה מקורי: {orig_due_str or '-'}</span>
                <span class="{delay_cls}">⏳ {row['delay_days_display']}</span>
            </div>""", unsafe_allow_html=True)

            if row["mador_response"]:
                st.info(f"💬 **מענה מדור חט\"ל (נעול):** {row['mador_response']}")

            current_st = row["supplier_status"] if row["supplier_status"] in STATUS_OPTIONS else STATUS_OPTIONS[0]
            status = st.selectbox(
                "✍️ סטטוס עדכני:",
                STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(current_st),
                key=f"st_{oid}",
            )

            # בדיקה אם הספק כבר שינה בעבר את התאריך מתאריך המקור
            already_changed = bool(
                saved_exp_date and orig_due_date and saved_exp_date != orig_due_date
            )
            c_btn1, c_btn2, c_date = st.columns([1.4, 1.2, 2.2])
            with c_btn1:
                change_date = st.checkbox("📅 שנה תאריך אספקה", value=already_changed, key=f"chg_{oid}")
            with c_btn2:
                no_eta = st.checkbox("❓ אין צפי עדיין", value=(saved_exp_str == NO_ETA), key=f"noeta_{oid}")

            default_picker_date = saved_exp_date or orig_due_date or date.today()
            with c_date:
                eta_date = st.date_input(
                    "📅 תאריך אספקה בתגובת ספק (נעול לתאריך המקורי עד לחיצה על 'שנה תאריך'):",
                    value=default_picker_date,
                    format="DD/MM/YYYY",
                    disabled=(not change_date or no_eta),
                    key=f"eta_{oid}",
                )

            if no_eta:
                expected = NO_ETA
            elif change_date:
                expected = encode_eta(eta_date, False, orig_due_str)
            else:
                expected = orig_due_str or encode_eta(default_picker_date, False, "")

            note_val = clean_supplier_note(row["supplier_note"])
            note = st.text_input(
                "✍️ תגובת ספק / פירוט סיבה למדור:",
                value=note_val,
                placeholder="הקלד כאן תגובה מפורטת או בקשה למדור...",
                key=f"nt_{oid}",
            )
            updates.append((oid, status, expected, note))

    if st.button('✅ שמור ושלח את כל העדכונים לחט"ל', type="primary", use_container_width=True):
        return updates
    return None


def render_supplier_table(df):
    st.caption(
        "🔒 **הנחיות טבלה:** תאריך האספקה המקורי מוצג כברירת מחדל. "
        "כדי לשנות תאריך אספקה בשורה מסוימת, סמן V בעמודת **'📅 שנה תאריך'** ובחר את התאריך החדש."
    )
    df = df.copy()
    df["supplier_status"] = df["supplier_status"].apply(lambda x: x if x in STATUS_OPTIONS else STATUS_OPTIONS[0])
    df["orig_due_str"] = df["due_date"].apply(format_date_il)
    df["eta_date"] = [
        parse_date(r["expected_date"]) or parse_date(r["due_date"]) or date.today()
        for _, r in df.iterrows()
    ]
    df["change_date"] = [
        bool(parse_date(r["expected_date"]) and parse_date(r["due_date"]) and parse_date(r["expected_date"]) != parse_date(r["due_date"]))
        for _, r in df.iterrows()
    ]
    df["no_eta"] = df["expected_date"].apply(lambda x: clean_str(x) == NO_ETA)
    df["supplier_note"] = df["supplier_note"].apply(clean_supplier_note)

    T = st.column_config.TextColumn
    edited = st.data_editor(
        df[[
            "id", "order_number", "line_number", "part_number", "item_description",
            "orig_due_str", "delay_days_display", "supplier_status",
            "change_date", "eta_date", "no_eta", "supplier_note", "mador_response",
        ]],
        column_config={
            "id": None,
            "order_number": T("🔒 מס' הזמנה", disabled=True),
            "line_number": T("🔒 שורה", disabled=True),
            "part_number": T('🔒 מק"ט', disabled=True),
            "item_description": T("🔒 שם פריט", disabled=True),
            "orig_due_str": T("🔒 תאריך מקורי", disabled=True),
            "delay_days_display": T("⏳ פיגור בימים", disabled=True),
            "supplier_status": st.column_config.SelectboxColumn("✍️ סטטוס עדכני", options=STATUS_OPTIONS, required=True),
            "change_date": st.column_config.CheckboxColumn("📅 שנה תאריך"),
            "eta_date": st.column_config.DateColumn("📅 תאריך בתגובת ספק", format="DD/MM/YYYY"),
            "no_eta": st.column_config.CheckboxColumn("❓ אין צפי"),
            "supplier_note": T("✍️ תגובת ספק"),
            "mador_response": T('🔒 מענה מדור חט"ל', disabled=True),
        },
        use_container_width=True, hide_index=True,
    )
    if st.button('✅ שמור ושלח עדכונים לחט"ל', type="primary", use_container_width=True):
        results = []
        for _, r in edited.iterrows():
            if r["no_eta"]:
                exp = NO_ETA
            elif r["change_date"]:
                exp = encode_eta(r["eta_date"], False, r["orig_due_str"])
            else:
                exp = r["orig_due_str"]
            results.append((r["id"], r["supplier_status"], exp, r["supplier_note"]))
        return results
    return None


def render_done_screen(df):
    st.success('✅ העדכונים נשלחו בהצלחה לחט"ל. תודה רבה!')
    last = df["last_updated"].replace("", pd.NA).dropna()
    if not last.empty:
        st.caption(f"עודכן לאחרונה: {last.iloc[-1]}")

    st.markdown("##### סיכום העדכונים ששלחתם")
    summary = df[[
        "order_number", "line_number", "item_description", "due_date",
        "delay_days_display", "supplier_status", "expected_date", "supplier_note", "mador_response",
    ]]
    st.dataframe(
        summary.rename(columns={
            "order_number": "הזמנה",
            "line_number": "שורה",
            "item_description": "פריט",
            "due_date": "תאריך מקורי",
            "delay_days_display": "פיגור בימים",
            "supplier_status": "סטטוס",
            "expected_date": "צפי ספק",
            "supplier_note": "הערתכם",
            "mador_response": 'מענה חט"ל',
        }),
        use_container_width=True, hide_index=True,
    )
    st.info("טעיתם בפרט כלשהו? אפשר לחזור ולתקן, ולשלוח שוב.")
    if st.button("✏️ עריכת התשובות", type="primary", use_container_width=True):
        st.session_state.submitted = False
        st.rerun()


# ==================== 6. main ====================
def run_app(conn):
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("failed_attempts", 0)
    st.session_state.setdefault("submitted", False)

    url_key = st.query_params.get("key", "").strip().upper()
    if url_key and not st.session_state.user:
        login_with_key(conn, url_key)

    if not st.session_state.user:
        render_login(conn)
        st.stop()

    user = st.session_state.user
    render_top_bar(conn, user)
    if user["role"] in ("admin", "mador"):
        render_staff(conn, user)
    else:
        render_supplier(conn, user)
    st.markdown('<div class="watermark">Powered by BEN HUR</div>', unsafe_allow_html=True)


def main():
    try:
        init_db()
        conn = get_db()
    except Exception as exc:
        st.error("❌ אין חיבור למסד הנתונים. בדקו את DATABASE_URL ב-Secrets של האפליקציה.")
        st.code(str(exc))
        st.stop()
    try:
        run_app(conn)
    finally:
        conn.close()


main()
