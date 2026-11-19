"""
================================================================================
מערכת SAPakim - פורטל ארגוני מאובטח לניהול ותיקוף הזמנות מול ספקים ומנהלי הזמנות
פותח ע"י: רועי בן חור (Powered by BEN HUR)
================================================================================
מבנה הקוד (7 פרקים מודולריים ומתועדים להעברה נוחה לאיש תוכנה):
- פרק 1: הגדרות מערכת, רשימת מנהלי הזמנה והרשאות שדות בצד השרת (Config & RBAC)
- פרק 2: שכבת עיצוב רספונסיבית + נעילת ניגודיות למניעת שיבוש Dark Mode בנייד (CSS)
- פרק 3: שכבת אבטחת מידע, הצפנת scrypt והגנת קלט/אקסל (Security & Crypto Engine)
- פרק 4: שכבת מסד הנתונים - Neon PostgreSQL / SQLite + מיגרציה אוטומטית (Database Layer)
- פרק 5: לוגיקה עסקית, מיזוג אקסל (VLOOKUP), קבצים מצורפים ווואטסאפ (Business Logic)
- פרק 6: מסכי המערכת לפי הרשאות (Login, Supplier, Staff - Mobile & Desktop)
- פרק 7: נקודת כניסה ראשית וניהול פג תוקף חיבור (Main Entry & Session Timeout)
================================================================================
"""

import hashlib
import hmac
import html
import logging
import os
import re
import secrets
import sqlite3
import urllib.parse
from datetime import datetime, timedelta
from io import BytesIO

import pandas as pd
import streamlit as st

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


# ==============================================================================
# פרק 1: הגדרות מערכת, מנהלי הזמנה והרשאות שדות בצד השרת (Config & Server RBAC)
# ==============================================================================

st.set_page_config(
    page_title="SAPakim - פורטל הזמנות חט\"ל",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

SESSION_TIMEOUT_MINUTES = 20
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 30
TOKEN_EXPIRY_DAYS = 14
MAX_ATTACHMENT_SIZE_MB = 5
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".xlsx"}
DEFAULT_PORTAL_URL = "https://sapakim-kukmcxaux8yf9tfjrygif9.streamlit.app"

SUPPLIER_STATUS_OPTIONS = [
    "טרם עודכן",
    "תקין - בייצור",
    "עיכוב בחומר גלם",
    "ממתין לשרטוט / מפרט טכני",
    "ממתין לבק\"מ / בחינה",
    "מוכן לאספקה / משלוח",
    "סופק"
]

ORDER_MANAGERS = ["שגיא", "פיראס", "סאקר", "אדי", "כללי"]

MANAGER_ALLOWED_FIELDS = {
    "part_number", "item_description", "quantity", "contact_person",
    "supplier_phone", "due_date", "internal_status", "mador_response",
    "needs_attention"
}

ROLE_ALLOWED_FIELDS = {
    "supplier": {"supplier_status", "expected_date", "supplier_note", "needs_attention"},
    "manager": MANAGER_ALLOWED_FIELDS,
    "mador": MANAGER_ALLOWED_FIELDS,
    "admin": {
        "order_manager", "order_number", "line_number", "part_number",
        "item_description", "quantity", "supplier_name", "contact_person",
        "supplier_phone", "due_date", "internal_status", "supplier_status",
        "expected_date", "supplier_note", "mador_response", "needs_attention"
    }
}

COLUMN_LABELS_HE = {
    "order_manager": "מנהל ההזמנה",
    "order_number": "מספר הזמנה",
    "line_number": "שורה",
    "part_number": "מק\"ט",
    "item_description": "תיאור פריט",
    "quantity": "כמות",
    "supplier_name": "ספק",
    "contact_person": "איש קשר",
    "supplier_phone": "טלפון ספק",
    "due_date": "תאריך יעד מקורי",
    "internal_status": "סטטוס פנימי",
    "supplier_status": "סטטוס ספק",
    "expected_date": "צפי אספקה מספק",
    "supplier_note": "הערת / בקשת ספק",
    "mador_response": "מענה מנהל ההזמנה",
    "needs_attention": "דרוש טיפול"
}

GENERIC_PHRASES_TO_CLEAN = [
    "כל השאר אבדוק ואעדכן",
    "כל השאר סופק",
    "אבדוק ואעדכן"
]


# ==============================================================================
# פרק 2: עיצוב רספונסיבי + נעילת ניגודיות מוחלטת (מונע באג Dark Mode בנייד)
# ==============================================================================

