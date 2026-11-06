"""
================================================================================
SAPakim - מערכת שו"ב ארגונית לבקרת הזמנות, מדורים ותקשורת ספקים (חט"ל / צה"ל)
================================================================================
ארכיטקטורת הקובץ (מותאם לתחזוקה והעברה למתכנתים):
  פרק 1: הגדרות מערכת, קבועים והרשאות צוות (Configuration & Constants)
  פרק 2: שכבת עיצוב ותצוגה רשמית מיושרת לימין (RTL UI & CSS Layer)
  פרק 3: שכבת מסד הנתונים - Neon PostgreSQL / SQLite (Database Abstraction Layer)
  פרק 4: מנוע אבטחה, יומן אירועים, אימות ספקים ואיפוס סיסמאות (Security & Audit Layer)
  פרק 5: לוגיקה עסקית, VLOOKUP חכם, חישוב פיגורים וסטטוס שבועי (Business Logic Layer)
  פרק 6: תצוגות מערכת לפי תפקיד - כניסה / מנהל ומדורים / פורטל ספק (Presentation Layer)
  פרק 7: נקודת כניסה ראשית של האפליקציה (Main Entry Point)
================================================================================
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
    page_title='SAPakim - מערכת שו"ב הזמנות וספקים',
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ==============================================================================
# פרק 1: הגדרות מערכת, קבועים והרשאות צוות (Configuration & Constants)
# ==============================================================================
DB_PATH = "sapakim_cloud.db"
APP_URL = "https://sapakim-kukmcxaux8yf9tfjrygif9.streamlit.app"
MAX_LOGIN_ATTEMPTS = 5
DONE_STATUS = "סופק"
NO_ETA = "אין צפי"
DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y")
DATETIME_FORMATS = ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y")

# אפשרויות עבור עמודת "מנהל ההזמנה" (שיוך למדור)
MANAGER_OPTIONS = ['נמ"ר', "מרכבה", "איתן", 'מנה"ר', "כללי"]

# אפשרויות סטטוס ספק מובנות
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

OBSOLETE_NOTES = (
    "כל השאר אבדוק ואעדכן",
    "כל השאר אבדוק",
    "כל השאר סופק",
)

# מפתחות צוות: (מפתח גישה, תפקיד, שם תצוגה, שיוך למנהל ההזמנה)
# שיוך 'ALL' עבור מנהל מערכת רואה הכל; שיוך ספציפי ממדר אוטומטית את ההזמנות למדור!
STAFF_KEYS = [
    ("BH-ADMIN-9920", "admin", "רועי - מנהל מערכת ראשי", "ALL"),
    ("NAMER-7741", "mador", 'מדור נמ"ר', 'נמ"ר'),
    ("MERKAVA-5582", "mador", "מדור מרכבה", "מרכבה"),
    ("EITAN-6614", "mador", "מדור איתן", "איתן"),
    ("MANHAR-3319", "mador", 'מנה"ר רכש', 'מנה"ר'),
]

# מיפוי שמות עמודות גמיש לקליטת קובצי אקסל
EXCEL_ALIASES = {
    "order": ["מספר הזמנה", "הזמנה"],
    "line": ["שורה", "מספר שורה"],
    "manager": ["מנהל ההזמנה", "מנהל הזמנה", "מדור", "פרויקט", "רק\"מ", "רקמ"],
    "supplier": ["חברה", "שם ספק", "ספק"],
    "contact": ["איש קשר", "איש_קשר", "נציג"],
    "phone": ["מספר טלפון", "טלפון", "פרטי התקשרות", "נייד"],
    "part": ['מק"ט', "מקט"],
    "desc": ["שם פריט", "פרט", "תיאור"],
    "qty": ["כמה הוזמנו", "כמות"],
    "due": ["תאריך אספקה מקורי", "תאריך אספקה", "אספקה"],
    "internal": ["סטטוס אחרון"],
    "expected": ["צפי ספק", "צפי_אספקה_מעודכן"],
    "status": ["סטטוס עדכני"],
    "note": ["תגובת ספק"],
    "updated": ["תאריך_עדכון_אחרון", "תאריך עדכון"],
    "mador": ["מענה מדור"],
}

KEEP_IF_EMPTY = [
    "order_manager", "part_number", "item_description", "contact_person",
    "supplier_phone", "due_date", "internal_status", "supplier_status",
    "expected_date", "supplier_note", "mador_response",
]

EXPORT_MAP = {
    "מספר הזמנה": "order_number",
    "שורה": "line_number",
    "מנהל ההזמנה": "order_manager",
    "שם פריט": "item_description",
    'מק"ט': "part_number",
    "תאריך אספקה מקורי": "due_date",
    "פיגור בימים": "delay_days_display",
    "סטטוס שבועי": "weekly_status_display",
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


# ==============================================================================
# פרק 2: שכבת עיצוב ותצוגה רשמית מיושרת לימין (RTL UI & CSS Layer)
# ==============================================================================
CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700&display=swap');

    :root, html, body, .stApp {
        color-scheme: light !important;
        font-family: 'Rubik', sans-serif !important;
        direction: rtl;
        text-align: right;
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
        max-width: 1420px !important; margin: 0 auto !important;
        padding-top: 4.2rem !important; padding-bottom: 3rem !important;
    }

    .stMarkdown, .stText, .stCaption, [data-testid="stMarkdownContainer"] p,
    h1, h2, h3, h4, h5, h6 {
        color: #0f172a;
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
        font-size: 1.45rem !important; font-weight: 700 !important;
        color: #0f172a !important;
        direction: rtl !important; text-align: right !important;
    }
    div[data-testid="stMetricLabel"] p {
        font-size: 0.84rem !important; font-weight: 600 !important; color: #475569 !important;
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

    [data-testid="stDateInputField"], [data-testid="stDateInputCalendar"] {
        background-color: #ffffff !important; border: 1px solid #cbd5e1 !important; color-scheme: light !important;
    }
    [data-testid="stDateInputField"] *, [data-testid="stDateInputCalendar"] * {
        color: #0f172a !important; -webkit-text-fill-color: #0f172a !important;
        font-family: 'Rubik', sans-serif !important;
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


# ==============================================================================
# פרק 3: שכבת מסד הנתונים - Neon PostgreSQL / SQLite (Database Layer)
# ==============================================================================
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
    """מחלקת עטיפה אחידה ל-Neon PostgreSQL ול-SQLite."""

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
    """מאתחל את כלל הטבלאות, מבצע מיגרציות אוטומטיות לעמודות חדשות ומזריק מפתחות צוות."""
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS access_keys (
            access_key TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            contact_person TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            custom_password TEXT DEFAULT '',
            assigned_manager TEXT DEFAULT 'ALL',
            is_locked INTEGER DEFAULT 0,
            last_pwd_change TEXT DEFAULT '',
            UNIQUE(role, entity_name)
        )''')
    conn.execute(f'''
        CREATE TABLE IF NOT EXISTS orders (
            id {PK_DEF},
            order_number TEXT NOT NULL,
            line_number TEXT NOT NULL,
            order_manager TEXT DEFAULT 'נמ"ר',
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
    conn.execute(f'''
        CREATE TABLE IF NOT EXISTS security_logs (
            id {PK_DEF},
            event_time TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor_name TEXT NOT NULL,
            details TEXT NOT NULL,
            new_credential TEXT DEFAULT '',
            is_read INTEGER DEFAULT 0
        )''')
    conn.commit()

    # מיגרציות בטוחות לעמודות חדשות (עובד גם על Neon PostgreSQL וגם על SQLite)
    migrations = [
        "ALTER TABLE orders ADD COLUMN contact_person TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN internal_status TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN order_manager TEXT DEFAULT 'נמ\"ר'",
        "ALTER TABLE access_keys ADD COLUMN contact_person TEXT DEFAULT ''",
        "ALTER TABLE access_keys ADD COLUMN custom_password TEXT DEFAULT ''",
        "ALTER TABLE access_keys ADD COLUMN assigned_manager TEXT DEFAULT 'ALL'",
        "ALTER TABLE access_keys ADD COLUMN is_locked INTEGER DEFAULT 0",
        "ALTER TABLE access_keys ADD COLUMN last_pwd_change TEXT DEFAULT ''",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            if USE_PG:
                conn.raw.rollback()

    for obs in OBSOLETE_NOTES:
        conn.execute("UPDATE orders SET supplier_note='' WHERE TRIM(supplier_note)=?", (obs,))

    conn.execute("""
        UPDATE orders
        SET expected_date = due_date
        WHERE (expected_date IS NULL OR TRIM(expected_date) = '')
          AND due_date IS NOT NULL AND TRIM(due_date) != ''
    """)
    conn.execute("""
        UPDATE orders
        SET order_manager = 'נמ"ר'
        WHERE order_manager IS NULL OR TRIM(order_manager) = ''
    """)

    # תיקון פורמט מספרים קיימים במסד
    rows_p = conn.execute("SELECT id, supplier_phone, part_number, order_number, line_number FROM orders").fetchall()
    for rp in rows_p:
        fixed_p = clean_display_phone(rp["supplier_phone"])
        fixed_part = clean_part_num(rp["part_number"])
        fixed_ord = clean_id_num(rp["order_number"])
        fixed_line = clean_id_num(rp["line_number"]) or "10"
        if (fixed_p != rp["supplier_phone"] or fixed_part != rp["part_number"]
                or fixed_ord != rp["order_number"] or fixed_line != rp["line_number"]):
            conn.execute(
                "UPDATE orders SET supplier_phone=?, part_number=?, order_number=?, line_number=? WHERE id=?",
                (fixed_p, fixed_part, fixed_ord, fixed_line, rp["id"]),
            )

    conn.execute("DELETE FROM access_keys WHERE role IN ('admin', 'mador')")
    for key, role, name, mgr in STAFF_KEYS:
        conn.execute(
            "INSERT INTO access_keys (access_key, role, entity_name, assigned_manager) VALUES (?, ?, ?, ?)",
            (key, role, name, mgr),
        )
    conn.commit()
    conn.close()
    return True


# ==============================================================================
# פרק 4: מנוע אבטחה, יומן אירועים, אימות ספקים ואיפוס סיסמאות (Security Layer)
# ==============================================================================
def log_security_event(conn, event_type, actor_name, details, new_credential=""):
    """מתעד אירוע אבטחה / שינוי סיסמה / עריכת מנהל בטבלת הבקרה."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    conn.execute(
        """INSERT INTO security_logs (event_time, event_type, actor_name, details, new_credential, is_read)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (now, event_type, actor_name, details, new_credential),
    )
    conn.commit()


def authenticate_user(conn, key_or_pwd):
    """מאמת משתמש לפי מפתח גישה ראשי או לפי סיסמה אישית שהספק הגדיר."""
    clean_k = clean_str(key_or_pwd)
    if not clean_k:
        return None, "נא להזין מפתח גישה או סיסמה."
    row = conn.execute(
        "SELECT * FROM access_keys WHERE UPPER(access_key)=? OR (custom_password != '' AND custom_password=?)",
        (clean_k.upper(), clean_k),
    ).fetchone()
    if not row:
        return None, "מפתח גישה או סיסמה שגויים."
    if int(row.get("is_locked") or 0) == 1:
        return None, "⛔ גישת ספק זה ננעלה על ידי מנהל המערכת. אנא פנה לחט\"ל."
    return dict(row), ""


def verify_supplier_pin(conn, supplier_user, pin_input):
    """
    אימות דו-שלבי (2FA) לקישור ספק למניעת דליפת מידע:
    מוודא שמי שלחץ על הקישור הוא אכן איש הקשר של הספק (4 ספרות אחרונות של הטלפון שלו או סיסמת הספק).
    """
    pin = clean_str(pin_input)
    if not pin:
        return False

    # בדיקה מול סיסמה אישית או מפתח גישה
    if pin.upper() == supplier_user["access_key"].upper():
        return True
    if supplier_user.get("custom_password") and pin == supplier_user["custom_password"]:
        return True

    # שליפת מספר הטלפון של איש הקשר
    phone = clean_display_phone(supplier_user.get("phone", ""))
    if not phone:
        r_p = conn.execute(
            "SELECT supplier_phone FROM orders WHERE supplier_name=? AND supplier_phone != '' LIMIT 1",
            (supplier_user["entity_name"],),
        ).fetchone()
        if r_p:
            phone = clean_display_phone(r_p["supplier_phone"])

    # אם לספק יש טלפון תקין במערכת - נבדוק התאמה ל-4 הספרות האחרונות (או למספר המלא)
    if phone and len(phone) >= 4:
        if pin == phone[-4:] or clean_display_phone(pin) == phone:
            return True
    return False


def update_supplier_password(conn, entity_name, new_password, changed_by="ספק"):
    """מעדכן סיסמה חדשה לספק ושולח התראה מיידית למנהל המערכת."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    conn.execute(
        "UPDATE access_keys SET custom_password=?, last_pwd_change=? WHERE role='supplier' AND entity_name=?",
        (new_password, now, entity_name),
    )
    conn.commit()
    log_security_event(
        conn,
        event_type="החלפת סיסמת ספק",
        actor_name=entity_name,
        details=f"הספק '{entity_name}' החליף סיסמה ({changed_by}).",
        new_credential=new_password,
    )