def inject_custom_css():
    """
    נועל את כל רכיבי הממשק (כפתורים, כרטיסיות נפתחות, תיבות קלט, התראות וקוד)
    לערכת צבעים בהירה עם ניגודיות חדה – גם כשהטלפון הנייד מוגדר על מצב כהה (Dark Mode).
    """
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700&display=swap');

        :root, html, body, .stApp, [data-testid="stAppViewContainer"] {
            color-scheme: light !important;
            font-family: 'Rubik', Arial, sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
            background: linear-gradient(180deg, #fffbeb 0%, #f8fafc 35%, #f1f5f9 100%) !important;
            color: #0f172a !important;
        }

        /* סרגל עליון בהיר וברור במקום שחור במצב כהה */
        header[data-testid="stHeader"] {
            background-color: rgba(255, 251, 235, 0.96) !important;
            border-bottom: 1px solid #fde68a !important;
            color: #0f172a !important;
        }
        header[data-testid="stHeader"] svg,
        header[data-testid="stHeader"] button {
            color: #0f172a !important;
            fill: #0f172a !important;
        }

        .block-container {
            max-width: 1280px !important;
            padding-top: 3.6rem !important;
            padding-bottom: 3rem !important;
            margin: 0 auto !important;
        }

        /* כותרת ראשית כהה עם טקסט לבן וזהב */
        .header-box {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 65%, #78350f 100%) !important;
            color: #ffffff !important;
            padding: 1.15rem 1.6rem;
            border-radius: 16px;
            border-bottom: 4px solid #f59e0b;
            margin-bottom: 1rem;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12);
        }
        .header-box .header-title {
            font-size: 1.4rem !important;
            font-weight: 700 !important;
            color: #ffffff !important;
            margin: 0 !important;
        }
        .header-box .header-sub {
            font-size: 0.88rem !important;
            color: #fcd34d !important;
            margin-top: 0.25rem !important;
        }

        /* כרטיסיות מדדים (KPI) */
        .kpi-card {
            background: #ffffff !important;
            border: 1px solid #fde68a !important;
            border-right: 5px solid #f59e0b !important;
            border-radius: 12px;
            padding: 0.85rem 0.9rem;
            text-align: center;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
            margin-bottom: 0.5rem;
        }
        .kpi-num { font-size: 1.5rem; font-weight: 700; color: #b45309 !important; }
        .kpi-label { font-size: 0.83rem; color: #475569 !important; font-weight: 600; }

        /* כרטיסיות נפתחות (Expanders) - מונע רקע שחור עם כתב שחור ב-Dark Mode */
        [data-testid="stExpander"] {
            background-color: #ffffff !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 12px !important;
            margin-bottom: 0.75rem !important;
            overflow: hidden !important;
        }
        [data-testid="stExpander"] details,
        [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            background-color: #ffffff !important;
            color: #0f172a !important;
        }
        [data-testid="stExpander"] summary {
            background-color: #f1f5f9 !important;
            color: #0f172a !important;
            border-bottom: 1px solid #e2e8f0 !important;
            padding: 0.8rem 1rem !important;
        }
        [data-testid="stExpander"] summary p,
        [data-testid="stExpander"] summary span,
        [data-testid="stExpander"] summary svg {
            color: #0f172a !important;
            fill: #0f172a !important;
            font-weight: 600 !important;
        }

        /* כפתורים ראשיים (כתום-זהב עם כתב לבן) */
        button[kind="primary"],
        [data-testid="stBaseButton-primary"],
        [data-testid="stBaseLinkButton-primary"] {
            background: linear-gradient(135deg, #d97706 0%, #b45309 100%) !important;
            color: #ffffff !important;
            border: none !important;
            font-weight: 600 !important;
            border-radius: 10px !important;
            box-shadow: 0 3px 10px rgba(180, 83, 9, 0.22) !important;
        }
        button[kind="primary"] *,
        [data-testid="stBaseButton-primary"] *,
        [data-testid="stBaseLinkButton-primary"] * {
            color: #ffffff !important;
        }

        /* כפתורים משניים (רקע לבן נקי עם כתב שחור חד - מתקן כפתור 'סמן כנשלח') */
        button[kind="secondary"],
        [data-testid="stBaseButton-secondary"],
        [data-testid="stBaseLinkButton-secondary"],
        [data-testid="stDownloadButton"] button {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1.5px solid #94a3b8 !important;
            font-weight: 600 !important;
            border-radius: 10px !important;
        }
        button[kind="secondary"] *,
        [data-testid="stBaseButton-secondary"] *,
        [data-testid="stBaseLinkButton-secondary"] *,
        [data-testid="stDownloadButton"] button * {
            color: #0f172a !important;
        }

        /* תיבות התראה (info / warning / error / success) בניגודיות גבוהה */
        [data-testid="stAlert"] {
            background-color: #fef3c7 !important;
            border: 1px solid #f59e0b !important;
            border-radius: 10px !important;
        }
        [data-testid="stAlert"] p,
        [data-testid="stAlert"] span,
        [data-testid="stAlert"] div {
            color: #1e293b !important;
            font-weight: 500 !important;
        }

        /* תיבת תצוגת הודעת וואטסאפ בהירה שגולשת נכון בנייד בלי חיתוך טקסט */
        .wa-preview-box {
            background-color: #f8fafc !important;
            color: #0f172a !important;
            border: 1.5px solid #cbd5e1 !important;
            border-right: 4px solid #16a34a !important;
            border-radius: 10px;
            padding: 0.9rem 1rem;
            margin-bottom: 0.8rem;
            white-space: pre-wrap !important;
            word-break: break-word !important;
            overflow-wrap: anywhere !important;
            direction: rtl !important;
            text-align: right !important;
            font-size: 0.92rem !important;
            line-height: 1.6 !important;
        }

        /* תיבות st.code (אם מופיעות בפרטי הנפקת סיסמה) */
        [data-testid="stCode"],
        [data-testid="stCode"] pre,
        [data-testid="stCode"] code {
            background-color: #f8fafc !important;
            color: #0f172a !important;
            border: 1px solid #cbd5e1 !important;
            white-space: pre-wrap !important;
            word-break: break-word !important;
            overflow-wrap: anywhere !important;
        }

        /* שדות קלט, בחירה, טפסים ותפריטים נפתחים */
        input, textarea, select,
        [data-baseweb="input"],
        [data-baseweb="base-input"],
        [data-baseweb="textarea"],
        [data-baseweb="select"] > div {
            background-color: #ffffff !important;
            color: #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
            border-color: #cbd5e1 !important;
            direction: rtl !important;
            text-align: right !important;
            unicode-bidi: plaintext !important;
        }
        [data-baseweb="popover"],
        [data-baseweb="menu"],
        ul[role="listbox"],
        li[role="option"] {
            background-color: #ffffff !important;
            color: #0f172a !important;
        }
        [data-testid="stForm"] {
            background-color: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 12px !important;
            padding: 0.9rem !important;
        }

        /* לשוניות (Tabs) ותוויות טקסט כלליות */
        [data-testid="stTabs"] button {
            background-color: transparent !important;
            color: #334155 !important;
            font-weight: 600 !important;
        }
        [data-testid="stTabs"] button[aria-selected="true"] {
            color: #b45309 !important;
            border-bottom-color: #d97706 !important;
        }
        label[data-testid="stWidgetLabel"] p,
        .stRadio label p,
        .stCheckbox label p,
        [data-testid="stCaptionContainer"] p,
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li,
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3,
        [data-testid="stMarkdownContainer"] h4,
        [data-testid="stMarkdownContainer"] h5 {
            color: #0f172a !important;
        }

        /* שמירה על טקסט לבן בתוך הכותרת הראשית */
        .header-box p, .header-box div, .header-box span {
            color: #ffffff !important;
        }
        .header-box .header-sub {
            color: #fcd34d !important;
        }

        .mobile-card-banner {
            background: #f8fafc !important;
            color: #0f172a !important;
            border: 1px solid #cbd5e1 !important;
            border-right: 4px solid #f59e0b !important;
            border-radius: 10px;
            padding: 0.75rem 0.95rem;
            margin-bottom: 0.7rem;
            font-size: 0.9rem;
            line-height: 1.6;
        }
        .badge-pill {
            display: inline-block;
            background: #e2e8f0 !important;
            color: #0f172a !important;
            padding: 0.22rem 0.55rem;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
            margin-left: 0.35rem;
            margin-bottom: 0.25rem;
        }
        .watermark {
            text-align: center;
            font-size: 0.8rem;
            color: #64748b !important;
            margin-top: 2.5rem;
            font-weight: 600;
            letter-spacing: 0.5px;
        }

        /* התאמה ייעודית למסכי טלפון נייד (Mobile-First) */
        @media (max-width: 768px) {
            .block-container {
                padding-top: 3.4rem !important;
                padding-left: 0.65rem !important;
                padding-right: 0.65rem !important;
            }
            .header-box {
                padding: 0.9rem 1rem;
                border-radius: 12px;
            }
            .header-box .header-title { font-size: 1.12rem !important; }
            .header-box .header-sub { font-size: 0.78rem !important; }
            .kpi-num { font-size: 1.25rem; }
            button[kind="primary"],
            button[kind="secondary"],
            [data-testid="stBaseButton-primary"],
            [data-testid="stBaseButton-secondary"],
            [data-testid="stBaseLinkButton-primary"],
            [data-testid="stBaseLinkButton-secondary"] {
                min-height: 2.9rem !important;
                font-size: 0.96rem !important;
                border-radius: 10px !important;
            }
            input, select, textarea {
                font-size: 16px !important;
            }
        }
    </style>
    """, unsafe_allow_html=True)


# ==============================================================================
# פרק 3: שכבת אבטחת מידע, הצפנת scrypt והגנת קלט/אקסל (Security & Crypto Engine)
# ==============================================================================

def hash_secret(secret_text: str) -> str:
    """מצפין סיסמה או PIN ב-scrypt עם Salt אקראי (ללא שמירה בטקסט גלוי)."""
    if not secret_text:
        return ""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        secret_text.strip().encode("utf-8"),
        salt=salt, n=16384, r=8, p=1, dklen=32
    )
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_secret(secret_text: str, stored_hash: str) -> bool:
    """מאמת סיסמה או PIN מול הגיבוב השמור בשיטת constant-time comparison."""
    if not secret_text or not stored_hash or not stored_hash.startswith("scrypt$"):
        return False
    try:
        _, salt_hex, derived_hex = stored_hash.split("$", 2)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(derived_hex)
        candidate = hashlib.scrypt(
            secret_text.strip().encode("utf-8"),
            salt=salt, n=16384, r=8, p=1, dklen=32
        )
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def hash_token_fast(token_str: str) -> str:
    """גיבוב SHA-256 לאסימוני קישור של 128 ביט."""
    return hashlib.sha256(token_str.strip().encode("utf-8")).hexdigest()


def clean_input(val) -> str:
    """מנקה ערך לשמירה נקייה במסד הנתונים."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "null") else s


def escape_html(val) -> str:
    """מבצע html.escape אך ורק לפני הזרקה לתוך בלוק unsafe_allow_html למניעת XSS."""
    return html.escape(clean_input(val))


def sanitize_excel_value(val):
    """מונע הזרקת נוסחאות אקסל (Formula Injection) בייצוא קבצים."""
    s = clean_input(val)
    if s.startswith(("=", "+", "-", "@")):
        return "'" + s
    return s


def sanitize_dataframe_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    safe_df = df.copy()
    for col in safe_df.columns:
        safe_df[col] = safe_df[col].map(sanitize_excel_value)
    return safe_df


def validate_uploaded_file(uploaded_file) -> tuple[bool, str]:
    """בודק סיומת, גודל קובץ (עד 5MB) וחתימת קובץ אמיתית (Magic Bytes)."""
    if not uploaded_file:
        return False, "לא נבחר קובץ."
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"סוג קובץ לא מורשה ({ext}). מותר: PDF, PNG, JPG, XLSX."
    data = uploaded_file.getvalue()
    if len(data) > MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
        return False, f"הקובץ חורג מהגודל המותר ({MAX_ATTACHMENT_SIZE_MB}MB)."
    if ext == ".pdf" and not data.startswith(b"%PDF"):
        return False, "תוכן הקובץ אינו תואם קובץ PDF תקני."
    if ext == ".png" and not data.startswith(b"\x89PNG"):
        return False, "תוכן הקובץ אינו תואם תמונת PNG תקנית."
    if ext in {".jpg", ".jpeg"} and not data.startswith(b"\xff\xd8"):
        return False, "תוכן הקובץ אינו תואם תמונת JPG תקנית."
    if ext == ".xlsx" and not data.startswith(b"PK\x03\x04"):
        return False, "תוכן הקובץ אינו תואם קובץ Excel תקני."
    return True, "תקין"


# ==============================================================================
# פרק 4: שכבת מסד הנתונים - Neon PostgreSQL / SQLite + מיגרציה (Database Layer)
# ==============================================================================

def get_database_url() -> str:
    try:
        if "DATABASE_URL" in st.secrets:
            url = str(st.secrets["DATABASE_URL"]).strip()
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            return url
    except Exception:
        pass
    return os.environ.get("DATABASE_URL", "")


class DBWrapper:
    """מעטפת אחידה ל-Neon PostgreSQL ול-SQLite המקומי עם שאילתות פרמטריות בלבד."""
    def __init__(self):
        self.db_url = get_database_url()
        self.is_postgres = bool(self.db_url and HAS_PSYCOPG2)
        if self.is_postgres:
            self.conn = psycopg2.connect(self.db_url, connect_timeout=15)
        else:
            self.conn = sqlite3.connect("sapakim_secure_v2.db", check_same_thread=False)
            self.conn.row_factory = sqlite3.Row

    def execute(self, query: str, params: tuple = ()):
        if self.is_postgres:
            pg_query = query.replace("?", "%s")
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(pg_query, params)
            return cur
        cur = self.conn.cursor()
        cur.execute(query, params)
        return cur

    def fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        cur = self.execute(query, params)
        return [dict(r) for r in cur.fetchall()]

    def fetchone(self, query: str, params: tuple = ()) -> dict | None:
        cur = self.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row is not None else None

    def ensure_columns(self, table_name: str, columns_spec: list[tuple[str, str]]):
        if self.is_postgres:
            for col_name, col_def in columns_spec:
                self.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col_name} {col_def}")
        else:
            existing_cols = {row["name"] for row in self.fetchall(f"PRAGMA table_info({table_name})")}
            for col_name, col_def in columns_spec:
                if col_name not in existing_cols:
                    self.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")

    def rollback(self):
        try:
            self.conn.rollback()
        except Exception:
            pass

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


@st.cache_resource
def init_db() -> bool:
    """מקים טבלאות, מבצע מיגרציה אוטומטית לעמודות חדשות ב-Neon ומסנכרן חשבונות צוות."""
    db = None
    stage = "DB_CONNECT"
    try:
        db = DBWrapper()
        id_serial = "SERIAL PRIMARY KEY" if db.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        blob_type = "BYTEA" if db.is_postgres else "BLOB"

        stage = "CREATE_TABLES"
        db.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                id {id_serial},
                username TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                order_manager_scope TEXT DEFAULT 'ALL',
                password_hash TEXT NOT NULL,
                pin_hash TEXT DEFAULT '',
                token_hash TEXT DEFAULT '',
                token_expires_at TEXT DEFAULT '',
                contact_person TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                is_locked INTEGER DEFAULT 0,
                failed_attempts INTEGER DEFAULT 0,
                locked_until TEXT DEFAULT '',
                must_change_password INTEGER DEFAULT 0,
                last_login TEXT DEFAULT ''
            )
        """)

        db.execute(f"""
            CREATE TABLE IF NOT EXISTS orders (
                id {id_serial},
                order_manager TEXT DEFAULT 'כללי',
                order_number TEXT NOT NULL,
                line_number TEXT NOT NULL,
                part_number TEXT DEFAULT '',
                item_description TEXT DEFAULT '',
                quantity TEXT DEFAULT '1',
                supplier_name TEXT DEFAULT '',
                contact_person TEXT DEFAULT '',
                supplier_phone TEXT DEFAULT '',
                due_date TEXT DEFAULT '',
                internal_status TEXT DEFAULT '',
                supplier_status TEXT DEFAULT 'טרם עודכן',
                expected_date TEXT DEFAULT '',
                supplier_note TEXT DEFAULT '',
                mador_response TEXT DEFAULT '',
                needs_attention INTEGER DEFAULT 0,
                last_updated TEXT DEFAULT '',
                last_supplier_update TEXT DEFAULT '',
                is_deleted INTEGER DEFAULT 0,
                deleted_at TEXT DEFAULT '',
                deleted_by TEXT DEFAULT '',
                UNIQUE(order_number, line_number)
            )
        """)

        db.execute(f"""
            CREATE TABLE IF NOT EXISTS attachments (
                id {id_serial},
                order_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                file_data {blob_type} NOT NULL,
                uploaded_by TEXT NOT NULL,
                uploaded_role TEXT NOT NULL,
                uploaded_at TEXT NOT NULL
            )
        """)

        db.execute(f"""
            CREATE TABLE IF NOT EXISTS order_comments (
                id {id_serial},
                order_id INTEGER NOT NULL,
                author_name TEXT NOT NULL,
                author_role TEXT NOT NULL,
                comment_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        db.execute(f"""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id {id_serial},
                timestamp TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                action_type TEXT NOT NULL,
                order_ref TEXT DEFAULT '',
                details TEXT NOT NULL
            )
        """)

        stage = "MIGRATE_COLUMNS"
        db.ensure_columns("orders", [
            ("order_manager", "TEXT DEFAULT 'כללי'"),
            ("contact_person", "TEXT DEFAULT ''"),
            ("supplier_phone", "TEXT DEFAULT ''"),
            ("internal_status", "TEXT DEFAULT ''"),
            ("last_supplier_update", "TEXT DEFAULT ''"),
            ("is_deleted", "INTEGER DEFAULT 0"),
            ("deleted_at", "TEXT DEFAULT ''"),
            ("deleted_by", "TEXT DEFAULT ''"),
        ])

        db.ensure_columns("users", [
            ("order_manager_scope", "TEXT DEFAULT 'ALL'"),
            ("pin_hash", "TEXT DEFAULT ''"),
            ("token_hash", "TEXT DEFAULT ''"),
            ("token_expires_at", "TEXT DEFAULT ''"),
            ("contact_person", "TEXT DEFAULT ''"),
            ("phone", "TEXT DEFAULT ''"),
            ("is_locked", "INTEGER DEFAULT 0"),
            ("failed_attempts", "INTEGER DEFAULT 0"),
            ("locked_until", "TEXT DEFAULT ''"),
            ("must_change_password", "INTEGER DEFAULT 0"),
            ("last_login", "TEXT DEFAULT ''"),
        ])

        db.ensure_columns("audit_logs", [
            ("order_ref", "TEXT DEFAULT ''"),
        ])

        stage = "NORMALIZE_DATA"
        db.execute("DELETE FROM users WHERE username IN ('namer', 'merkava', 'eitan', 'manhar')")
        db.execute("UPDATE orders SET order_manager = 'כללי' WHERE order_manager IS NULL OR order_manager NOT IN ('שגיא', 'פיראס', 'סאקר', 'אדי', 'כללי')")
        db.execute("UPDATE orders SET is_deleted = 0 WHERE is_deleted IS NULL")
        db.execute("UPDATE orders SET needs_attention = 0 WHERE needs_attention IS NULL")

        existing_suppliers = db.fetchall("""
            SELECT supplier_name, MAX(contact_person) AS contact_person, MAX(supplier_phone) AS supplier_phone
            FROM orders
            WHERE supplier_name IS NOT NULL AND TRIM(supplier_name) != ''
            GROUP BY supplier_name
        """)
        for sup in existing_suppliers:
            ensure_supplier_account(db, sup["supplier_name"], sup.get("contact_person", ""), sup.get("supplier_phone", ""))

        stage = "SYNC_STAFF"
        staff_secrets = {}
        try:
            if "staff_keys" in st.secrets:
                staff_secrets = dict(st.secrets["staff_keys"])
        except Exception:
            pass

        default_staff = [
            ("admin", "admin", "רועי - מנהל מערכת ראשי", "ALL", staff_secrets.get("ADMIN_KEY", "BH-ADMIN-9920")),
            ("sagi", "manager", "שגיא", "שגיא", staff_secrets.get("SAGI_KEY", "SAGI-7741")),
            ("firas", "manager", "פיראס", "פיראס", staff_secrets.get("FIRAS_KEY", "FIRAS-5582")),
            ("saker", "manager", "סאקר", "סאקר", staff_secrets.get("SAKER_KEY", "SAKER-6614")),
            ("edi", "manager", "אדי", "אדי", staff_secrets.get("EDI_KEY", "EDI-3319")),
        ]

        for uname, role, ename, scope, raw_pwd in default_staff:
            existing = db.fetchone("SELECT id, password_hash FROM users WHERE username = ?", (uname,))
            if not existing:
                db.execute("""
                    INSERT INTO users (username, role, entity_name, order_manager_scope, password_hash)
                    VALUES (?, ?, ?, ?, ?)
                """, (uname, role, ename, scope, hash_secret(raw_pwd)))
            elif staff_secrets and not verify_secret(raw_pwd, existing.get("password_hash", "")):
                db.execute("""
                    UPDATE users SET role = ?, entity_name = ?, order_manager_scope = ?, password_hash = ?
                    WHERE username = ?
                """, (role, ename, scope, hash_secret(raw_pwd), uname))

        db.commit()
        return True
    except Exception:
        if db is not None:
            db.rollback()
        logging.exception(f"init_db failed at stage: {stage}")
        st.error(f"אירעה שגיאת תקשורת פנימית מול שרת הנתונים [שלב: {stage}]. נא לפנות למנהל המערכת או לבדוק את Manage app -> Logs.")
        st.stop()
    finally:
        if db is not None:
            db.close()


def log_audit(db: DBWrapper, actor_name: str, actor_role: str, action_type: str, details: str, order_ref: str = ""):
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    db.execute("""
        INSERT INTO audit_logs (timestamp, actor_name, actor_role, action_type, order_ref, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (now_str, clean_input(actor_name), clean_input(actor_role), clean_input(action_type), clean_input(order_ref), clean_input(details)))


# ==============================================================================
# פרק 5: לוגיקה עסקית, מיזוג אקסל (VLOOKUP), קבצים מצורפים ווואטסאפ (Business Logic)
# ==============================================================================

def normalize_phone_display(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = re.sub(r"[^\d]", "", str(val).split(".")[0])
    if not s or s == "0" or len(s) < 8:
        return ""
    if len(s) == 9 and s.startswith("5"):
        return "0" + s
    if s.startswith("972") and len(s) >= 11:
        return "0" + s[3:]
    return s


def normalize_phone_whatsapp(val) -> str:
    disp = normalize_phone_display(val)
    if not disp or len(disp) < 9:
        return ""
    if disp.startswith("0"):
        return "972" + disp[1:]
    return disp


def infer_order_manager(row_dict: dict) -> str:
    candidate_cols = ["מנהל ההזמנה", "מנהל הזמנה", "קצין אחראי", "אחראי", "מנהל", "מדור"]
    explicit = ""
    for col in candidate_cols:
        val = clean_input(row_dict.get(col))
        if val:
            explicit = val
            break

    for m in ORDER_MANAGERS:
        if m != "כללי" and m in explicit:
            return m
    return "כללי"


def calc_delay_days(due_date_str: str, supplier_status: str) -> tuple[int, str]:
    if supplier_status == "סופק":
        return 0, "🟢 סופק"
    if not due_date_str:
        return 0, "⚪ ללא תאריך יעד"
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(str(due_date_str).strip()[:10], fmt).date()
            diff = (datetime.now().date() - dt).days
            if diff > 0:
                return diff, f"🔴 {diff} ימים בפיגור"
            return diff, f"🟢 {abs(diff)} ימים למועד"
        except ValueError:
            continue
    return 0, "⚪ תאריך לא תקני"


def ensure_supplier_account(db: DBWrapper, supplier_name: str, contact_person: str, phone: str):
    clean_name = clean_input(supplier_name)
    if not clean_name:
        return
    existing = db.fetchone("SELECT id FROM users WHERE role = 'supplier' AND entity_name = ?", (clean_name,))
    if not existing:
        uname = clean_name
        if db.fetchone("SELECT id FROM users WHERE username = ?", (uname,)):
            uname = f"{clean_name}_{secrets.token_hex(2)}"
        initial_pwd = secrets.token_urlsafe(6)
        initial_pin = f"{secrets.randbelow(900000) + 100000}"
        raw_token = secrets.token_hex(16)
        exp = (datetime.now() + timedelta(days=TOKEN_EXPIRY_DAYS)).strftime("%Y-%m-%d")
        db.execute("""
            INSERT INTO users (
                username, role, entity_name, order_manager_scope,
                password_hash, pin_hash, token_hash, token_expires_at,
                contact_person, phone, must_change_password
            ) VALUES (?, 'supplier', ?, 'SUPPLIER', ?, ?, ?, ?, ?, ?, 1)
        """, (
            uname, clean_name,
            hash_secret(initial_pwd), hash_secret(initial_pin),
            hash_token_fast(raw_token), exp,
            clean_input(contact_person), normalize_phone_display(phone)
        ))
    else:
        db.execute("""
            UPDATE users SET contact_person = CASE WHEN ? != '' THEN ? ELSE contact_person END,
                             phone = CASE WHEN ? != '' THEN ? ELSE phone END
            WHERE role = 'supplier' AND entity_name = ?
        """, (clean_input(contact_person), clean_input(contact_person),
              normalize_phone_display(phone), normalize_phone_display(phone), clean_name))


def issue_new_supplier_credentials(db: DBWrapper, supplier_name: str, actor_name: str) -> dict:
    temp_password = f"SUP-{secrets.token_hex(3).upper()}"
    new_pin = f"{secrets.randbelow(900000) + 100000}"
    raw_token = secrets.token_hex(16)
    expires_at = (datetime.now() + timedelta(days=TOKEN_EXPIRY_DAYS)).strftime("%Y-%m-%d")

    db.execute("""
        UPDATE users
        SET password_hash = ?, pin_hash = ?, token_hash = ?, token_expires_at = ?,
            is_locked = 0, failed_attempts = 0, locked_until = '', must_change_password = 1
        WHERE role = 'supplier' AND entity_name = ?
    """, (hash_secret(temp_password), hash_secret(new_pin), hash_token_fast(raw_token), expires_at, supplier_name))

    log_audit(db, actor_name, "admin", "ISSUE_CREDENTIALS", f"הונפקו אמצעי זיהוי חדשים לספק {supplier_name}")
    db.commit()
    return {
        "supplier_name": supplier_name,
        "temp_password": temp_password,
        "pin": new_pin,
        "raw_token": raw_token,
        "expires_at": expires_at
    }


def build_whatsapp_message(supplier_name: str, contact_person: str, orders_list: list[dict], portal_url: str, raw_token: str = "") -> str:
    """בונה הודעת וואטסאפ ללא חשיפת PIN או סיסמה בגוף ההודעה."""
    greeting_name = f"{contact_person} ({supplier_name})" if contact_person else supplier_name
    lines_text = []
    for o in orders_list[:12]:
        lines_text.append(
            f"• הזמנה {o['order_number']} (שורה {o['line_number']}) | מק\"ט {o['part_number']} - {o['item_description']}"
        )
    if len(orders_list) > 12:
        lines_text.append(f"...ועוד {len(orders_list) - 12} שורות נוספות בפורטל.")

    link_to_send = f"{portal_url}/?token={raw_token}" if raw_token else portal_url
    return (
        f"שלום {greeting_name},\n"
        f"בהמשך למעקב הזמנות חט\"ל, להלן ההזמנות הפתוחות הממתינות לעדכון סטטוס וצפי אספקה:\n\n"
        + "\n".join(lines_text) +
        f"\n\nלכניסה מאובטחת לפורטל ועדכון ישיר:\n{link_to_send}\n"
        f"(הכניסה באמצעות שם הספק והסיסמה האישית שלך, או באמצעות קוד ה-PIN שנמסר לך בנפרד).\n"
        f"תודה על שיתוף הפעולה."
    )


def normalize_field_for_compare(field: str, val):
    if field == "needs_attention":
        if isinstance(val, bool):
            return val
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return False
        return str(val).strip().lower() in ("1", "true", "yes")
    return clean_input(val)


# ==============================================================================
# פרק 6: מסכי המערכת לפי הרשאות (Login, Supplier, Staff - Desktop & Mobile)
# ==============================================================================

def render_login_view(db: DBWrapper):
    st.markdown("""
        <div class="header-box" style="text-align:center;">
            <div class="header-title">🛡️ פורטל SAPakim - מערכת הזמנות חט"ל</div>
            <div class="header-sub">כניסה מאובטחת וממודרת לספקים, מנהלי הזמנה והנהלה</div>
        </div>
    """, unsafe_allow_html=True)

    url_token = st.query_params.get("token", "").strip()

    _, col_main, _ = st.columns([0.6, 2, 0.6])
    with col_main:
        if url_token:
            token_user = db.fetchone(
                "SELECT * FROM users WHERE token_hash = ? AND role = 'supplier'",
                (hash_token_fast(url_token),)
            )
            if not token_user:
                st.error("קישור הגישה אינו תקף או שפג תוקפו. אנא התחבר עם שם ספק וסיסמה.")
            else:
                st.info(f"🔒 זיהוי קישור עבור: **{token_user['entity_name']}**. הזן את קוד ה-PIN האישי (שנמסר לך בנפרד):")
                pin_input = st.text_input("קוד PIN (6 ספרות):", type="password", max_chars=10)
                if st.button("אמת כניסה לפורטל 🔓", type="primary", use_container_width=True):
                    _process_auth_attempt(db, token_user, pin_input, is_pin=True)
                st.divider()

        st.markdown("#### 🔑 כניסה באמצעות שם משתמש/ספק וסיסמה")
        identifier = st.text_input("שם משתמש (admin, שגיא, פיראס, סאקר, אדי) או שם ספק:").strip()
        password = st.text_input("סיסמה / מפתח גישה סודי:", type="password").strip()

        if st.button("התחבר למערכת 🔒", type="primary", use_container_width=True):
            if not identifier or not password:
                st.warning("נא להזין שם משתמש/ספק וסיסמה.")
            else:
                user_row = db.fetchone(
                    "SELECT * FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(entity_name) = LOWER(?)",
                    (identifier, identifier)
                )
                if not user_row:
                    log_audit(db, identifier, "unknown", "LOGIN_FAIL", "ניסיון התחברות עם מזהה לא קיים")
                    db.commit()
                    st.error("פרטי ההזדהות שגויים.")
                else:
                    _process_auth_attempt(db, user_row, password, is_pin=False)

        st.caption("ניתן להזין בשדה המשתמש את השם בעברית (שגיא / פיראס / סאקר / אדי) או באנגלית (sagi / firas / saker / edi / admin).")


def _process_auth_attempt(db: DBWrapper, user_row: dict, secret_input: str, is_pin: bool):
    now = datetime.now()

    if user_row.get("is_locked") == 1:
        st.error("🔒 החשבון נחסם על ידי מנהל המערכת. יש לפנות למנהל המערכת הראשי.")
        return

    if user_row.get("locked_until"):
        try:
            lock_dt = datetime.strptime(user_row["locked_until"], "%Y-%m-%d %H:%M:%S")
            if now < lock_dt:
                mins_left = int((lock_dt - now).total_seconds() // 60) + 1
                st.error(f"🔒 החשבון נעול זמנית עקב ניסיונות כושלים. נסה שוב בעוד {mins_left} דקות.")
                return
        except ValueError:
            pass

    if is_pin and user_row.get("token_expires_at"):
        try:
            exp_dt = datetime.strptime(user_row["token_expires_at"], "%Y-%m-%d").date()
            if now.date() > exp_dt:
                st.error("פג תוקף קישור הגישה. בקש ממנהל המערכת להנפיק קישור חדש.")
                return
        except ValueError:
            pass

    target_hash = user_row["pin_hash"] if is_pin else user_row["password_hash"]
    if verify_secret(secret_input, target_hash):
        db.execute("""
            UPDATE users SET failed_attempts = 0, locked_until = '', last_login = ?
            WHERE id = ?
        """, (now.strftime("%d/%m/%Y %H:%M"), user_row["id"]))
        log_audit(db, user_row["entity_name"], user_row["role"], "LOGIN_SUCCESS", "התחברות מוצלחת למערכת")
        db.commit()
        st.session_state.user = dict(user_row)
        st.session_state.last_activity = now
        st.rerun()
    else:
        fails = int(user_row.get("failed_attempts") or 0) + 1
        locked_until_str = ""
        if fails >= MAX_LOGIN_ATTEMPTS:
            locked_until_str = (now + timedelta(minutes=LOCKOUT_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute("""
            UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?
        """, (fails, locked_until_str, user_row["id"]))
        log_audit(db, user_row["entity_name"], user_row["role"], "LOGIN_FAIL", f"ניסיון כניסה כושל ({fails}/{MAX_LOGIN_ATTEMPTS})")
        db.commit()
        st.error(f"פרטי ההזדהות שגויים (ניסיון {fails} מתוך {MAX_LOGIN_ATTEMPTS}).")


def render_attachments_and_comments_widget(db: DBWrapper, order_row: dict, user: dict, key_prefix: str = ""):
    oid = order_row["id"]
    order_ref = f"{order_row['order_number']}/{order_row['line_number']}"

    col_c, col_a = st.columns([1.2, 1])

    with col_c:
        st.markdown("**💬 שרשור תגובות מתועד לשורה זו:**")
        comments = db.fetchall("SELECT * FROM order_comments WHERE order_id = ? ORDER BY id ASC", (oid,))
        if not comments:
            st.caption("אין עדיין הודעות בשרשור לשורה זו.")
        else:
            for c in comments:
                badge = "🛠️ מנהל הזמנה/חט\"ל" if c["author_role"] in ("admin", "manager", "mador") else "🏭 ספק"
                st.markdown(f"- **{badge} ({c['author_name']})** `[{c['created_at']}]`: {c['comment_text']}")

        new_comment = st.text_input("הוסף תגובה חדשה לשרשור:", key=f"{key_prefix}comm_in_{oid}")
        if st.button("שלח תגובה 💬", key=f"{key_prefix}comm_btn_{oid}", use_container_width=True):
            clean_c = clean_input(new_comment)
            if clean_c:
                now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
                db.execute("""
                    INSERT INTO order_comments (order_id, author_name, author_role, comment_text, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (oid, user["entity_name"], user["role"], clean_c, now_s))
                if user["role"] == "supplier":
                    db.execute("UPDATE orders SET supplier_note = ?, last_supplier_update = ?, last_updated = ? WHERE id = ?",
                               (clean_c, now_s, now_s, oid))
                else:
                    db.execute("UPDATE orders SET mador_response = ?, last_updated = ? WHERE id = ?",
                               (clean_c, now_s, oid))
                log_audit(db, user["entity_name"], user["role"], "ADD_COMMENT", f"נוספה תגובה לשורה {order_ref}", order_ref)
                db.commit()
                st.success("התגובה נוספה לשרשור!")
                st.rerun()

    with col_a:
        st.markdown("**📎 מסמכים ושרטוטים מצורפים (עד 5MB):**")
        att_rows = db.fetchall(
            "SELECT id, filename, uploaded_by, uploaded_role, uploaded_at FROM attachments WHERE order_id = ? ORDER BY id DESC",
            (oid,)
        )
        if not att_rows:
            st.caption("לא צורפו מסמכים לשורה זו.")
        else:
            for att in att_rows:
                full_att = db.fetchone("SELECT file_data FROM attachments WHERE id = ?", (att["id"],))
                if full_att and full_att.get("file_data") is not None:
                    raw_bytes = bytes(full_att["file_data"])
                    st.download_button(
                        label=f"📥 הורד: {att['filename']} ({att['uploaded_by']})",
                        data=raw_bytes,
                        file_name=att["filename"],
                        key=f"{key_prefix}dl_att_{att['id']}_{oid}",
                        use_container_width=True
                    )

        up_file = st.file_uploader(
            "צרף שרטוט / מפרט / אישור (PDF, PNG, JPG, XLSX):",
            type=["pdf", "png", "jpg", "jpeg", "xlsx"],
            key=f"{key_prefix}up_file_{oid}"
        )
        if up_file and st.button("העלה ושמור מסמך 📎", key=f"{key_prefix}up_btn_{oid}", use_container_width=True):
            ok, msg = validate_uploaded_file(up_file)
            if not ok:
                st.error(msg)
            else:
                now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
                fname = clean_input(os.path.basename(up_file.name))
                db.execute("""
                    INSERT INTO attachments (order_id, filename, file_data, uploaded_by, uploaded_role, uploaded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (oid, fname, up_file.getvalue(), user["entity_name"], user["role"], now_s))
                log_audit(db, user["entity_name"], user["role"], "UPLOAD_ATTACHMENT", f"הועלה קובץ {fname}", order_ref)
                db.commit()
                st.success("המסמך צורף בהצלחה!")
                st.rerun()


def render_supplier_portal(db: DBWrapper, user: dict):
    sup_name = user["entity_name"]

    if user.get("must_change_password") == 1:
        st.warning("🔐 זוהי כניסה עם סיסמה זמנית. אנא בחר כעת סיסמה אישית חדשה (לפחות 6 תווים):")
        new_p1 = st.text_input("סיסמה אישית חדשה:", type="password")
        new_p2 = st.text_input("אימות סיסמה חדשה:", type="password")
        if st.button("עדכן סיסמה אישית 💾", type="primary", use_container_width=True):
            if len(new_p1.strip()) < 6 or new_p1 != new_p2:
                st.error("הסיסמאות אינן תואמות או קצרות מ-6 תווים.")
            else:
                db.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                           (hash_secret(new_p1), user["id"]))
                log_audit(db, sup_name, "supplier", "PASSWORD_CHANGED", f"הספק {sup_name} החליף את סיסמתו הזמנית לסיסמה אישית")
                db.commit()
                st.session_state.user["must_change_password"] = 0
                st.success("הסיסמה עודכנה בהצלחה!")
                st.rerun()
        return

    orders = db.fetchall(
        "SELECT * FROM orders WHERE supplier_name = ? AND is_deleted = 0 ORDER BY order_number, line_number",
        (sup_name,)
    )
    if not orders:
        st.info("אין כרגע הזמנות פתוחות המשויכות לחשבונך.")
        return

    with st.expander("⚡ עדכון מהיר וגורף לכל השורות שלי", expanded=False):
        c1, c2, c3 = st.columns([1, 1.5, 1])
        bulk_status = c1.selectbox("בחר סטטוס להחלה גורפת:", SUPPLIER_STATUS_OPTIONS, key="bulk_sup_stat")
        bulk_note = c2.text_input("הערה גורפת לכל השורות (אופציונלי):", key="bulk_sup_note")
        if c3.button("⚡ החל על כל השורות שלי", type="primary", use_container_width=True):
            now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
            bn = clean_input(bulk_note)
            for o in orders:
                db.execute("""
                    UPDATE orders
                    SET supplier_status = ?,
                        supplier_note = CASE WHEN ? != '' THEN ? ELSE supplier_note END,
                        last_supplier_update = ?, last_updated = ?
                    WHERE id = ? AND supplier_name = ?
                """, (bulk_status, bn, bn, now_s, now_s, o["id"], sup_name))
            log_audit(db, sup_name, "supplier", "BULK_UPDATE", f"עדכון גורף לסטטוס {bulk_status} ({len(orders)} שורות)")
            db.commit()
            st.success("כל השורות עודכנו בהצלחה!")
            st.rerun()

    st.markdown(f"### 📦 ההזמנות הפתוחות שלי ({len(orders)} שורות)")
    for o in orders:
        _, delay_badge = calc_delay_days(o["due_date"], o["supplier_status"])
        title = (
            f"הזמנה {o['order_number']} | שורה {o['line_number']} | "
            f"מק\"ט: {o['part_number']} - {o['item_description']} | {delay_badge}"
        )
        with st.expander(title, expanded=True):
            st.markdown(f"""
                <div class="mobile-card-banner">
                    <span class="badge-pill">🔒 כמות: {escape_html(o['quantity'])}</span>
                    <span class="badge-pill">🔒 יעד מקורי: {escape_html(o['due_date']) or 'לא הוגדר'}</span>
                    <span class="badge-pill">👤 מנהל ההזמנה: {escape_html(o['order_manager'])}</span><br>
                    <strong>💬 מענה מנהל ההזמנה:</strong> {escape_html(o['mador_response']) or 'טרם נרשם מענה'}
                </div>
            """, unsafe_allow_html=True)

            col1, col2, col3, col4 = st.columns([1.1, 1.1, 1.5, 0.8])
            cur_stat = o["supplier_status"] if o["supplier_status"] in SUPPLIER_STATUS_OPTIONS else "טרם עודכן"
            new_stat = col1.selectbox(
                "סטטוס ספק:", SUPPLIER_STATUS_OPTIONS,
                index=SUPPLIER_STATUS_OPTIONS.index(cur_stat),
                key=f"s_stat_{o['id']}"
            )

            default_exp = o["expected_date"] or o["due_date"] or ""
            change_date = col2.checkbox("📅 שנה תאריך אספקה", key=f"chg_dt_{o['id']}")
            if change_date:
                new_exp = col2.date_input("בחר צפי אספקה מעודכן:", key=f"dt_pick_{o['id']}").strftime("%Y-%m-%d")
            else:
                col2.text_input("צפי אספקה (נעול לתאריך המקורי):", value=default_exp, disabled=True, key=f"dt_dis_{o['id']}")
                new_exp = default_exp

            new_note = col3.text_input("הערת ספק / בקשה למנהל ההזמנה:", value=o["supplier_note"] or "", key=f"s_note_{o['id']}")
            needs_att = col4.checkbox("🚩 דרוש מענה", value=bool(o["needs_attention"]), key=f"s_att_{o['id']}")

            if st.button("💾 שמור עדכון לשורה זו", key=f"save_sup_{o['id']}", type="primary", use_container_width=True):
                now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
                db.execute("""
                    UPDATE orders
                    SET supplier_status = ?, expected_date = ?, supplier_note = ?,
                        needs_attention = ?, last_supplier_update = ?, last_updated = ?
                    WHERE id = ? AND supplier_name = ?
                """, (new_stat, clean_input(new_exp), clean_input(new_note), int(needs_att), now_s, now_s, o["id"], sup_name))
                log_audit(
                    db, sup_name, "supplier", "ROW_UPDATE",
                    f"סטטוס: {new_stat}, צפי: {new_exp}", f"{o['order_number']}/{o['line_number']}"
                )
                db.commit()
                st.success("העדכון נשמר בהצלחה!")
                st.rerun()

            st.divider()
            render_attachments_and_comments_widget(db, o, user, key_prefix="sup_")


def render_staff_dashboard(db: DBWrapper, user: dict):
    role = user["role"]
    scope = user.get("order_manager_scope", "ALL")

    if db.is_postgres:
        st.caption("🟢 מחובר למסד הנתונים הקבוע בענן (Neon PostgreSQL)")
    else:
        st.caption("⚠️ פועל במצב SQLite מקומי (לא הוגדר DATABASE_URL ב-Secrets)")

    if role == "admin":
        sec_alerts = db.fetchall("""
            SELECT timestamp, actor_name, action_type, details
            FROM audit_logs
            WHERE action_type IN ('PASSWORD_CHANGED', 'LOGIN_FAIL', 'ISSUE_CREDENTIALS')
            ORDER BY id DESC LIMIT 5
        """)
        if sec_alerts:
            with st.expander("🔔 התראות אבטחה ובקרת סיסמאות אחרונות", expanded=False):
                for a in sec_alerts:
                    st.markdown(f"- `{a['timestamp']}` | **{a['actor_name']}** ({a['action_type']}): {a['details']}")

    if role == "admin" or scope == "ALL":
        all_orders = db.fetchall("SELECT * FROM orders WHERE is_deleted = 0 ORDER BY order_number, line_number")
    else:
        all_orders = db.fetchall(
            "SELECT * FROM orders WHERE is_deleted = 0 AND order_manager = ? ORDER BY order_number, line_number",
            (scope,)
        )

    total_rows = len(all_orders)
    delayed_days_list = []
    updated_this_week = 0
    attention_count = 0
    now_dt = datetime.now()

    for o in all_orders:
        d_days, d_label = calc_delay_days(o["due_date"], o["supplier_status"])
        o["פיגור בימים"] = d_label
        if d_days > 0:
            delayed_days_list.append(d_days)
        if o.get("needs_attention"):
            attention_count += 1
        if o.get("last_supplier_update"):
            try:
                up_dt = datetime.strptime(o["last_supplier_update"], "%d/%m/%Y %H:%M")
                if (now_dt - up_dt).days <= 7:
                    updated_this_week += 1
                    o["סטטוס שבועי"] = "🟢 עודכן השבוע"
                else:
                    o["סטטוס שבועי"] = "⚪ טרם עודכן השבוע"
            except ValueError:
                o["סטטוס שבועי"] = "⚪ טרם עודכן השבוע"
        else:
            o["סטטוס שבועי"] = "⚪ טרם עודכן השבוע"

    avg_delay = round(sum(delayed_days_list) / len(delayed_days_list), 1) if delayed_days_list else 0.0

    k1, k2, k3, k4 = st.columns(4)
    scope_lbl = "כל מנהלי ההזמנה" if scope == "ALL" else scope
    k1.markdown(f"<div class='kpi-card'><div class='kpi-num'>{total_rows}</div><div class='kpi-label'>שורות פתוחות ({escape_html(scope_lbl)})</div></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='kpi-card'><div class='kpi-num'>{avg_delay}</div><div class='kpi-label'>ממוצע ימי פיגור</div></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='kpi-card'><div class='kpi-num'>🟢 {updated_this_week}</div><div class='kpi-label'>עודכנו השבוע ע\"י ספק</div></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='kpi-card'><div class='kpi-num'>🚩 {attention_count}</div><div class='kpi-label'>דורשות טיפול</div></div>", unsafe_allow_html=True)

    st.write("")
    tabs = st.tabs([
        "📋 הזמנות ועריכה (מחשב / נייד)",
        "📎 שרטוטים, תגובות והיסטוריה",
        "📲 וואטסאפ ותזכורות",
        "📥 טעינת אקסל (VLOOKUP)",
        "📊 דשבורד מפקד",
        "🔐 ניהול ספקים, מחיקה וגיבוי"
    ])

    with tabs[0]:
        _render_tab_orders_table_and_mobile(db, user, all_orders)

    with tabs[1]:
        _render_tab_attachments_and_history(db, user, all_orders)

    with tabs[2]:
        _render_tab_whatsapp(db, user, all_orders)

    with tabs[3]:
        _render_tab_excel_upload(db, user)

    with tabs[4]:
        _render_tab_commander_dashboard(db, all_orders)

    with tabs[5]:
        _render_tab_security_and_backup(db, user, all_orders)


def _render_tab_orders_table_and_mobile(db: DBWrapper, user: dict, all_orders: list[dict]):
    role = user["role"]
    if not all_orders:
        st.info("אין הזמנות להצגה. ניתן לטעון קובץ אקסל בלשונית 'טעינת אקסל'.")
        return

    c_f1, c_f2, c_f3, c_f4 = st.columns([1.1, 1.3, 1, 1.2])
    if role == "admin":
        mgr_filter = c_f1.selectbox("סינון לפי מנהל ההזמנה:", ["הכל"] + ORDER_MANAGERS)
    else:
        mgr_filter = "הכל"
        c_f1.text_input("מנהל ההזמנה:", value=user.get("order_manager_scope", ""), disabled=True)

    search_q = c_f2.text_input("🔍 חיפוש (הזמנה / מק\"ט / ספק / איש קשר):").strip()
    att_only = c_f3.checkbox("🚩 דורשות טיפול בלבד")
    view_mode = c_f4.radio(
        "מצב תצוגה ועריכה:",
        ["📱 כרטיסיות (נוח לנייד)", "💻 טבלה מלאה (למחשב)"],
        horizontal=True
    )

    filtered = all_orders
    if mgr_filter != "הכל":
        filtered = [o for o in filtered if o["order_manager"] == mgr_filter]
    if att_only:
        filtered = [o for o in filtered if o.get("needs_attention")]
    if search_q:
        filtered = [
            o for o in filtered
            if search_q.lower() in f"{o['order_number']} {o['part_number']} {o['item_description']} {o['supplier_name']} {o['contact_person']} {o['order_manager']}".lower()
        ]

    st.caption(f"מציג {len(filtered)} שורות מתוך {len(all_orders)}.")
    if not filtered:
        st.info("לא נמצאו הזמנות התואמות את תנאי החיפוש או הסינון.")
        return

    if view_mode.startswith("📱"):
        st.info("📱 **מצב עריכה לנייד:** לחץ על כל הזמנה כדי לפתוח כרטיסייה נוחה לעריכה מהטלפון ולשמור מיידית.")
        max_show = st.number_input("כמות כרטיסיות להצגה בעמוד:", min_value=5, max_value=200, value=25, step=5)

        for o in filtered[:int(max_show)]:
            oid = o["id"]
            order_ref = f"{o['order_number']}/{o['line_number']}"
            flag_icon = "🚩 " if o.get("needs_attention") else "📦 "
            card_title = f"{flag_icon}{o['supplier_name']} | הזמנה {order_ref} | {o['order_manager']} | {o['פיגור בימים']}"

            with st.expander(card_title, expanded=False):
                st.markdown(f"""
                    <div class="mobile-card-banner">
                        <strong>פריט:</strong> {escape_html(o['item_description']) or '-'}<br>
                        <span class="badge-pill">מק"ט: {escape_html(o['part_number']) or '-'}</span>
                        <span class="badge-pill">כמות: {escape_html(o['quantity'])}</span>
                        <span class="badge-pill">יעד: {escape_html(o['due_date']) or '-'}</span>
                        <span class="badge-pill">איש קשר: {escape_html(o['contact_person']) or '-'} ({escape_html(o['supplier_phone']) or '-'})</span><br>
                        <strong>סטטוס ספק:</strong> {escape_html(o['supplier_status'])} | <strong>צפי ספק:</strong> {escape_html(o['expected_date']) or 'לא הוזן'}<br>
                        <strong>הערת ספק:</strong> {escape_html(o['supplier_note']) or 'אין הערה'}
                    </div>
                """, unsafe_allow_html=True)

                with st.form(key=f"mob_edit_form_{oid}"):
                    updated_vals = {}
                    if role == "admin":
                        cur_mgr = o["order_manager"] if o["order_manager"] in ORDER_MANAGERS else "כללי"
                        updated_vals["order_manager"] = st.selectbox(
                            "👤 מנהל ההזמנה:", ORDER_MANAGERS,
                            index=ORDER_MANAGERS.index(cur_mgr),
                            key=f"m_mgr_{oid}"
                        )
                        cur_st = o["supplier_status"] if o["supplier_status"] in SUPPLIER_STATUS_OPTIONS else "טרם עודכן"
                        updated_vals["supplier_status"] = st.selectbox(
                            "📊 סטטוס ספק (עריכת Admin):", SUPPLIER_STATUS_OPTIONS,
                            index=SUPPLIER_STATUS_OPTIONS.index(cur_st),
                            key=f"m_sst_{oid}"
                        )
                        updated_vals["expected_date"] = st.text_input("📅 צפי אספקה מספק (Admin):", value=o["expected_date"] or "", key=f"m_exp_{oid}")
                        updated_vals["supplier_note"] = st.text_input("💬 הערת ספק (Admin):", value=o["supplier_note"] or "", key=f"m_snt_{oid}")

                    c_m1, c_m2 = st.columns(2)
                    updated_vals["part_number"] = c_m1.text_input("מק\"ט:", value=o["part_number"] or "", key=f"m_pn_{oid}")
                    updated_vals["quantity"] = c_m2.text_input("כמות:", value=o["quantity"] or "1", key=f"m_qty_{oid}")
                    updated_vals["item_description"] = st.text_input("תיאור פריט:", value=o["item_description"] or "", key=f"m_desc_{oid}")
                    updated_vals["due_date"] = st.text_input("תאריך יעד מקורי (YYYY-MM-DD):", value=o["due_date"] or "", key=f"m_due_{oid}")

                    c_p1, c_p2 = st.columns(2)
                    updated_vals["contact_person"] = c_p1.text_input("איש קשר ספק:", value=o["contact_person"] or "", key=f"m_cp_{oid}")
                    updated_vals["supplier_phone"] = c_p2.text_input("טלפון ספק:", value=o["supplier_phone"] or "", key=f"m_ph_{oid}")

                    updated_vals["mador_response"] = st.text_area("✍️ מענה מנהל ההזמנה לספק:", value=o["mador_response"] or "", key=f"m_resp_{oid}")
                    updated_vals["needs_attention"] = st.checkbox("🚩 מסומן כדרוש טיפול", value=bool(o["needs_attention"]), key=f"m_att_{oid}")

                    if st.form_submit_button("💾 שמור שינויים בכרטיסייה זו", type="primary", use_container_width=True):
                        now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
                        allowed = ROLE_ALLOWED_FIELDS.get(role, set())
                        changed_count = 0
                        for field, new_v in updated_vals.items():
                            if field not in allowed:
                                continue
                            old_norm = normalize_field_for_compare(field, o.get(field))
                            new_norm = normalize_field_for_compare(field, new_v)
                            if new_norm != old_norm:
                                db_val = int(bool(new_norm)) if field == "needs_attention" else (
                                    normalize_phone_display(new_norm) if field == "supplier_phone" else new_norm
                                )
                                db.execute(f"UPDATE orders SET {field} = ?, last_updated = ? WHERE id = ?", (db_val, now_s, oid))
                                log_audit(
                                    db, user["entity_name"], role, "MOBILE_CARD_UPDATE",
                                    f"שדה {COLUMN_LABELS_HE.get(field, field)} שונה מ-'{old_norm}' ל-'{new_norm}'",
                                    order_ref
                                )
                                changed_count += 1
                        if changed_count > 0:
                            db.commit()
                            st.success(f"נשמרו {changed_count} שינויים בהצלחה!")
                            st.rerun()
                        else:
                            st.info("לא בוצעו שינויים בשדות.")

                ph_wa = normalize_phone_whatsapp(o.get("supplier_phone", ""))
                if ph_wa:
                    quick_msg = build_whatsapp_message(o["supplier_name"], o.get("contact_person", ""), [o], DEFAULT_PORTAL_URL)
                    st.link_button(
                        f"📲 שלח וואטסאפ ל-{o['supplier_name']} על הזמנה זו",
                        f"https://wa.me/{ph_wa}?text={urllib.parse.quote(quick_msg)}",
                        use_container_width=True
                    )
    else:
        df_view = pd.DataFrame(filtered)
        df_view["needs_attention"] = df_view["needs_attention"].apply(lambda x: bool(int(x or 0)))
        display_cols = [
            "id", "order_manager", "order_number", "line_number", "part_number",
            "item_description", "quantity", "supplier_name", "contact_person",
            "supplier_phone", "due_date", "פיגור בימים", "סטטוס שבועי",
            "supplier_status", "expected_date", "supplier_note", "mador_response", "needs_attention"
        ]
        df_view = df_view[[c for c in display_cols if c in df_view.columns]]

        allowed_for_role = ROLE_ALLOWED_FIELDS.get(role, set())
        disabled_cols = [c for c in df_view.columns if c not in allowed_for_role]

        col_cfg = {
            "id": None,
            "order_manager": st.column_config.SelectboxColumn("מנהל ההזמנה", options=ORDER_MANAGERS),
            "order_number": st.column_config.TextColumn("מס' הזמנה"),
            "line_number": st.column_config.TextColumn("שורה"),
            "part_number": st.column_config.TextColumn("מק\"ט"),
            "item_description": st.column_config.TextColumn("תיאור פריט"),
            "quantity": st.column_config.TextColumn("כמות"),
            "supplier_name": st.column_config.TextColumn("ספק"),
            "contact_person": st.column_config.TextColumn("איש קשר"),
            "supplier_phone": st.column_config.TextColumn("טלפון"),
            "due_date": st.column_config.TextColumn("תאריך יעד"),
            "supplier_status": st.column_config.SelectboxColumn("סטטוס ספק", options=SUPPLIER_STATUS_OPTIONS),
            "expected_date": st.column_config.TextColumn("צפי ספק"),
            "supplier_note": st.column_config.TextColumn("הערת ספק"),
            "mador_response": st.column_config.TextColumn("מענה מנהל ההזמנה"),
            "needs_attention": st.column_config.CheckboxColumn("דרוש טיפול")
        }

        edited_df = st.data_editor(
            df_view,
            column_config=col_cfg,
            disabled=disabled_cols,
            hide_index=True,
            use_container_width=True,
            key="main_orders_editor"
        )

        changes = []
        orig_map = {row["id"]: row for row in filtered}
        for _, erow in edited_df.iterrows():
            oid = erow["id"]
            orig = orig_map.get(oid)
            if not orig:
                continue
            for field in allowed_for_role:
                if field in erow:
                    old_norm = normalize_field_for_compare(field, orig.get(field))
                    new_norm = normalize_field_for_compare(field, erow[field])
                    if new_norm != old_norm:
                        changes.append({
                            "id": oid,
                            "order_ref": f"{orig['order_number']}/{orig['line_number']}",
                            "field": field,
                            "field_label": COLUMN_LABELS_HE.get(field, field),
                            "old": str(old_norm),
                            "new": str(new_norm),
                            "raw_new": new_norm
                        })

        if changes:
            st.warning(f"⚠️ זוהו {len(changes)} שינויים בטבלה. אנא בדוק את טבלת ההשוואה ואשר שמירה:")
            st.dataframe(
                pd.DataFrame(changes)[["order_ref", "field_label", "old", "new"]].rename(
                    columns={"order_ref": "הזמנה/שורה", "field_label": "שדה", "old": "ערך קודם", "new": "ערך חדש"}
                ),
                hide_index=True,
                use_container_width=True
            )
            if st.button("✅ אשר ובצע שמירה דיפרנציאלית למסד הנתונים", type="primary", use_container_width=True):
                now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
                for ch in changes:
                    field = ch["field"]
                    if field not in ROLE_ALLOWED_FIELDS.get(role, set()):
                        continue
                    raw_new = ch["raw_new"]
                    val = int(bool(raw_new)) if field == "needs_attention" else (
                        normalize_phone_display(raw_new) if field == "supplier_phone" else clean_input(raw_new)
                    )
                    db.execute(f"UPDATE orders SET {field} = ?, last_updated = ? WHERE id = ?", (val, now_s, ch["id"]))
                    log_audit(
                        db, user["entity_name"], role, "FIELD_UPDATE",
                        f"שדה {ch['field_label']} שונה מ-'{ch['old']}' ל-'{ch['new']}'", ch["order_ref"]
                    )
                db.commit()
                st.success("השינויים נשמרו בהצלחה ללא דריסת שדות מקבילים!")
                st.rerun()

    st.write("")
    if st.button("📥 הורד דוח מאוחד ומוגן ל-Excel", use_container_width=True):
        out = BytesIO()
        df_export = pd.DataFrame(filtered)
        export_cols = [
            "order_manager", "order_number", "line_number", "part_number",
            "item_description", "quantity", "supplier_name", "contact_person",
            "supplier_phone", "due_date", "פיגור בימים", "סטטוס שבועי",
            "supplier_status", "expected_date", "supplier_note", "mador_response"
        ]
        df_export = df_export[[c for c in export_cols if c in df_export.columns]].rename(columns=COLUMN_LABELS_HE)
        safe_df = sanitize_dataframe_for_excel(df_export)
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            safe_df.to_excel(writer, index=False, sheet_name="Orders_Report")
        st.download_button(
            "⬇️ לחץ כאן להורדת קובץ האקסל",
            data=out.getvalue(),
            file_name=f"SAPakim_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )


def _render_tab_attachments_and_history(db: DBWrapper, user: dict, all_orders: list[dict]):
    if not all_orders:
        st.info("אין הזמנות פעילות.")
        return

    options_map = {
        f"הזמנה {o['order_number']} | שורה {o['line_number']} | {o['supplier_name']} ({o['order_manager']})": o
        for o in all_orders
    }
    selected_label = st.selectbox("בחר שורת הזמנה לצפייה בשרשור תגובות, העלאת שרטוט או היסטוריה:", list(options_map.keys()))
    selected_order = options_map[selected_label]

    render_attachments_and_comments_widget(db, selected_order, user, key_prefix="staff_")
    st.divider()
    st.markdown("#### 📜 היסטוריית שינויים מלאה לשורה זו (Row Audit Trail)")
    ref = f"{selected_order['order_number']}/{selected_order['line_number']}"
    hist = db.fetchall("SELECT timestamp, actor_name, actor_role, action_type, details FROM audit_logs WHERE order_ref = ? ORDER BY id DESC", (ref,))
    if hist:
        st.dataframe(pd.DataFrame(hist), use_container_width=True, hide_index=True)
    else:
        st.caption("טרם נרשמו שינויים בהיסטוריה לשורה זו.")


def _render_tab_whatsapp(db: DBWrapper, user: dict, all_orders: list[dict]):
    """מרכז וואטסאפ אוניברסלי עם תיבת תצוגה בהירה ומותאמת לנייד ללא חיתוך טקסט."""
    st.markdown("#### 📲 מרכז שיגור וואטסאפ ותזכורות לספקים")
    st.caption("💡 קישורי הוואטסאפ פועלים מהנייד ומהמחשב. כל לחיצה פותחת את הצ'אט מוכן עם ההודעה – שלח וסמן 'נשלח' כדי לעבור לספק הבא.")

    if "wa_sent_suppliers" not in st.session_state:
        st.session_state.wa_sent_suppliers = set()

    c1, c2 = st.columns([1, 1])
    stale_days = c1.number_input("סנן ספקים שלא עדכנו סטטוס מעל X ימים (0 = כל הספקים הפתוחים):", min_value=0, max_value=90, value=0)
    portal_url = c2.text_input("כתובת הפורטל לשליחה:", value=DEFAULT_PORTAL_URL)

    open_orders = [o for o in all_orders if o["supplier_status"] != "סופק"]
    now_dt = datetime.now()
    if stale_days > 0:
        filtered_orders = []
        for o in open_orders:
            if not o.get("last_supplier_update"):
                filtered_orders.append(o)
            else:
                try:
                    up_dt = datetime.strptime(o["last_supplier_update"], "%d/%m/%Y %H:%M")
                    if (now_dt - up_dt).days >= stale_days:
                        filtered_orders.append(o)
                except ValueError:
                    filtered_orders.append(o)
    else:
        filtered_orders = open_orders

    sup_groups = {}
    for o in filtered_orders:
        sname = o["supplier_name"]
        if not sname:
            continue
        sup_groups.setdefault(sname, []).append(o)

    if not sup_groups:
        st.info("לא נמצאו ספקים העונים לתנאי הסינון.")
        return

    all_sup_names = list(sup_groups.keys())
    col_sel1, col_sel2 = st.columns([2, 1])
    select_all = col_sel2.checkbox(f"בחר את כל הספקים ({len(all_sup_names)})", value=False)
    selected_suppliers = col_sel1.multiselect(
        "בחר ספקים לתור השליחה:",
        all_sup_names,
        default=all_sup_names if select_all else all_sup_names[:5]
    )

    if not selected_suppliers:
        return

    sent_count = sum(1 for s in selected_suppliers if s in st.session_state.wa_sent_suppliers)
    st.progress(sent_count / len(selected_suppliers), text=f"התקדמות שליחה בתור הנוכחי: {sent_count} מתוך {len(selected_suppliers)} ספקים סומנו כנשלחו")

    if sent_count > 0 and st.button("🔄 אפס סימוני 'נשלח' להתחלה מחדש"):
        st.session_state.wa_sent_suppliers = set()
        st.rerun()

    for idx, sname in enumerate(selected_suppliers, start=1):
        s_orders = sup_groups[sname]
        contact = s_orders[0].get("contact_person", "")
        phone_wa = normalize_phone_whatsapp(s_orders[0].get("supplier_phone", ""))
        msg = build_whatsapp_message(sname, contact, s_orders, portal_url)
        encoded = urllib.parse.quote(msg)
        wa_url = f"https://wa.me/{phone_wa}?text={encoded}" if phone_wa else ""
        is_sent = sname in st.session_state.wa_sent_suppliers
        status_icon = "✅ נשלח" if is_sent else f"#{idx} ממתין לשליחה"

        with st.expander(f"{status_icon} | {sname} (איש קשר: {contact or 'לא הוגדר'} | {len(s_orders)} שורות)", expanded=not is_sent):
            st.markdown(f"<div class='wa-preview-box'>{escape_html(msg)}</div>", unsafe_allow_html=True)
            b1, b2 = st.columns([1.5, 1])
            if wa_url:
                b1.link_button(f"📲 פתח וואטסאפ אל {sname}", wa_url, type="primary", use_container_width=True)
            else:
                b1.warning("חסר מספר טלפון תקין לספק זה.")

            if not is_sent:
                if b2.button("✅ סמן כנשלח (עבור לבא)", key=f"mark_sent_{sname}_{idx}", use_container_width=True):
                    st.session_state.wa_sent_suppliers.add(sname)
                    st.rerun()
            else:
                if b2.button("↩️ בטל סימון נשלח", key=f"unmark_sent_{sname}_{idx}", use_container_width=True):
                    st.session_state.wa_sent_suppliers.discard(sname)
                    st.rerun()


def _render_tab_excel_upload(db: DBWrapper, user: dict):
    role = user["role"]
    scope = user.get("order_manager_scope", "ALL")
    st.markdown(f"#### 📥 טעינת קובץ אקסל (הרשאת טעינה נוכחית: `{scope}`)")

    up_excel = st.file_uploader("בחר קובץ אקסל (.xlsx):", type=["xlsx"])
    if not up_excel:
        return

    ok, msg = validate_uploaded_file(up_excel)
    if not ok:
        st.error(msg)
        return

    df_raw = pd.read_excel(up_excel)
    df_raw.columns = df_raw.columns.astype(str).str.strip()

    preview_rows = []
    skipped_by_scope = 0

    for _, r in df_raw.iterrows():
        r_dict = r.to_dict()
        order_num = clean_input(r_dict.get("מספר הזמנה") or r_dict.get("הזמנה")).split(".")[0]
        line_num = clean_input(r_dict.get("שורה") or r_dict.get("מספר שורה") or "10").split(".")[0]
        if not order_num:
            continue

        mgr = infer_order_manager(r_dict)
        if role != "admin" and scope != "ALL" and mgr != scope:
            skipped_by_scope += 1
            continue

        sup_note_raw = clean_input(r_dict.get("תגובת ספק"))
        if any(p in sup_note_raw for p in GENERIC_PHRASES_TO_CLEAN):
            sup_note_raw = ""

        preview_rows.append({
            "order_manager": mgr,
            "order_number": order_num,
            "line_number": line_num or "10",
            "part_number": clean_input(r_dict.get("מק\"ט") or r_dict.get("מקט")),
            "item_description": clean_input(r_dict.get("תיאור מוצר") or r_dict.get("שם פריט") or r_dict.get("פרט")),
            "quantity": clean_input(r_dict.get("כמות") or "1").split(".")[0],
            "supplier_name": clean_input(r_dict.get("חברה") or r_dict.get("שם ספק") or r_dict.get("ספק")),
            "contact_person": clean_input(r_dict.get("איש קשר")),
            "supplier_phone": normalize_phone_display(r_dict.get("מספר טלפון") or r_dict.get("טלפון")),
            "due_date": clean_input(r_dict.get("תאריך אספקה") or r_dict.get("תאריך יעד"))[:10],
            "internal_status": clean_input(r_dict.get("סטטוס אחרון")),
            "supplier_note_excel": sup_note_raw
        })

    st.info(f"🔎 תצוגה מקדימה לפני כתיבה למסד: נמצאו **{len(preview_rows)}** שורות מורשות לטעינה (דולגו {skipped_by_scope} שורות של מנהלי הזמנה אחרים).")
    if preview_rows:
        st.dataframe(pd.DataFrame(preview_rows).rename(columns=COLUMN_LABELS_HE), use_container_width=True, hide_index=True)
        if st.button("⚡ אשר וטען שורות אלו למסד הנתונים (ללא דריסת תגובות קיימות)", type="primary", use_container_width=True):
            now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
            for pr in preview_rows:
                ensure_supplier_account(db, pr["supplier_name"], pr["contact_person"], pr["supplier_phone"])
                existing = db.fetchone(
                    "SELECT id FROM orders WHERE order_number = ? AND line_number = ?",
                    (pr["order_number"], pr["line_number"])
                )
                if not existing:
                    db.execute("""
                        INSERT INTO orders (
                            order_manager, order_number, line_number, part_number, item_description,
                            quantity, supplier_name, contact_person, supplier_phone, due_date,
                            internal_status, supplier_note, last_updated
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        pr["order_manager"], pr["order_number"], pr["line_number"], pr["part_number"],
                        pr["item_description"], pr["quantity"], pr["supplier_name"], pr["contact_person"],
                        pr["supplier_phone"], pr["due_date"], pr["internal_status"], pr["supplier_note_excel"], now_s
                    ))
                else:
                    db.execute("""
                        UPDATE orders
                        SET order_manager = CASE WHEN ? != 'כללי' THEN ? ELSE order_manager END,
                            part_number = CASE WHEN ? != '' THEN ? ELSE part_number END,
                            item_description = CASE WHEN ? != '' THEN ? ELSE item_description END,
                            quantity = ?,
                            supplier_name = ?,
                            contact_person = CASE WHEN ? != '' THEN ? ELSE contact_person END,
                            supplier_phone = CASE WHEN ? != '' THEN ? ELSE supplier_phone END,
                            due_date = CASE WHEN ? != '' THEN ? ELSE due_date END,
                            internal_status = CASE WHEN ? != '' THEN ? ELSE internal_status END,
                            last_updated = ?
                        WHERE id = ?
                    """, (
                        pr["order_manager"], pr["order_manager"],
                        pr["part_number"], pr["part_number"],
                        pr["item_description"], pr["item_description"],
                        pr["quantity"], pr["supplier_name"],
                        pr["contact_person"], pr["contact_person"],
                        pr["supplier_phone"], pr["supplier_phone"],
                        pr["due_date"], pr["due_date"],
                        pr["internal_status"], pr["internal_status"], now_s, existing["id"]
                    ))
            log_audit(db, user["entity_name"], role, "EXCEL_SYNC", f"נטענו/סונכרנו {len(preview_rows)} שורות מאקסל")
            db.commit()
            st.success("הסנכרון הושלם בהצלחה!")
            st.rerun()


def _render_tab_commander_dashboard(db: DBWrapper, all_orders: list[dict]):
    st.markdown("#### 🎖️ דשבורד מפקד ודוח ביצועים שבועי")
    if not all_orders:
        st.info("אין נתונים להצגה.")
        return

    df = pd.DataFrame(all_orders)
    df["בפיגור"] = df["פיגור בימים"].apply(lambda x: 1 if "🔴" in str(x) else 0)
    df["עודכן_השבוע"] = df["סטטוס שבועי"].apply(lambda x: 1 if "🟢" in str(x) else 0)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**📊 סיכום לפי מנהל ההזמנה:**")
        mgr_summary = df.groupby("order_manager", as_index=False).agg(
            סהכ_שורות=("id", "count"),
            שורות_בפיגור=("בפיגור", "sum"),
            עודכנו_השבוע=("עודכן_השבוע", "sum"),
            דורשות_טיפול=("needs_attention", "sum")
        ).rename(columns={"order_manager": "מנהל ההזמנה"})
        st.dataframe(mgr_summary, use_container_width=True, hide_index=True)

    with col2:
        st.markdown("**🏭 10 הספקים עם כמות השורות הפתוחות הגבוהה ביותר:**")
        sup_summary = df.groupby("supplier_name", as_index=False).agg(
            סהכ_שורות=("id", "count"),
            שורות_בפיגור=("בפיגור", "sum"),
            עודכנו_השבוע=("עודכן_השבוע", "sum")
        ).sort_values(by="שורות_בפיגור", ascending=False).head(10).rename(columns={"supplier_name": "ספק"})
        st.dataframe(sup_summary, use_container_width=True, hide_index=True)


def _render_tab_security_and_backup(db: DBWrapper, user: dict, all_orders: list[dict]):
    if user["role"] != "admin":
        st.warning("לשונית זו מיועדת למנהל המערכת הראשי (Admin) בלבד.")
        return

    st.markdown("#### 🔑 הנפקת סיסמה זמנית / PIN לספק ונעילת חשבונות (Admin Only)")
    suppliers = db.fetchall("SELECT id, entity_name, contact_person, phone, is_locked, failed_attempts, last_login FROM users WHERE role = 'supplier' ORDER BY entity_name")
    if suppliers:
        st.dataframe(pd.DataFrame(suppliers), use_container_width=True, hide_index=True)
        c1, c2 = st.columns(2)
        target_sup = c1.selectbox("בחר ספק לאיפוס סיסמה / הנפקת קישור ו-PIN חדשים:", [s["entity_name"] for s in suppliers])
        if c1.button("🔄 הנפק סיסמה זמנית + PIN + קישור 128-ביט חדשים", type="primary", use_container_width=True):
            creds = issue_new_supplier_credentials(db, target_sup, user["entity_name"])
            st.success(f"אמצעי זיהוי חדשים הונפקו עבור **{target_sup}** (מוצגים כעת בלבד ואינם נשמרים בטקסט גלוי):")
            st.code(
                f"שם ספק לכניסה: {creds['supplier_name']}\n"
                f"סיסמה זמנית חד-פעמית: {creds['temp_password']}\n"
                f"קוד PIN נפרד (אל תשלח יחד עם הקישור!): {creds['pin']}\n"
                f"קישור 128-ביט (בתוקף עד {creds['expires_at']}):\n"
                f"{DEFAULT_PORTAL_URL}/?token={creds['raw_token']}",
                language="text"
            )

        lock_sup = c2.selectbox("בחר ספק לנעילה / שחרור נעילה (Kill Switch):", [s["entity_name"] for s in suppliers], key="lock_sel")
        if c2.button("🔒 החלף מצב נעילה לספק", use_container_width=True):
            cur = db.fetchone("SELECT is_locked FROM users WHERE role = 'supplier' AND entity_name = ?", (lock_sup,))
            new_lock = 0 if cur and cur["is_locked"] else 1
            db.execute("UPDATE users SET is_locked = ?, failed_attempts = 0, locked_until = '' WHERE role = 'supplier' AND entity_name = ?", (new_lock, lock_sup))
            log_audit(db, user["entity_name"], "admin", "TOGGLE_LOCK", f"מצב נעילה לספק {lock_sup} שונה ל-{new_lock}")
            db.commit()
            st.success("מצב הנעילה עודכן!")
            st.rerun()

    st.divider()
    st.markdown("#### 🗑️ מחיקה רכה (Soft Delete) ושחזור הזמנות (מותנה בקבלת מענה ספק)")
    eligible_for_delete = [
        o for o in all_orders
        if (o.get("supplier_status") and o["supplier_status"] != "טרם עודכן") or o.get("supplier_note")
    ]
    del_map = {f"הזמנה {o['order_number']}/{o['line_number']} ({o['supplier_name']} - {o['supplier_status']})": o["id"] for o in eligible_for_delete}
    sel_del = st.multiselect("בחר שורות שקיבלו מענה ספק להעברה לארכיון (מחיקה רכה):", list(del_map.keys()))
    if sel_del and st.button("🗑️ העבר שורות נבחרות לארכיון (מחיקה רכה)", use_container_width=True):
        now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
        for lbl in sel_del:
            oid = del_map[lbl]
            db.execute("UPDATE orders SET is_deleted = 1, deleted_at = ?, deleted_by = ? WHERE id = ?", (now_s, user["entity_name"], oid))
            log_audit(db, user["entity_name"], "admin", "SOFT_DELETE", f"שורה הועברה לארכיון: {lbl}")
        db.commit()
        st.success("השורות הועברו לארכיון בהצלחה (ניתנות לשחזור).")
        st.rerun()

    archived = db.fetchall("SELECT id, order_number, line_number, supplier_name, deleted_at, deleted_by FROM orders WHERE is_deleted = 1")
    if archived:
        rest_map = {f"הזמנה {a['order_number']}/{a['line_number']} ({a['supplier_name']}) - נמחק ב-{a['deleted_at']}": a["id"] for a in archived}
        sel_rest = st.multiselect("שחזור שורות מהארכיון:", list(rest_map.keys()))
        if sel_rest and st.button("♻️ שחזר שורות נבחרות לפורטל", use_container_width=True):
            for lbl in sel_rest:
                db.execute("UPDATE orders SET is_deleted = 0, deleted_at = '', deleted_by = '' WHERE id = ?", (rest_map[lbl],))
                log_audit(db, user["entity_name"], "admin", "RESTORE_ROW", f"שורה שוחזרה מהארכיון: {lbl}")
            db.commit()
            st.success("השורות שוחזרו בהצלחה!")
            st.rerun()

    st.divider()
    st.markdown("#### 💾 גיבוי מערכת מלא ל-Excel (ללא חשיפת סיסמאות או אסימונים)")
    if st.button("📦 הפק קובץ גיבוי מערכת מלא (Orders + Users Metadata + Audit Log)", use_container_width=True):
        out = BytesIO()
        orders_df = sanitize_dataframe_for_excel(pd.DataFrame(db.fetchall("SELECT * FROM orders")))
        users_df = sanitize_dataframe_for_excel(pd.DataFrame(db.fetchall(
            "SELECT id, username, role, entity_name, order_manager_scope, contact_person, phone, is_locked, last_login FROM users"
        )))
        logs_df = sanitize_dataframe_for_excel(pd.DataFrame(db.fetchall("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 2000")))

        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            orders_df.to_excel(writer, index=False, sheet_name="Orders")
            users_df.to_excel(writer, index=False, sheet_name="Users_Safe")
            logs_df.to_excel(writer, index=False, sheet_name="Audit_Logs")

        st.download_button(
            "⬇️ הורד גיבוי מערכת מלא (.xlsx)",
            data=out.getvalue(),
            file_name=f"SAPakim_Full_Backup_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )


# ==============================================================================
# פרק 7: נקודת כניסה ראשית וניהול פג תוקף חיבור (Main Entry & Session Timeout)
# ==============================================================================

def main():
    inject_custom_css()
    init_db()
    db = DBWrapper()

    try:
        if "user" not in st.session_state:
            st.session_state.user = None
        if "last_activity" not in st.session_state:
            st.session_state.last_activity = datetime.now()

        if st.session_state.user:
            elapsed = (datetime.now() - st.session_state.last_activity).total_seconds() / 60.0
            if elapsed > SESSION_TIMEOUT_MINUTES:
                st.session_state.user = None
                st.query_params.clear()
                st.warning("נותקת אוטומטית מהמערכת עקב חוסר פעילות. אנא התחבר מחדש.")
                return
            st.session_state.last_activity = datetime.now()

        if not st.session_state.user:
            render_login_view(db)
            st.markdown("<div class='watermark'>Powered by BEN HUR</div>", unsafe_allow_html=True)
            return

        user = st.session_state.user
        contact_suffix = f" (איש קשר: {user['contact_person']})" if user["role"] == "supplier" and user.get("contact_person") else ""
        role_he = {"admin": "מנהל מערכת ראשי", "manager": "מנהל הזמנה", "mador": "מנהל הזמנה", "supplier": "ספק"}.get(user["role"], user["role"])

        col_h, col_b = st.columns([5, 1])
        with col_h:
            st.markdown(f"""
                <div class="header-box">
                    <div class="header-title">🛡️ SAPakim | שלום, {escape_html(user['entity_name'])}{escape_html(contact_suffix)}</div>
                    <div class="header-sub">הרשאה: {escape_html(role_he)}</div>
                </div>
            """, unsafe_allow_html=True)
        with col_b:
            st.write("")
            if st.button("התנתק 🚪", use_container_width=True):
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

        if user["role"] == "supplier":
            render_supplier_portal(db, user)
        else:
            render_staff_dashboard(db, user)

        st.markdown("<div class='watermark'>Powered by BEN HUR</div>", unsafe_allow_html=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