def regenerate_supplier_key(conn, entity_name, admin_name):
    """מייצר מפתח קישור חדש לספק (מבטל קישור קודם במקרה של חשש לדליפה)."""
    new_key = f"SUP-{secrets.token_hex(3).upper()}"
    conn.execute(
        "UPDATE access_keys SET access_key=? WHERE role='supplier' AND entity_name=?",
        (new_key, entity_name),
    )
    conn.commit()
    log_security_event(
        conn,
        event_type="איפוס קישור ספק",
        actor_name=admin_name,
        details=f"מפתח הקישור של '{entity_name}' הוחלף למניעת דליפת מידע.",
        new_credential=new_key,
    )
    return new_key


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
            (phone or clean_display_phone(row["phone"]), contact_person or row["contact_person"], row["access_key"]),
        )
        return row["access_key"]

    new_key = f"SUP-{secrets.token_hex(3).upper()}"
    conn.execute(
        "INSERT INTO access_keys (access_key, role, entity_name, contact_person, phone) VALUES (?, 'supplier', ?, ?, ?)",
        (new_key, entity_name, contact_person, phone),
    )
    return new_key


# ==============================================================================
# פרק 5: לוגיקה עסקית, VLOOKUP, חישוב פיגורים וסטטוס שבועי (Business Logic)
# ==============================================================================
def clean_str(val):
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "null") else s


def clean_id_num(val):
    if val is None or pd.isna(val):
        return ""
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        try:
            return str(int(round(val)))
        except Exception:
            pass
    s = clean_str(val)
    if not s:
        return ""
    try:
        if "e" in s.lower() or "." in s:
            return str(int(round(float(s))))
    except Exception:
        pass
    return s.split(".")[0].strip()


def clean_part_num(val):
    p = clean_id_num(val)
    if len(p) == 8 and p.startswith("4") and p.isdigit():
        return "0" + p
    return p


def clean_supplier_note(val):
    s = clean_str(val)
    for obs in OBSOLETE_NOTES:
        if s == obs or s.startswith(obs):
            return ""
    return s


def normalize_manager(raw_manager, item_desc=""):
    """מנרמל את שיוך 'מנהל ההזמנה' (נמ"ר / מרכבה / איתן / מנה"ר) מהאקסל או מתיאור הפריט."""
    txt = f"{clean_str(raw_manager)} {clean_str(item_desc)}"
    if "מרכבה" in txt:
        return "מרכבה"
    if "איתן" in txt:
        return "איתן"
    if "מנה\"ר" in txt or "מנהר" in txt:
        return 'מנה"ר'
    if "נמר" in txt or 'נמ"ר' in txt:
        return 'נמ"ר'
    clean_m = clean_str(raw_manager)
    return clean_m if clean_m in MANAGER_OPTIONS else 'נמ"ר'


def find_col(columns, candidates):
    for cand in candidates:
        for col in columns:
            if cand == str(col).strip() or cand in str(col).strip():
                return col
    return None


def clean_display_phone(raw):
    s = clean_id_num(raw)
    if not s:
        s = clean_str(raw).split(".")[0]
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) < 8 or digits == "0":
        return ""
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    elif len(digits) == 9 and digits[0] in ("5", "7"):
        digits = "0" + digits
    elif len(digits) == 8 and digits[0] in ("2", "3", "4", "8", "9"):
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
    d = parse_date(value)
    return d.strftime("%d/%m/%Y") if d else clean_str(value)


def calc_delay_days_int(due_str, status=""):
    if str(status or "").strip() == DONE_STATUS:
        return 0
    due_d = parse_date(due_str)
    if not due_d:
        return None
    return (date.today() - due_d).days


def format_delay_days(due_str, status=""):
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


def calc_weekly_status(last_updated_str, status=""):
    """מחשב חיווי עדכון שבועי (האם הספק עדכן ב-7 הימים האחרונים)."""
    if str(status or "").strip() == DONE_STATUS:
        return "✅ הושלם"
    txt = clean_str(last_updated_str)
    if not txt:
        return "⚪ טרם עודכן"
    upd_date = parse_date(txt)
    if not upd_date:
        return "⚪ טרם עודכן"
    days_ago = (date.today() - upd_date).days
    if days_ago <= 7:
        return "🟢 עודכן השבוע"
    return f"🟠 לפני {days_ago} ימים"


def enrich_orders_df(df):
    """מוסיף עמודות מחושבות: ניקוי מספרים, פיגור בימים וסטטוס עדכון שבועי."""
    df = df.copy()
    if df.empty:
        df["delay_days_num"] = []
        df["delay_days_display"] = []
        df["weekly_status_display"] = []
        return df
    df["order_number"] = df["order_number"].apply(clean_id_num)
    df["line_number"] = df["line_number"].apply(lambda x: clean_id_num(x) or "10")
    df["part_number"] = df["part_number"].apply(clean_part_num)
    df["supplier_phone"] = df["supplier_phone"].apply(clean_display_phone)
    df["order_manager"] = [
        normalize_manager(r.get("order_manager", ""), r.get("item_description", ""))
        for _, r in df.iterrows()
    ]
    df["delay_days_num"] = [
        calc_delay_days_int(r["due_date"], r["supplier_status"]) for _, r in df.iterrows()
    ]
    df["delay_days_display"] = [
        format_delay_days(r["due_date"], r["supplier_status"]) for _, r in df.iterrows()
    ]
    df["weekly_status_display"] = [
        calc_weekly_status(r["last_updated"], r["supplier_status"]) for _, r in df.iterrows()
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
    log_security_event(conn, "עדכון סטטוס ספק", supplier_name, f"הספק עדכן {len(updates)} שורות הזמנה.")


def delete_orders_by_ids(conn, order_ids, actor_name="מנהל מערכת"):
    for oid in order_ids:
        conn.execute("DELETE FROM orders WHERE id=?", (int(oid),))
    conn.commit()
    log_security_event(conn, "מחיקת הזמנות", actor_name, f"נמחקו {len(order_ids)} שורות הזמנה ממסד הנתונים.")


def export_full_backup_excel(conn):
    """מייצא גיבוי מערכת מלא ל-Excel עם 3 גיליונות: הזמנות, מפתחות ספקים ויומן אבטחה."""
    df_ord = enrich_orders_df(query_df(conn, "SELECT * FROM orders ORDER BY supplier_name, order_number"))
    export_orders = pd.DataFrame({heb: df_ord[col] for heb, col in EXPORT_MAP.items()}) if not df_ord.empty else pd.DataFrame()
    df_keys = query_df(conn, "SELECT access_key, role, entity_name, contact_person, phone, custom_password, assigned_manager, is_locked, last_pwd_change FROM access_keys")
    df_logs = query_df(conn, "SELECT event_time, event_type, actor_name, details, new_credential FROM security_logs ORDER BY id DESC")

    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        export_orders.to_excel(writer, index=False, sheet_name="הזמנות_ומעקב")
        df_keys.to_excel(writer, index=False, sheet_name="ספקים_וסיסמאות")
        df_logs.to_excel(writer, index=False, sheet_name="יומן_אבטחה")
    return out.getvalue()


# ==============================================================================
# פרק 6: תצוגות מערכת לפי תפקיד (Presentation Layer)
# ==============================================================================

# ---------- 6א. מסך כניסה + איפוס סיסמה לספק + אימות דו-שלבי לקישור ----------
def render_login(conn):
    _, center, _ = st.columns([0.8, 2.2, 0.8])
    with center:
        st.markdown("""
        <div class="header-box" style="text-align: center !important;">
            <div class="header-title" style="text-align: center !important;">🛡️ פורטל SAPakim - חט"ל</div>
            <div class="header-sub" style="text-align: center !important;">מערכת שו"ב ארגונית לבקרת הזמנות, מדורים ותקשורת ספקים מאובטחת</div>
        </div>""", unsafe_allow_html=True)

        tab_login, tab_reset = st.tabs(["🔒 כניסה למערכת", "🔑 איפוס / הגדרת סיסמה לספק"])

        with tab_login:
            with st.container(border=True):
                st.markdown("##### הזדהות וכניסה למערכת")
                st.caption("הזן את מפתח הגישה האישי (Access Key) או את הסיסמה האישית שהגדרת.")

                if st.session_state.failed_attempts >= MAX_LOGIN_ATTEMPTS:
                    st.error("הגעת למספר הניסיונות המקסימלי. אנא רענן את הדף או פנה למנהל המערכת.")
                    st.stop()

                key_input = st.text_input("מפתח גישה / סיסמה:", type="password", placeholder="••••••••••••")
                if st.button("התחבר למערכת 🔒", type="primary", use_container_width=True):
                    user_obj, err = authenticate_user(conn, key_input)
                    if not user_obj:
                        st.session_state.failed_attempts += 1
                        st.error(f"{err} (ניסיון {st.session_state.failed_attempts}/{MAX_LOGIN_ATTEMPTS}).")
                    else:
                        st.session_state.user = user_obj
                        st.session_state.link_verified = True
                        st.session_state.failed_attempts = 0
                        st.rerun()

        with tab_reset:
            with st.container(border=True):
                st.markdown("##### 🔄 איפוס או החלפת סיסמה לספק")
                st.caption("ספקים רשומים יכולים להגדיר לעצמם סיסמה אישית קבועה באמצעות אימות מספר הטלפון הרשום במערכת החט\"ל.")
                sup_rows = conn.execute("SELECT entity_name, phone, access_key FROM access_keys WHERE role='supplier' ORDER BY entity_name").fetchall()
                sup_names = [r["entity_name"] for r in sup_rows]
                if not sup_names:
                    st.info("טרם נטענו ספקים למערכת.")
                else:
                    sel_sup = st.selectbox("בחר את שם החברה שלך:", sup_names)
                    verify_phone = st.text_input("הזן את מספר הטלפון הנייד של איש הקשר (או מפתח הגישה הנוכחי):", placeholder="למשל: 0546966537")
                    new_pwd = st.text_input("בחר סיסמה חדשה (לפחות 4 תווים):", type="password")
                    if st.button("עדכן סיסמה חדשה ושלח דיווח למנהל המערכת ✅", type="primary", use_container_width=True):
                        sup_rec = conn.execute("SELECT * FROM access_keys WHERE role='supplier' AND entity_name=?", (sel_sup,)).fetchone()
                        db_phone = clean_display_phone(sup_rec["phone"])
                        if not db_phone:
                            r_ord_p = conn.execute("SELECT supplier_phone FROM orders WHERE supplier_name=? AND supplier_phone!='' LIMIT 1", (sel_sup,)).fetchone()
                            if r_ord_p:
                                db_phone = clean_display_phone(r_ord_p["supplier_phone"])
                        inp_phone = clean_display_phone(verify_phone)
                        is_valid_auth = (
                            (db_phone and inp_phone == db_phone)
                            or (clean_str(verify_phone).upper() == sup_rec["access_key"].upper())
                        )
                        if not is_valid_auth:
                            st.error("אימות נכשל: מספר הטלפון או מפתח הגישה אינם תואמים לרשום במערכת עבור ספק זה.")
                        elif len(clean_str(new_pwd)) < 4:
                            st.warning("נא לבחור סיסמה בת 4 תווים לפחות.")
                        else:
                            update_supplier_password(conn, sel_sup, clean_str(new_pwd), changed_by="איפוס עצמי במסך כניסה")
                            st.success(f"✅ הסיסמה של '{sel_sup}' עודכנה בהצלחה! מנהל המערכת קיבל התראה. כעת ניתן להתחבר בלשונית הכניסה.")

        st.markdown('<div class="watermark">Powered by BEN HUR</div>', unsafe_allow_html=True)


def render_link_verification_gate(conn, user):
    """מסך אימות דו-שלבי (2FA) לספק שנכנס דרך קישור וואטסאפ - מונע דליפת מידע אם הקישור הועבר הלאה."""
    _, center, _ = st.columns([0.8, 2.2, 0.8])
    with center:
        st.markdown(f"""
        <div class="header-box">
            <div class="header-title">🛡️ אימות אבטחה לאיש קשר - {user['entity_name']}</div>
            <div class="header-sub">הגנה מפני דליפת מידע: הצגת ההזמנות מורשית לאיש הקשר של הספק בלבד</div>
        </div>""", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("##### 📱 אימות זהות מהיר (חד-פעמי לחיבור זה)")
            st.info(
                "כדי להגן על סודיות ההזמנות ולמנוע חשיפת מידע לגורם שאינו מורשה, "
                "אנא הזינו את **4 הספרות האחרונות של מספר הטלפון הנייד** של איש הקשר הרשום במערכת (או את הסיסמה האישית שלכם)."
            )
            pin_inp = st.text_input("4 ספרות אחרונות של הטלפון הנייד (או סיסמה אישית):", max_chars=20, placeholder="למשל: 6537")
            c1, c2 = st.columns([2, 1])
            with c1:
                if st.button("אמת זהות והצג הזמנות 🔓", type="primary", use_container_width=True):
                    if verify_supplier_pin(conn, user, pin_inp):
                        st.session_state.link_verified = True
                        st.rerun()
                    else:
                        st.session_state.failed_attempts += 1
                        st.error("הספרות שהוזנו אינן תואמות לטלפון איש הקשר של הספק.")
            with c2:
                if st.button("יציאה למסך ראשי 🚪", use_container_width=True):
                    st.session_state.user = None
                    st.query_params.clear()
                    st.rerun()


def render_top_bar(conn, user):
    contact_str = clean_str(user.get("contact_person", ""))
    if user["role"] == "supplier" and not contact_str:
        r_c = conn.execute(
            "SELECT contact_person FROM orders WHERE supplier_name=? AND contact_person != '' LIMIT 1",
            (user["entity_name"],),
        ).fetchone()
        if r_c:
            contact_str = clean_str(r_c["contact_person"])

    if user["role"] == "supplier":
        sub_text = f"👤 איש קשר מורשה: {contact_str}" if contact_str else "פורטל עדכון סטטוס הזמנות ספק"
    elif user["role"] == "admin":
        sub_text = "מחובר בהרשאת: מנהל מערכת ראשי (גישה מלאה לכל התאים ולכל המדורים)"
    else:
        mgr_scope = user.get("assigned_manager", "ALL")
        sub_text = f"מחובר בהרשאת מדור | שיוך אוטומטי להזמנות: {mgr_scope}"

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
            st.session_state.link_verified = False
            st.session_state.pending_admin_changes = None
            st.query_params.clear()
            st.rerun()


# ---------- 6ב. ממשק מנהל מערכת ומדורים ----------
def render_staff(conn, user):
    is_admin = (user["role"] == "admin")

    if USE_PG:
        st.success("🟢 מחובר למסד הנתונים הקבוע בענן (Neon PostgreSQL) – כל ההזמנות, השיוכים ויומני האבטחה שמורים ומגובים.")
    else:
        st.warning("⚠️ המערכת עובדת עם מסד נתונים זמני. הגדירו DATABASE_URL של Neon ב-Secrets לחיבור קבוע.")

    # התראות אבטחה ושינויי סיסמאות ספקים למנהל המערכת
    if is_admin:
        unread_logs = conn.execute(
            "SELECT * FROM security_logs WHERE is_read=0 AND event_type='החלפת סיסמת ספק' ORDER BY id DESC"
        ).fetchall()
        if unread_logs:
            with st.container(border=True):
                st.warning(f"🔔 **התראת אבטחה למנהל המערכת – {len(unread_logs)} ספקים החליפו סיסמה לאחרונה:**")
                for lg in unread_logs:
                    st.markdown(
                        f"• **{lg['event_time']}** | ספק: **{lg['actor_name']}** | {lg['details']} | "
                        f"🔑 סיסמה חדשה שהוגדרה: `{lg['new_credential']}`"
                    )
                if st.button("✔️ סמן התראות כנקראו", key="ack_sec_logs"):
                    conn.execute("UPDATE security_logs SET is_read=1 WHERE event_type='החלפת סיסמת ספק'")
                    conn.commit()
                    st.rerun()

    tabs_list = [
        "📊 הזמנות, פיגורים ומענה",
        "💬 שיגור וואטסאפ למדור",
        "📥 טעינת אקסל (VLOOKUP חכם)",
    ]
    if is_admin:
        tabs_list.append("🔐 ניהול אבטחה, סיסמאות ספקים וגיבוי (Admin)")

    tabs = st.tabs(tabs_list)
    with tabs[0]:
        render_orders_tab(conn, user)
    with tabs[1]:
        render_whatsapp_tab(conn, user)
    with tabs[2]:
        render_upload_tab(conn, user)
    if is_admin and len(tabs) > 3:
        with tabs[3]:
            render_security_admin_tab(conn, user)


def get_scoped_orders_df(conn, user):
    """מחזיר את ההזמנות בהתאם להרשאה: מנהל רואה הכל, מדור רואה אוטומטית רק את ההזמנות המשויכות אליו."""
    mgr_scope = user.get("assigned_manager", "ALL")
    if user["role"] == "admin" or mgr_scope == "ALL":
        df = query_df(conn, "SELECT * FROM orders ORDER BY needs_attention DESC, supplier_name, order_number")
    else:
        df = query_df(
            conn,
            "SELECT * FROM orders WHERE order_manager=? ORDER BY needs_attention DESC, supplier_name, order_number",
            (mgr_scope,),
        )
    return enrich_orders_df(df)


def render_orders_tab(conn, user):
    is_admin = (user["role"] == "admin")
    df = get_scoped_orders_df(conn, user)
    if df.empty:
        st.info("אין הזמנות המשויכות למדור זה כרגע. עבור ללשונית 'טעינת אקסל' להעלאת קובץ.")
        return

    # סינון לפי מנהל ההזמנה (מדור) עבור מנהל המערכת
    if is_admin:
        f_mgr1, f_mgr2 = st.columns([1.2, 2.8])
        with f_mgr1:
            selected_mgr = st.selectbox("🎯 סנן לפי מנהל ההזמנה (מדור):", ["כל המדורים"] + MANAGER_OPTIONS)
        if selected_mgr != "כל המדורים":
            df = df[df["order_manager"] == selected_mgr].copy()

    overdue_mask = df["delay_days_num"].fillna(0) > 0
    weekly_updated_count = int(df["weekly_status_display"].astype(str).str.contains("עודכן השבוע").sum())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric('סה"כ שורות הזמנה במדור', len(df))
    k2.metric("שורות בפיגור מתאריך המקור", int(overdue_mask.sum()))
    k3.metric("🟢 עודכנו השבוע ע\"י ספק", weekly_updated_count)
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
        render_staff_cards(conn, view, is_admin, user)
    else:
        render_staff_table(conn, view, is_admin, user)

    st.download_button(
        "📥 הורד דוח אקסל מלא (כולל מנהל הזמנה, פיגור בימים וסטטוס שבועי)",
        data=export_excel(df), file_name="suppliers_updated.xlsx", use_container_width=True,
    )

    if is_admin:
        render_admin_delete_panel(conn, df, user["entity_name"])


def render_staff_cards(conn, view, is_admin, user):
    for _, r in view.iterrows():
        icon = "⚠️" if r["needs_attention"] == 1 else "📦"
        with st.expander(f"{icon} [{r['order_manager']}] {r['supplier_name']} | הזמנה {r['order_number']} שורה {r['line_number']} | {r['delay_days_display']}"):
            st.markdown(f"""
            <div class="order-card-header">
                <strong>מנהל הזמנה:</strong> {r['order_manager']} | <strong>פריט:</strong> {r['item_description']} | <strong>מק"ט:</strong> {r['part_number']}<br>
                <strong>⏳ פיגור:</strong> {r['delay_days_display']} | <strong>📅 סטטוס שבועי:</strong> {r['weekly_status_display']} | <strong>👤 איש קשר:</strong> {r['contact_person'] or '-'} ({r['supplier_phone'] or 'חסר'})
            </div>""", unsafe_allow_html=True)
            st.markdown(f"🔒 **סטטוס ספק:** `{r['supplier_status']}` | **צפי ספק:** `{r['expected_date'] or r['due_date']}`")
            st.markdown(f"🔒 **תגובת ספק:** {r['supplier_note'] or 'אין הערות'}")

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
                        delete_orders_by_ids(conn, [r["id"]], user["entity_name"])
                        st.rerun()


def compute_table_diff(orig_df, edited_df, compare_cols):
    """מחשב אילו תאים בדיוק שונו בטבלה כדי להציג התראה לאישור מנהל לפני שמירה."""
    orig_by_id = orig_df.set_index("id")
    changes = []
    for _, row in edited_df.iterrows():
        oid = row["id"]
        if oid not in orig_by_id.index:
            continue
        orig_row = orig_by_id.loc[oid]
        for col_name, heb_label in compare_cols.items():
            old_val = clean_str(orig_row[col_name])
            new_val = clean_str(row[col_name])
            if old_val != new_val:
                changes.append({
                    "id": int(oid),
                    "הזמנה ושורה": f"{row['order_number']} / {row['line_number']}",
                    "ספק": row["supplier_name"],
                    "שדה שהשתנה": heb_label,
                    "ערך קודם": old_val or "(ריק)",
                    "ערך חדש": new_val or "(ריק)",
                })
    return changes


def render_staff_table(conn, view, is_admin, user):
    if is_admin:
        st.caption(
            "🔓 **מצב מנהל מערכת (Full Access):** כל התאים בטבלה פתוחים לעריכה מלאה (כולל תאי ספק, הזמנה ומנהל הזמנה). "
            "לחיצה על 'שמור' תציג חלונית התראה לאישור השינויים לפני כתיבה למסד."
        )
    else:
        st.caption('🔒 **אבטחת מידע למדור:** עמודות דיווח הספק נעולות. המדור רשאי לעדכן מנהל הזמנה, איש קשר, טלפון ומענה מדור.')

    view = view.copy()
    view["attention"] = [
        attention_reason(r["supplier_status"], r["supplier_note"], r["expected_date"], r["due_date"]) if r["needs_attention"] == 1 else ""
        for _, r in view.iterrows()
    ]
    if is_admin:
        view["delete_row"] = False

    base_cols = [
        "id", "order_manager", "supplier_name", "contact_person", "supplier_phone",
        "order_number", "line_number", "part_number", "item_description",
        "due_date", "delay_days_display", "weekly_status_display",
        "supplier_status", "expected_date", "supplier_note", "mador_response", "attention",
    ]
    cols = base_cols + (["delete_row"] if is_admin else [])

    T = st.column_config.TextColumn
    S = st.column_config.SelectboxColumn
    # למנהל מערכת (is_admin=True) כלל התאים פתוחים (disabled=False)! למדור רגיל תאי הספק נעולים.
    lock_for_mador = not is_admin

    col_cfg = {
        "id": None,
        "order_manager": S("🎯 מנהל ההזמנה", options=MANAGER_OPTIONS, required=True, width="small"),
        "supplier_name": T("חברה", disabled=lock_for_mador, width="medium"),
        "contact_person": T("👤 איש קשר", width="medium"),
        "supplier_phone": T("📞 מספר טלפון", width="medium"),
        "order_number": T("מספר הזמנה", disabled=lock_for_mador, width="medium"),
        "line_number": T("שורה", disabled=lock_for_mador, width="small"),
        "part_number": T('מק"ט', width="medium"),
        "item_description": T("שם פריט", width="large"),
        "due_date": T("תאריך מקורי", width="small"),
        "delay_days_display": T("⏳ פיגור בימים", disabled=True, width="medium"),
        "weekly_status_display": T("📅 סטטוס שבועי", disabled=True, width="medium"),
        "supplier_status": S("סטטוס עדכני", options=STATUS_OPTIONS, disabled=lock_for_mador, width="medium") if is_admin else T("🔒 סטטוס עדכני", disabled=True, width="medium"),
        "expected_date": T("צפי ספק", disabled=lock_for_mador, width="small"),
        "supplier_note": T("תגובת ספק", disabled=lock_for_mador, width="large"),
        "mador_response": T("✍️ מענה מדור לספק", width="large"),
        "attention": T("⚠️ סיבת סימון", disabled=True, width="large"),
    }
    if is_admin:
        col_cfg["delete_row"] = st.column_config.CheckboxColumn("🗑️ מחק", default=False, width="small")

    edited = st.data_editor(
        view[cols],
        column_config=col_cfg,
        use_container_width=True,
        hide_index=True,
        key="staff_main_editor",
    )

    compare_map = {
        "order_manager": "מנהל ההזמנה",
        "supplier_name": "חברה",
        "contact_person": "איש קשר",
        "supplier_phone": "מספר טלפון",
        "order_number": "מספר הזמנה",
        "line_number": "שורה",
        "part_number": 'מק"ט',
        "item_description": "שם פריט",
        "due_date": "תאריך מקורי",
        "supplier_status": "סטטוס עדכני",
        "expected_date": "צפי ספק",
        "supplier_note": "תגובת ספק",
        "mador_response": "מענה מדור",
    }

    btn_col1, btn_col2 = st.columns([2, 1]) if is_admin else (st.container(), None)
    with btn_col1:
        if st.button("💾 בדוק ושמור שינויים בטבלה", type="primary", use_container_width=True):
            diffs = compute_table_diff(view, edited, compare_map)
            if not diffs:
                st.info("לא זוהו שינויים בנתוני הטבלה.")
            else:
                st.session_state.pending_admin_changes = {
                    "diffs": diffs,
                    "rows": edited.to_dict(orient="records"),
                }

    if is_admin and btn_col2 is not None:
        with btn_col2:
            to_delete = edited[edited["delete_row"] == True]["id"].tolist()
            if st.button(f"🗑️ מחק שורות שסומנו ({len(to_delete)})", use_container_width=True):
                if not to_delete:
                    st.warning("לא סומנו שורות למחיקה בטבלה.")
                else:
                    delete_orders_by_ids(conn, to_delete, user["entity_name"])
                    st.success(f"נמחקו {len(to_delete)} שורות הזמנה בהצלחה!")
                    st.rerun()

    # חלונית התראה ואישור לפני ביצוע שינוי (Confirmation Prompt)
    pending = st.session_state.get("pending_admin_changes")
    if pending:
        with st.container(border=True):
            st.warning(f"⚠️ **התראת אישור שינוי נתונים ({len(pending['diffs'])} שדות שונו):** אנא בדוק ואשר את השינויים הבאים לפני שמירה למסד הנתונים:")
            st.dataframe(pd.DataFrame(pending["diffs"]).drop(columns=["id"], errors="ignore"), use_container_width=True, hide_index=True)
            ca1, ca2 = st.columns(2)
            with ca1:
                if st.button("✅ אני מאשר – שמור שינויים למסד הנתונים", type="primary", use_container_width=True):
                    now = datetime.now().strftime("%d/%m/%Y %H:%M")
                    for r in pending["rows"]:
                        phone = clean_display_phone(r["supplier_phone"])
                        contact = clean_str(r["contact_person"])
                        part = clean_part_num(r["part_number"])
                        ord_num = clean_id_num(r["order_number"])
                        line_num = clean_id_num(r["line_number"]) or "10"
                        mgr = r["order_manager"] if r["order_manager"] in MANAGER_OPTIONS else 'נמ"ר'
                        flag = needs_attention(r["supplier_status"], r["supplier_note"], r["expected_date"], r["due_date"])
                        if r["mador_response"]:
                            flag = False
                        conn.execute(
                            """UPDATE orders
                               SET order_manager=?, supplier_name=?, contact_person=?, supplier_phone=?,
                                   order_number=?, line_number=?, part_number=?, item_description=?,
                                   due_date=?, supplier_status=?, expected_date=?, supplier_note=?,
                                   mador_response=?, needs_attention=?, last_updated=?
                               WHERE id=?""",
                            (
                                mgr, clean_str(r["supplier_name"]), contact, phone,
                                ord_num, line_num, part, clean_str(r["item_description"]),
                                clean_str(r["due_date"]), r["supplier_status"], clean_str(r["expected_date"]),
                                clean_str(r["supplier_note"]), clean_str(r["mador_response"]),
                                int(flag), now, int(r["id"]),
                            ),
                        )
                        if phone or contact:
                            get_or_create_key(conn, r["supplier_name"], contact, phone)
                    conn.commit()
                    log_security_event(
                        conn,
                        "עריכת טבלה מאושרת",
                        user["entity_name"],
                        f"אושרו ונשמרו {len(pending['diffs'])} שינויים בטבלת ההזמנות.",
                    )
                    st.session_state.pending_admin_changes = None
                    st.success("✅ השינויים אושרו ונשמרו בהצלחה למסד הנתונים!")
                    st.rerun()
            with ca2:
                if st.button("❌ בטל שינויים", use_container_width=True):
                    st.session_state.pending_admin_changes = None
                    st.rerun()


def render_admin_delete_panel(conn, df, actor_name):
    st.divider()
    with st.expander("🗑️ ניהול מחיקת הזמנות שהסתיימו / קיבלו מענה (הרשאת מנהל מערכת בלבד)"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**1. מחיקת הזמנה שלמה או שורות נבחרות:**")
            df_opts = df.copy()
            df_opts["label"] = [
                f"[{r['order_manager']}] הזמנה {r['order_number']} | שורה {r['line_number']} | {r['supplier_name']} ({r['supplier_status']})"
                for _, r in df_opts.iterrows()
            ]
            label_to_id = dict(zip(df_opts["label"], df_opts["id"]))
            selected_labels = st.multiselect("בחר הזמנות / שורות למחיקה:", options=df_opts["label"].tolist())
            if selected_labels and st.button(f"🗑️ מחק לצמיתות {len(selected_labels)} שורות שנבחרו", key="del_selected_admin"):
                ids = [label_to_id[lbl] for lbl in selected_labels]
                delete_orders_by_ids(conn, ids, actor_name)
                st.success(f"נמחקו {len(ids)} שורות מהמערכת!")
                st.rerun()

        with c2:
            st.markdown("**2. ניקוי מהיר לפי סטטוס (סופק / טופל):**")
            done_ids = df[df["supplier_status"].astype(str).str.strip() == DONE_STATUS]["id"].tolist()
            st.write(f"שורות המסומנות כעת בסטטוס **'{DONE_STATUS}'**: `{len(done_ids)}` שורות.")
            confirm_done = st.checkbox("אני מאשר מחיקה של כל השורות שסופקו", key="confirm_del_done")
            if st.button(f"🧹 מחק את כל השורות שסופקו ({len(done_ids)})", disabled=not (confirm_done and done_ids)):
                delete_orders_by_ids(conn, done_ids, actor_name)
                st.success(f"נמחקו {len(done_ids)} שורות שסופקו!")
                st.rerun()


def export_excel(df):
    df_enriched = enrich_orders_df(df)
    export_df = pd.DataFrame({heb: df_enriched[col] for heb, col in EXPORT_MAP.items()})
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Sheet")
    return out.getvalue()


# ---------- 6ג. לשונית וואטסאפ (ממודרת אוטומטית לפי מנהל ההזמנה / המדור המחובר) ----------
def build_whatsapp_message(conn, sup, sender, mgr_scope="ALL"):
    name = sup["supplier_name"]
    if mgr_scope == "ALL":
        rows = conn.execute(
            "SELECT order_number, line_number, item_description, due_date, order_manager FROM orders "
            "WHERE supplier_name=? AND TRIM(COALESCE(supplier_status, '')) != ?",
            (name, DONE_STATUS),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT order_number, line_number, item_description, due_date, order_manager FROM orders "
            "WHERE supplier_name=? AND order_manager=? AND TRIM(COALESCE(supplier_status, '')) != ?",
            (name, mgr_scope, DONE_STATUS),
        ).fetchall()

    lines = "\n".join(
        f"• הזמנה {clean_id_num(o['order_number'])} שורה {clean_id_num(o['line_number'])} - {o['item_description']} (יעד: {o['due_date'] or '-'})"
        for o in rows[:12]
    )
    greeting = sup["contact_person"] or name
    phone_clean = clean_display_phone(sup["phone"])
    last4_hint = f" (אימות כניסה: 4 ספרות אחרונות של הטלפון שלך - {phone_clean[-4:]})" if len(phone_clean) >= 4 else ""
    link = f"{APP_URL}/?key={sup['access_key']}"
    return (
        f"היי {greeting}, מה נשמע?\n"
        f"זה {sender} מהחט\"ל. אני עובר על דו\"ח ההזמנות הפתוחות שלנו מול {name} וראיתי שיש לנו פער בלוח הזמנים בפריטים הבאים:\n"
        f"{lines}\n\n"
        f"כדי לעדכן סטטוס וצפי אספקה בלחיצה אחת, היכנסו לקישור המאובטח שלכם:\n"
        f"{link}\n"
        f"(מפתח גישה: {sup['access_key']}{last4_hint})\n"
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


def render_whatsapp_tab(conn, user):
    mgr_scope = user.get("assigned_manager", "ALL")
    if user["role"] == "admin":
        sel_mgr = st.selectbox("🎯 בחר מדור לשליחת וואטסאפ לספקים שלו:", ["ALL (כל המדורים)"] + MANAGER_OPTIONS, key="wa_mgr_sel")
        if not sel_mgr.startswith("ALL"):
            mgr_scope = sel_mgr
        else:
            mgr_scope = "ALL"

    st.markdown(f"##### 💬 מערך שיגור הודעות וואטסאפ לספקים (שיוך הזמנות: {mgr_scope})")

    if mgr_scope == "ALL":
        sup_sql = '''
            SELECT
                u.entity_name AS supplier_name,
                COALESCE(NULLIF(MAX(o.contact_person), ''), NULLIF(u.contact_person, ''), '') AS contact_person,
                COALESCE(NULLIF(MAX(o.supplier_phone), ''), NULLIF(u.phone, ''), '') AS phone,
                u.access_key,
                COUNT(o.id) AS total_orders,
                COALESCE(CAST(SUM(CASE WHEN TRIM(COALESCE(o.supplier_status, '')) != 'סופק' THEN 1 ELSE 0 END) AS INTEGER), 0) AS open_or_delayed_orders
            FROM access_keys u
            LEFT JOIN orders o ON o.supplier_name = u.entity_name
            WHERE u.role = 'supplier' AND COALESCE(u.is_locked, 0) = 0
            GROUP BY u.entity_name, u.access_key, u.contact_person, u.phone
            ORDER BY open_or_delayed_orders DESC, u.entity_name
        '''
        df_sups = query_df(conn, sup_sql)
    else:
        sup_sql = '''
            SELECT
                u.entity_name AS supplier_name,
                COALESCE(NULLIF(MAX(o.contact_person), ''), NULLIF(u.contact_person, ''), '') AS contact_person,
                COALESCE(NULLIF(MAX(o.supplier_phone), ''), NULLIF(u.phone, ''), '') AS phone,
                u.access_key,
                COUNT(o.id) AS total_orders,
                COALESCE(CAST(SUM(CASE WHEN TRIM(COALESCE(o.supplier_status, '')) != 'סופק' THEN 1 ELSE 0 END) AS INTEGER), 0) AS open_or_delayed_orders
            FROM access_keys u
            INNER JOIN orders o ON o.supplier_name = u.entity_name AND o.order_manager = ?
            WHERE u.role = 'supplier' AND COALESCE(u.is_locked, 0) = 0
            GROUP BY u.entity_name, u.access_key, u.contact_person, u.phone
            ORDER BY open_or_delayed_orders DESC, u.entity_name
        '''
        df_sups = query_df(conn, sup_sql, (mgr_scope,))

    if df_sups.empty:
        st.info(f"לא נמצאו ספקים עם הזמנות המשויכות למדור '{mgr_scope}'.")
        return

    df_sups["phone"] = df_sups["phone"].apply(clean_display_phone)
    df_sups["wa_ready"] = df_sups["phone"].apply(lambda p: "✅ תקין" if format_wa_phone(p) else "❌ חסר נייד")

    with st.container(border=True):
        c1, c2 = st.columns([2, 1])
        with c1:
            filter_mode = st.radio("1️⃣ בחר אוכלוסיית ספקים לשליחה:", [
                "📱 ספקים עם מספר נייד תקין לוואטסאפ (מומלץ לשליחה מיידית)",
                "🔴 כל הספקים עם הזמנות פתוחות / בעיכוב במדור זה",
                "📋 כל הספקים של מדור זה",
            ])
        sender = c2.text_input("שם השולח בהודעה:", value=user["entity_name"].split("-")[0].strip())

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
        text = urllib.parse.quote(build_whatsapp_message(conn, sup, sender, mgr_scope))
        items.append((sup["supplier_name"], sup["contact_person"], sup["phone"], f"https://wa.me/{wa_phone}?text={text}"))
        script_targets.append((sup["supplier_name"], sup["contact_person"],
                               f"https://web.whatsapp.com/send?phone={wa_phone}&text={text}"))

    if not chosen.empty:
        st.markdown(f"##### 3️⃣ לוח שיגור ישיר ({len(items)} ספקים עם מספר נייד תקין):")
        if not items:
            st.warning("לספקים שסימנת אין מספר נייד תקין.")
        else:
            render_launcher(items)
            st.download_button(
                "🤖 הורד רובוט שליחה אוטומטי מלא למחשב (שולח לבד ב-Chrome בלי ללחוץ Send)",
                data=build_selenium_script(script_targets).encode("utf-8"),
                file_name="auto_send_sapakim.py", mime="text/x-python", use_container_width=True,
            )


# ---------- 6ד. טעינת אקסל (VLOOKUP חכם + שיוך מנהל הזמנה) ----------
def render_upload_tab(conn, user):
    st.markdown("##### 📥 טעינת קובץ אקסל (`suppliers.xlsx`) - מנגנון VLOOKUP חכם למסד הנתונים")
    st.info(
        "💡 **סנכרון חכם (VLOOKUP):**\n"
        "• קולט אוטומטית את עמודת **'מנהל ההזמנה'** (נמ\"ר / מרכבה / איתן / מנה\"ר) או מזהה אותה מתוך שם הפריט.\n"
        "• שומר על תגובות הספקים, הצפי ומענה המדור הקיימים במסד הנתונים מבלי לדרוס אותם!"
    )
    default_mgr = st.selectbox(
        "ברירת מחדל עבור 'מנהל ההזמנה' (לשורות שבהן לא צוין מדור מפורש באקסל):",
        MANAGER_OPTIONS,
        index=0,
    )
    uploaded = st.file_uploader("בחר קובץ Excel או CSV", type=["xlsx", "xls", "csv"])
    if uploaded and st.button("טען וסנכרן הזמנות למסד הנתונים (ללא מחיקת קיימים) ⚡", type="primary", use_container_width=True):
        df = pd.read_csv(uploaded, dtype=str) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded, dtype=str)
        df.columns = [str(c).strip() for c in df.columns]
        result = import_orders(conn, df, default_mgr, user["entity_name"])
        st.success(
            f"✅ הסנכרון הושלם! עובדו {result['rows']} שורות הזמנה "
            f"({result['contacts']} עם איש קשר, {result['phones']} עם טלפון מלא)."
        )


def import_orders(conn, df, default_mgr='נמ"ר', actor_name="מערכת"):
    cols = df.columns.tolist()
    col = {key: find_col(cols, aliases) for key, aliases in EXCEL_ALIASES.items()}

    def get(row, key):
        return clean_str(row[col[key]]) if col[key] else ""

    rows = contacts = phones = 0
    for _, r in df.iterrows():
        order_num = clean_id_num(get(r, "order"))
        if not order_num:
            continue

        line_num = clean_id_num(get(r, "line")) or "10"
        part_num = clean_part_num(get(r, "part"))
        qty_num = clean_id_num(get(r, "qty")) or "1"
        desc_str = get(r, "desc")
        raw_mgr = get(r, "manager") or default_mgr
        mgr_val = normalize_manager(raw_mgr, desc_str)

        supplier = get(r, "supplier") or "ספק כללי"
        contact = get(r, "contact")
        phone = clean_display_phone(r[col["phone"]]) if col["phone"] else ""
        internal = get(r, "internal")

        if not phone or not contact:
            mem = conn.execute("SELECT phone, contact_person FROM access_keys WHERE role='supplier' AND entity_name=?", (supplier,)).fetchone()
            if mem:
                phone = phone or clean_display_phone(mem["phone"])
                contact = contact or mem["contact_person"]
        contacts += bool(contact)
        phones += bool(phone)

        get_or_create_key(conn, supplier, contact, phone)

        due_val = format_date_il(get(r, "due").split(" ")[0])
        exp_val = format_date_il(get(r, "expected").split(" ")[0]) or due_val
        note_val = clean_supplier_note(get(r, "note"))

        data = {
            "order_number": order_num,
            "line_number": line_num,
            "order_manager": mgr_val,
            "part_number": part_num,
            "item_description": desc_str,
            "quantity": qty_num,
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
    log_security_event(conn, "טעינת אקסל VLOOKUP", actor_name, f"נטענו/סונכרנו {rows} שורות הזמנה.")
    return {"rows": rows, "contacts": contacts, "phones": phones}


# ---------- 6ה. לשונית אבטחה, בקרה, סיסמאות ספקים וגיבוי (Admin בלבד) ----------
def render_security_admin_tab(conn, user):
    st.markdown("##### 🔐 מרכז בקרת אבטחה, ניהול הרשאות ספקים ויומן אירועים (Admin בלבד)")

    c_bkp1, c_bkp2 = st.columns([2, 1])
    with c_bkp1:
        st.info("📦 **גיבוי מערכת מלא בלחיצת כפתור:** מוריד קובץ Excel הכולל את כל ההזמנות, טבלת הספקים והסיסמאות, ויומן האבטחה המלא.")
    with c_bkp2:
        st.download_button(
            "📥 הורד גיבוי מלא של כל מסד הנתונים (Full Backup)",
            data=export_full_backup_excel(conn),
            file_name=f"SAPakim_Full_Backup_{date.today().strftime('%d_%m_%Y')}.xlsx",
            type="primary",
            use_container_width=True,
        )

    st.divider()
    st.markdown("###### 🔑 ניהול ספקים, איפוס סיסמאות, החלפת קישור ונעילת גישה (Kill Switch)")
    df_keys = query_df(
        conn,
        """SELECT entity_name, contact_person, phone, access_key, custom_password, last_pwd_change, is_locked
           FROM access_keys WHERE role='supplier' ORDER BY entity_name""",
    )
    if not df_keys.empty:
        df_keys["phone"] = df_keys["phone"].apply(clean_display_phone)
        df_keys["is_locked"] = df_keys["is_locked"].apply(lambda x: bool(int(x or 0)))

        edited_keys = st.data_editor(
            df_keys,
            column_config={
                "entity_name": st.column_config.TextColumn("חברה / ספק", disabled=True, width="medium"),
                "contact_person": st.column_config.TextColumn("👤 איש קשר מורשה", width="medium"),
                "phone": st.column_config.TextColumn("📞 טלפון לאימות כניסה", width="medium"),
                "access_key": st.column_config.TextColumn("🔗 מפתח קישור (Magic Key)", disabled=True, width="small"),
                "custom_password": st.column_config.TextColumn("🔑 סיסמת ספק אישית (ערוך לאיפוס)", width="medium"),
                "last_pwd_change": st.column_config.TextColumn("🕒 מועד החלפת סיסמה", disabled=True, width="medium"),
                "is_locked": st.column_config.CheckboxColumn("⛔ נעל גישת ספק", width="small"),
            },
            use_container_width=True,
            hide_index=True,
            key="admin_keys_editor",
        )

        ck1, ck2 = st.columns(2)
        with ck1:
            if st.button("💾 שמור עדכוני סיסמאות, טלפונים ונעילות ספקים", type="primary", use_container_width=True):
                now = datetime.now().strftime("%d/%m/%Y %H:%M")
                for _, r in edited_keys.iterrows():
                    conn.execute(
                        """UPDATE access_keys
                           SET contact_person=?, phone=?, custom_password=?, is_locked=?, last_pwd_change=?
                           WHERE role='supplier' AND entity_name=?""",
                        (
                            clean_str(r["contact_person"]),
                            clean_display_phone(r["phone"]),
                            clean_str(r["custom_password"]),
                            1 if r["is_locked"] else 0,
                            now if clean_str(r["custom_password"]) else r["last_pwd_change"],
                            r["entity_name"],
                        ),
                    )
                conn.commit()
                log_security_event(conn, "עדכון הרשאות ספקים", user["entity_name"], "עודכנו סיסמאות / נעילות בטבלת הספקים.")
                st.success("הגדרות האבטחה והסיסמאות של הספקים נשמרו!")
                st.rerun()

        with ck2:
            sup_to_regen = st.selectbox("בחר ספק להחלפת קישור (מבטל קישור ישן אם דלף):", df_keys["entity_name"].tolist())
            if st.button("🔄 החלף קישור אישי (Regenerate Link) לספק זה", use_container_width=True):
                new_k = regenerate_supplier_key(conn, sup_to_regen, user["entity_name"])
                st.success(f"הקישור הישן בוטל! מפתח הקישור החדש של '{sup_to_regen}' הוא: {new_k}")
                st.rerun()

    st.divider()
    st.markdown("###### 📜 יומן אירועי אבטחה והחלפות סיסמה (Audit Log)")
    df_logs = query_df(conn, "SELECT event_time, event_type, actor_name, details, new_credential FROM security_logs ORDER BY id DESC LIMIT 100")
    if df_logs.empty:
        st.caption("אין אירועים מתועדים ביומן.")
    else:
        st.dataframe(
            df_logs.rename(columns={
                "event_time": "זמן אירוע",
                "event_type": "סוג פעולה",
                "actor_name": "מבצע הפעולה",
                "details": "פירוט",
                "new_credential": "סיסמה / מפתח חדש",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ---------- 6ו. מסך ספק (ללא איש קשר בשורות, תאריך מקורי נעול, ואפשרות החלפת סיסמה) ----------
def render_supplier(conn, user):
    st.markdown(f"##### 📦 ההזמנות הפתוחות של: {user['entity_name']}")
    df = query_df(conn, "SELECT * FROM orders WHERE supplier_name=?", (user["entity_name"],))
    df["_line"] = pd.to_numeric(df["line_number"], errors="coerce")
    df = df.sort_values(["order_number", "_line"]).drop(columns="_line")

    # אפשרות לספק להחליף סיסמה מתוך הפורטל שלו (שולח התראה למנהל המערכת)
    with st.expander("🔑 הגדרות אבטחה: החלפת סיסמה אישית"):
        sp1, sp2 = st.columns([2, 1])
        new_sup_pwd = sp1.text_input("הגדר סיסמה אישית חדשה לחשבונך:", type="password", key="sup_self_pwd")
        with sp2:
            st.write("")
            if st.button("שמור סיסמה חדשה 🔒", use_container_width=True):
                if len(clean_str(new_sup_pwd)) < 4:
                    st.warning("נא להזין סיסמה בת 4 תווים לפחות.")
                else:
                    update_supplier_password(conn, user["entity_name"], clean_str(new_sup_pwd), changed_by="החלפה עצמית בפורטל הספק")
                    st.success("הסיסמה האישית שלך עודכנה בהצלחה!")

    if df.empty:
        st.warning("לא נמצאו הזמנות פתוחות המשויכות אליכם כרגע.")
        return

    df = enrich_orders_df(df)

    if st.session_state.submitted:
        render_done_screen(df)
        return

    with st.expander("⚡ עדכון מהיר אוטומטי לכל השורות (לחץ כאן להחלת סטטוס או הערה גורפת על כל ההזמנות)"):
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
                    st.session_state[f"st_{r['id']}"] = new_s
                    st.session_state[f"nt_{r['id']}"] = new_n
                conn.commit()
                st.success("העדכון הוחל אוטומטית על כל השורות!")
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
                    "📅 תאריך אספקה בתגובת ספק:",
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
            "order_number": T("🔒 מס' הזמנה", disabled=True, width="medium"),
            "line_number": T("🔒 שורה", disabled=True, width="small"),
            "part_number": T('🔒 מק"ט', disabled=True, width="medium"),
            "item_description": T("🔒 שם פריט", disabled=True, width="large"),
            "orig_due_str": T("🔒 תאריך מקורי", disabled=True, width="small"),
            "delay_days_display": T("⏳ פיגור בימים", disabled=True, width="medium"),
            "supplier_status": st.column_config.SelectboxColumn("✍️ סטטוס עדכני", options=STATUS_OPTIONS, required=True, width="medium"),
            "change_date": st.column_config.CheckboxColumn("📅 שנה תאריך", width="small"),
            "eta_date": st.column_config.DateColumn("📅 תאריך בתגובת ספק", format="DD/MM/YYYY", width="medium"),
            "no_eta": st.column_config.CheckboxColumn("❓ אין צפי", width="small"),
            "supplier_note": T("✍️ תגובת ספק", width="large"),
            "mador_response": T('🔒 מענה מדור חט"ל', disabled=True, width="large"),
        },
        use_container_width=True,
        hide_index=True,
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
    if st.button("✏️ עריכת התשובות", type="primary", use_container_width=True):
        st.session_state.submitted = False
        st.rerun()


# ==============================================================================
# פרק 7: נקודת כניסה ראשית של האפליקציה (Main Entry Point)
# ==============================================================================
def run_app(conn):
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("failed_attempts", 0)
    st.session_state.setdefault("submitted", False)
    st.session_state.setdefault("link_verified", False)
    st.session_state.setdefault("pending_admin_changes", None)

    url_key = st.query_params.get("key", "").strip().upper()
    if url_key and not st.session_state.user:
        user_obj, _ = authenticate_user(conn, url_key)
        if user_obj:
            st.session_state.user = user_obj
            # כניסה מקישור חיצוני של ספק דורשת אימות 4 ספרות אחרונות של טלפון איש הקשר!
            st.session_state.link_verified = (user_obj["role"] != "supplier")

    if not st.session_state.user:
        render_login(conn)
        st.stop()

    user = st.session_state.user
    if user["role"] == "supplier" and not st.session_state.link_verified:
        render_link_verification_gate(conn, user)
        st.stop()

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


if __name__ == "__main__":
    main()
