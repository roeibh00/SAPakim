"""
================================================================================
מערכת SAPakim - פורטל ארגוני מאובטח לניהול ותיקוף הזמנות חט"ל מול ספקים ומדורים
פותח ע"י: רועי בן חור (Powered by BEN HUR)
================================================================================
מבנה הקוד (ארכיטקטורה מודולרית להעברה נוחה למתכנת):
- פרק 1: הגדרות מערכת, קבועים והרשאות שדות בצד השרת (Config & Server RBAC)
- פרק 2: שכבת עיצוב ותצוגה מימין לשמאל (UI & RTL Styling)
- פרק 3: שכבת אבטחת מידע, הצפנת scrypt והגנת קלט/אקסל (Security & Crypto Engine)
- פרק 4: שכבת מסד הנתונים - Neon PostgreSQL / SQLite (Database Layer)
- פרק 5: לוגיקה עסקית, מיזוג אקסל (VLOOKUP), קבצים מצורפים ווואטסאפ (Business Logic)
- פרק 6: מסכי המערכת לפי הרשאות (Views: Login, Admin/Mador Dashboard, Supplier)
- פרק 7: נקודת כניסה ראשית וניהול פג תוקף חיבור (Main Entry & Session Timeout)
================================================================================
"""

import hashlib
import hmac
import html
import os
import re
import secrets
import sqlite3
import urllib.parse
from datetime import datetime, timedelta
from io import BytesIO

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# ==============================================================================
# פרק 1: הגדרות מערכת, קבועים והרשאות שדות בצד השרת (Config & Server RBAC)
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

SUPPLIER_STATUS_OPTIONS = [
    "טרם עודכן",
    "תקין - בייצור",
    "עיכוב בחומר גלם",
    "ממתין לשרטוט / מפרט טכני",
    "ממתין לבק\"מ / בחינה",
    "מוכן לאספקה / משלוח",
    "סופק"
]

ORDER_MANAGERS = ["נמ\"ר", "מרכבה", "איתן", "מנה\"ר", "כללי"]

# אכיפת הרשאות שדות בצד השרת (תיקון #7 - מניעת דריסת שדות ספק ע"י מדור ולהפך)
ROLE_ALLOWED_FIELDS = {
    "supplier": {"supplier_status", "expected_date", "supplier_note", "needs_attention"},
    "mador": {
        "part_number", "item_description", "quantity", "contact_person",
        "supplier_phone", "due_date", "internal_status", "mador_response",
        "needs_attention"
    },
    "admin": {
        "order_manager", "order_number", "line_number", "part_number",
        "item_description", "quantity", "supplier_name", "contact_person",
        "supplier_phone", "due_date", "internal_status", "supplier_status",
        "expected_date", "supplier_note", "mador_response", "needs_attention"
    }
}

GENERIC_PHRASES_TO_CLEAN = [
    "כל השאר אבדוק ואעדכן",
    "כל השאר סופק",
    "אבדוק ואעדכן"
]


# ==============================================================================
# פרק 2: שכבת עיצוב ותצוגה מימין לשמאל (UI & RTL Styling)
# ==============================================================================

def inject_custom_css():
    """מזריק עיצוב אחיד, רשמי ומיושר לימין (RTL) לכלל רכיבי האתר."""
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700&display=swap');
        :root, html, body, .stApp {
            color-scheme: light !important;
            font-family: 'Rubik', Arial, sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
            background: linear-gradient(180deg, #fffbeb 0%, #f8fafc 35%, #f1f5f9 100%) !important;
            color: #0f172a !important;
        }
        .block-container {
            max-width: 1280px !important;
            padding-top: 3.8rem !important;
            padding-bottom: 3rem !important;
            margin: 0 auto !important;
        }
        .header-box {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 65%, #78350f 100%);
            color: #ffffff !important;
            padding: 1.2rem 1.8rem;
            border-radius: 16px;
            border-bottom: 4px solid #f59e0b;
            margin-bottom: 1.2rem;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.1);
        }
        .header-title { font-size: 1.45rem !important; font-weight: 700 !important; color: #ffffff !important; margin: 0 !important; }
        .header-sub { font-size: 0.9rem !important; color: #fcd34d !important; margin-top: 0.25rem !important; }
        .kpi-card {
            background: #ffffff;
            border: 1px solid #fde68a;
            border-right: 5px solid #f59e0b;
            border-radius: 12px;
            padding: 0.9rem 1rem;
            text-align: center;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
        }
        .kpi-num { font-size: 1.55rem; font-weight: 700; color: #b45309; }
        .kpi-label { font-size: 0.85rem; color: #475569; font-weight: 500; }
        .watermark {
            text-align: center; font-size: 0.8rem; color: #64748b !important;
            margin-top: 2.5rem; font-weight: 600; letter-spacing: 0.5px;
        }
        input, textarea, select, [data-testid="stDataFrame"], th, td {
            direction: rtl !important;
            text-align: right !important;
            unicode-bidi: plaintext !important;
        }
    </style>
    """, unsafe_allow_html=True)


# ==============================================================================
# פרק 3: שכבת אבטחת מידע, הצפנת scrypt והגנת קלט/אקסל (Security & Crypto Engine)
# ==============================================================================

def hash_secret(secret_text: str) -> str:
    """
    מצפין סיסמה או קוד PIN באמצעות scrypt עם Salt אקראי (תיקון #1 ו-#4).
    לעולם לא שומר סיסמאות בטקסט גלוי.
    """
    if not secret_text:
        return ""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        secret_text.strip().encode("utf-8"),
        salt=salt, n=16384, r=8, p=1, dklen=32
    )
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_secret(secret_text: str, stored_hash: str) -> bool:
    """מאמת סיסמה או PIN מול הגיבוב השמור במסד הנתונים."""
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
    """גיבוב SHA-256 מהיר לחיפוש אסימוני גישה של 128 ביט."""
    return hashlib.sha256(token_str.strip().encode("utf-8")).hexdigest()


def safe_text(val) -> str:
    """מנקה טקסט למניעת הזרקת HTML / XSS (תיקון #10 ו-#11)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return html.escape(str(val).strip())


def sanitize_excel_value(val):
    """
    מונע הזרקת נוסחאות באקסל (CSV/Formula Injection - תיקון #12).
    אם תא מתחיל ב- =, +, -, @ מוסיף גרש בודד בתחילתו.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val)
    if s.startswith(("=", "+", "-", "@")):
        return "'" + s
    return s


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
# פרק 4: שכבת מסד הנתונים - Neon PostgreSQL / SQLite (Database Layer)
# ==============================================================================

def get_database_url() -> str:
    """שולף את כתובת מסד הנתונים מ-Secrets או ממשתני הסביבה."""
    try:
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    return os.environ.get("DATABASE_URL", "")


class DBWrapper:
    """מעטפת אחידה ל-Neon PostgreSQL ול-SQLite המקומי (כולל תיקון sqlite3.Row #15)."""
    def __init__(self):
        self.db_url = get_database_url()
        self.is_postgres = bool(self.db_url and HAS_PSYCOPG2)
        if self.is_postgres:
            self.conn = psycopg2.connect(self.db_url)
        else:
            self.conn = sqlite3.connect("sapakim_secure_v2.db", check_same_thread=False)
            self.conn.row_factory = sqlite3.Row

    def execute(self, query: str, params: tuple = ()):
        if self.is_postgres:
            pg_query = query.replace("?", "%s")
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(pg_query, params)
            return cur
        else:
            cur = self.conn.cursor()
            cur.execute(query, params)
            return cur

    def fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        cur = self.execute(query, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]

    def fetchone(self, query: str, params: tuple = ()) -> dict | None:
        cur = self.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row is not None else None

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def init_db():
    """מקים את טבלאות המערכת המאובטחות ומזין חשבונות צוות מ-Secrets בלבד."""
    try:
        db = DBWrapper()
        id_serial = "SERIAL PRIMARY KEY" if db.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        blob_type = "BYTEA" if db.is_postgres else "BLOB"

        # 1. טבלת משתמשים וספקים (ללא סיסמאות גלויות)
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

        # 2. טבלת הזמנות (כולל מחיקה רכה is_deleted ושיוך מנהל ההזמנה)
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

        # 3. טבלת קבצים מצורפים ושרטוטים (תיקון #11)
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

        # 4. טבלת שרשור תגובות לכל שורה
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

        # 5. טבלת היסטוריית שינויים לשורה + יומן אבטחה (ללא חשיפת סיסמאות)
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

        # טעינת מפתחות צוות מ-st.secrets (עם fallback בטוח לסביבת פיתוח מקומית)
        staff_secrets = {}
        try:
            if "staff_keys" in st.secrets:
                staff_secrets = dict(st.secrets["staff_keys"])
        except Exception:
            pass

        default_staff = [
            ("admin", "admin", "רועי - מנהל מערכת", "ALL", staff_secrets.get("ADMIN_KEY", "BH-ADMIN-9920")),
            ("namer", "mador", "מדור נמ\"ר", "נמ\"ר", staff_secrets.get("NAMER_KEY", "NAMER-7741")),
            ("merkava", "mador", "מדור מרכבה", "מרכבה", staff_secrets.get("MERKAVA_KEY", "MERKAVA-5582")),
            ("eitan", "mador", "מדור איתן", "איתן", staff_secrets.get("EITAN_KEY", "EITAN-6614")),
            ("manhar", "mador", "מנה\"ר רכש", "מנה\"ר", staff_secrets.get("MANHAR_KEY", "MANHAR-3319")),
        ]

        for uname, role, ename, scope, raw_pwd in default_staff:
            existing = db.fetchone("SELECT id FROM users WHERE username = ?", (uname,))
            if not existing:
                db.execute("""
                    INSERT INTO users (username, role, entity_name, order_manager_scope, password_hash)
                    VALUES (?, ?, ?, ?, ?)
                """, (uname, role, ename, scope, hash_secret(raw_pwd)))

        db.commit()
        db.close()
    except Exception:
        # תיקון #13: מניעת הדפסת שגיאות מסד נתונים (st.code(str(exc))) למבקרים
        st.error("אירעה שגיאת תקשורת פנימית מול שרת הנתונים. נא לפנות למנהל המערכת.")
        st.stop()


def log_audit(db: DBWrapper, actor_name: str, actor_role: str, action_type: str, details: str, order_ref: str = ""):
    """מתעד פעולה ביומן הביקורת (לעולם לא רושם סיסמאות או מפתחות גלויים)."""
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    db.execute("""
        INSERT INTO audit_logs (timestamp, actor_name, actor_role, action_type, order_ref, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (now_str, safe_text(actor_name), safe_text(actor_role), safe_text(action_type), safe_text(order_ref), safe_text(details)))


# ==============================================================================
# פרק 5: לוגיקה עסקית, מיזוג אקסל (VLOOKUP), קבצים מצורפים ווואטסאפ (Business Logic)
# ==============================================================================

def normalize_phone_display(val) -> str:
    """מנרמל מספר טלפון לתצוגה תקנית (למשל 546966537 -> 0546966537)."""
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
    """ממיר מספר טלפון לפורמט בינלאומי 972 לשליחת וואטסאפ."""
    disp = normalize_phone_display(val)
    if not disp or len(disp) < 9:
        return ""
    if disp.startswith("0"):
        return "972" + disp[1:]
    return disp


def infer_order_manager(row_dict: dict) -> str:
    """מזהה שיוך מדור אוטומטי מהאקסל או מתוך תיאור הפריט."""
    explicit = str(row_dict.get("מנהל ההזמנה", "") or row_dict.get("מדור", "")).strip()
    for m in ORDER_MANAGERS:
        if m in explicit:
            return m
    desc = str(row_dict.get("תיאור מוצר", "") or row_dict.get("שם פריט", "") or row_dict.get("פרט", ""))
    if "נמר" in desc or "נמ\"ר" in desc:
        return "נמ\"ר"
    if "מרכבה" in desc or "441" in desc:
        return "מרכבה"
    if "איתן" in desc:
        return "איתן"
    return "כללי"


def calc_delay_days(due_date_str: str, supplier_status: str) -> tuple[int, str]:
    """מחשב בזמן אמת את הפרש הימים מול תאריך היעד המקורי."""
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
    """מוודא שלכל ספק מהאקסל קיים חשבון ממודר בטבלת users."""
    clean_name = safe_text(supplier_name)
    if not clean_name:
        return
    existing = db.fetchone("SELECT id FROM users WHERE role = 'supplier' AND entity_name = ?", (clean_name,))
    if not existing:
        initial_pwd = secrets.token_urlsafe(6)
        initial_pin = f"{secrets.randbelow(900000) + 100000}"
        raw_token = secrets.token_hex(16)  # 128-bit token
        exp = (datetime.now() + timedelta(days=TOKEN_EXPIRY_DAYS)).strftime("%Y-%m-%d")
        db.execute("""
            INSERT INTO users (
                username, role, entity_name, order_manager_scope,
                password_hash, pin_hash, token_hash, token_expires_at,
                contact_person, phone, must_change_password
            ) VALUES (?, 'supplier', ?, 'SUPPLIER', ?, ?, ?, ?, ?, ?, 1)
        """, (
            clean_name, clean_name,
            hash_secret(initial_pwd), hash_secret(initial_pin),
            hash_token_fast(raw_token), exp,
            safe_text(contact_person), normalize_phone_display(phone)
        ))
    else:
        db.execute("""
            UPDATE users SET contact_person = CASE WHEN ? != '' THEN ? ELSE contact_person END,
                             phone = CASE WHEN ? != '' THEN ? ELSE phone END
            WHERE role = 'supplier' AND entity_name = ?
        """, (safe_text(contact_person), safe_text(contact_person),
              normalize_phone_display(phone), normalize_phone_display(phone), clean_name))


def issue_new_supplier_credentials(db: DBWrapper, supplier_name: str, actor_name: str) -> dict:
    """
    מנפיק לספק סיסמה זמנית חד-פעמית, קוד PIN נפרד בן 6 ספרות ואסימון 128-ביט עם תוקף.
    מחזיר אותם למנהל פעם אחת בלבד על המסך (תיקונים #1, #2, #3, #4, #6).
    """
    temp_password = f"SUP-{secrets.token_hex(3).upper()}"
    new_pin = f"{secrets.randbelow(900000) + 100000}"
    raw_token = secrets.token_hex(16)  # 128-bit
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
    """
    בונה הודעת וואטסאפ תקנית לספק.
    תיקון קריטי #2: לעולם לא מדביק את ה-PIN או הסיסמה בתוך הודעת הוואטסאפ!
    """
    greeting_name = f"{contact_person} ({supplier_name})" if contact_person else supplier_name
    lines_text = []
    for o in orders_list[:12]:
        lines_text.append(
            f"• הזמנה {o['order_number']} (שורה {o['line_number']}) | מק\"ט {o['part_number']} - {o['item_description']}"
        )
    if len(orders_list) > 12:
        lines_text.append(f"...ועוד {len(orders_list) - 12} שורות נוספות בפורטל.")

    link_To_send = f"{portal_url}/?token={raw_token}" if raw_token else portal_url
    msg = (
        f"שלום {greeting_name},\n"
        f"בהמשך למעקב הזמנות חט\"ל, להלן ההזמנות הפתוחות הממתינות לעדכון סטטוס וצפי אספקה:\n\n"
        + "\n".join(lines_text) +
        f"\n\nלכניסה מאובטחת לפורטל ועדכון ישיר:\n{link_To_send}\n"
        f"(הכניסה באמצעות שם הספק והסיסמה האישית שלך, או באמצעות קוד ה-PIN שנמסר לך בנפרד).\n"
        f"תודה על שיתוף הפעולה."
    )
    return msg


# ==============================================================================
# פרק 6: מסכי המערכת לפי הרשאות (Views: Login, Admin/Mador, Supplier)
# ==============================================================================

def render_login_view(db: DBWrapper):
    """
    מסך התחברות מאובטח:
    - ללא רשימת ספקים פומבית וללא איפוס סיסמה עצמי (תיקון #3)
    - כניסת ספק באמצעות שם ספק + סיסמה (תיקון #2)
    - תמיכה בקישור 128-ביט + אימות PIN אקראי נפרד (תיקון #4)
    - נעילת חשבון בצד השרת לאחר 5 ניסיונות כושלים (תיקון #6)
    """
    st.markdown("""
        <div class="header-box" style="text-align:center;">
            <div class="header-title">🛡️ פורטל SAPakim - מערכת הזמנות חט"ל</div>
            <div class="header-sub">כניסה מאובטחת וממודרת לספקים, מדורים והנהלה</div>
        </div>
    """, unsafe_allow_html=True)

    url_token = st.query_params.get("token", "").strip()

    col_spacer1, col_main, col_spacer2 = st.columns([1, 1.6, 1])
    with col_main:
        # מסלול א': כניסה דרך קישור טוקן 128-ביט (דורש קוד PIN נפרד שלא נשלח בהודעה)
        if url_token:
            token_user = db.fetchone(
                "SELECT * FROM users WHERE token_hash = ? AND role = 'supplier'",
                (hash_token_fast(url_token),)
            )
            if not token_user:
                st.error("קישור הגישה אינו תקף או שפג תוקפו. אנא התחבר עם שם ספק וסיסמה.")
            else:
                st.info(f"🔒 זיהוי קישור עבור: **{token_user['entity_name']}**. להשלמת האימות הדו-שלבי הזן את קוד ה-PIN האישי (שנמסר לך בנפרד):")
                pin_input = st.text_input("קוד PIN (6 ספרות):", type="password", max_chars=10)
                if st.button("אמת כניסה לפורטל 🔓", type="primary", use_container_width=True):
                    _process_auth_attempt(db, token_user, pin_input, is_pin=True)
                st.divider()

        # מסלול ב': כניסה רגילה (שם ספק / שם משתמש צוות + סיסמה)
        st.markdown("#### 🔑 כניסה באמצעות מזהה וסיסמה")
        identifier = st.text_input("שם ספק (כפי שמופיע בהזמנה) או שם משתמש צוות:").strip()
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

        st.caption("שכחת סיסמה או קוד PIN? מטעמי אבטחת מידע, איפוס מתבצע אך ורק מול מנהל המערכת בחט\"ל.")


def _process_auth_attempt(db: DBWrapper, user_row: dict, secret_input: str, is_pin: bool):
    """בודק נעילת חשבון בשרת, מאמת סיסמה/PIN ומנהל מונה ניסיונות כושלים בשרת."""
    now = datetime.now()

    if user_row.get("is_locked") == 1:
        st.error("🔒 החשבון נחסם על ידי מנהל המערכת. יש לפנות למנהל המערכת בחט\"ל.")
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


def render_Attachments_and_comments_widget(db: DBWrapper, order_row: dict, user: dict):
    """רכיב שרשור תגובות והעלאת/הורדת קבצים מצורפים מאומתים לכל שורת הזמנה."""
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
                badge = "🛠️ מדור/חט\"ל" if c["author_role"] in ("admin", "mador") else "🏭 ספק"
                st.markdown(f"- **{badge} ({c['author_name']})** `[{c['created_at']}]`: {c['comment_text']}")

        new_comment = st.text_input("הוסף תגובה חדשה לשרשור:", key=f"comm_in_{oid}")
        if st.button("שלח תגובה 💬", key=f"comm_btn_{oid}"):
            if new_comment.strip():
                now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
                clean_c = safe_text(new_comment)
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
                # הורדה מאומתת לפי הרשאת הזמנה בלבד
                full_att = db.fetchone("SELECT file_data FROM attachments WHERE id = ?", (att["id"],))
                if full_att and full_att.get("file_data") is not None:
                    raw_bytes = bytes(full_att["file_data"])
                    st.download_button(
                        label=f"📥 הורד: {att['filename']} ({att['uploaded_by']})",
                        data=raw_bytes,
                        file_name=att["filename"],
                        key=f"dl_att_{att['id']}_{oid}"
                    )

        up_file = st.file_uploader(
            "צרף שרטוט / מפרט / אישור (PDF, PNG, JPG, XLSX):",
            type=["pdf", "png", "jpg", "jpeg", "xlsx"],
            key=f"up_file_{oid}"
        )
        if up_file and st.button("העלה ושמור מסמך 📎", key=f"up_btn_{oid}"):
            ok, msg = validate_uploaded_file(up_file)
            if not ok:
                st.error(msg)
            else:
                now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
                db.execute("""
                    INSERT INTO attachments (order_id, filename, file_data, uploaded_by, uploaded_role, uploaded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (oid, safe_text(up_file.name), up_file.getvalue(), user["entity_name"], user["role"], now_s))
                log_audit(db, user["entity_name"], user["role"], "UPLOAD_ATTACHMENT", f"הועלה קובץ {up_file.name}", order_ref)
                db.commit()
                st.success("המסמך צורף בהצלחה!")
                st.rerun()


def render_supplier_portal(db: DBWrapper, user: dict):
    """מסך הספק הממודר: מציג אך ורק את הזמנות הספק, עם שדות ליבה נעולים בשרת."""
    sup_name = user["entity_name"]

    # בדיקה אם הספק נדרש להחליף סיסמה זמנית שהונפקה ע"י המנהל
    if user.get("must_change_password") == 1:
        st.warning("🔐 זוהי כניסה עם סיסמה זמנית. אנא בחר כעת סיסמה אישית חדשה (לפחות 6 תווים):")
        new_p1 = st.text_input("סיסמה אישית חדשה:", type="password")
        new_p2 = st.text_input("אימות סיסמה חדשה:", type="password")
        if st.button("עדכן סיסמה אישית 💾", type="primary"):
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

    # סרגל החלה מהירה על כל השורות של הספק
    with st.expander("⚡ עדכון מהיר וגורף לכל השורות שלי", expanded=False):
        c1, c2, c3 = st.columns([1, 1.5, 1])
        bulk_status = c1.selectbox("בחר סטטוס להחלה גורפת:", SUPPLIER_STATUS_OPTIONS, key="bulk_sup_stat")
        bulk_note = c2.text_input("הערה גורפת לכל השורות (אופציונלי):", key="bulk_sup_note")
        if c3.button("⚡ החל על כל השורות שלי", type="primary", use_container_width=True):
            now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
            for o in orders:
                db.execute("""
                    UPDATE orders
                    SET supplier_status = ?,
                        supplier_note = CASE WHEN ? != '' THEN ? ELSE supplier_note END,
                        last_supplier_update = ?, last_updated = ?
                    WHERE id = ? AND supplier_name = ?
                """, (bulk_status, safe_text(bulk_note), safe_text(bulk_note), now_s, now_s, o["id"], sup_name))
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
            st.markdown(
                f"🔒 **נתוני הזמנה (נעולים):** כמות: `{o['quantity']}` | "
                f"תאריך יעד מקורי: `{o['due_date'] or 'לא הוגדר'}` | "
                f"מדור מטפל: `{o['order_manager']}` | "
                f"מענה מדור אחרון: **{o['mador_response'] or 'טרם נרשם מענה'}**"
            )

            col1, col2, col3, col4 = st.columns([1.1, 1.1, 1.5, 0.8])
            cur_stat = o["supplier_status"] if o["supplier_status"] in SUPPLIER_STATUS_OPTIONS else "טרם עודכן"
            new_stat = col1.selectbox(
                "סטטוס ספק:", SUPPLIER_STATUS_OPTIONS,
                index=SUPPLIER_STATUS_OPTIONS.index(cur_stat),
                key=f"s_stat_{o['id']}"
            )

            # תאריך יעד מקורי נעול כברירת מחדל עד לחיצה על "שנה תאריך אספקה"
            default_exp = o["expected_date"] or o["due_date"] or ""
            change_date = col2.checkbox("📅 שנה תאריך אספקה", key=f"chg_dt_{o['id']}")
            if change_date:
                new_exp = col2.date_input("בחר צפי אספקה מעודכן:", key=f"dt_pick_{o['id']}").strftime("%Y-%m-%d")
            else:
                col2.text_input("צפי אספקה (נעול לתאריך המקורי):", value=default_exp, disabled=True, key=f"dt_dis_{o['id']}")
                new_exp = default_exp

            new_note = col3.text_input("הערת ספק / בקשה למדור:", value=o["supplier_note"] or "", key=f"s_note_{o['id']}")
            needs_att = col4.checkbox("🚩 דרוש מענה מדור", value=bool(o["needs_attention"]), key=f"s_att_{o['id']}")

            if st.button("💾 שמור עדכון לשורה זו", key=f"save_sup_{o['id']}", type="primary"):
                now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
                db.execute("""
                    UPDATE orders
                    SET supplier_status = ?, expected_date = ?, supplier_note = ?,
                        needs_attention = ?, last_supplier_update = ?, last_updated = ?
                    WHERE id = ? AND supplier_name = ?
                """, (new_stat, safe_text(new_exp), safe_text(new_note), int(needs_att), now_s, now_s, o["id"], sup_name))
                log_audit(
                    db, sup_name, "supplier", "ROW_UPDATE",
                    f"סטטוס: {new_stat}, צפי: {new_exp}", f"{o['order_number']}/{o['line_number']}"
                )
                db.commit()
                st.success("העדכון נשמר בהצלחה!")
                st.rerun()

            st.divider()
            render_Attachments_and_comments_widget(db, o, user)


def render_staff_dashboard(db: DBWrapper, user: dict):
    """מסך הניהול למדורים ולמנהל המערכת (כולל מידור מדורים, שמירה דיפרנציאלית ודשבורד מפקד)."""
    role = user["role"]
    scope = user.get("order_manager_scope", "ALL")

    # התראות אבטחה בראש מסך המנהל (איפוסים/החלפות סיסמה וניסיונות כושלים)
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

    # שליפת הזמנות לפי הרשאת המדור (מידור אוטומטי - תיקון #7 ו-#8)
    if role == "admin" or scope == "ALL":
        all_orders = db.fetchall("SELECT * FROM orders WHERE is_deleted = 0 ORDER BY order_number, line_number")
    else:
        all_orders = db.fetchall(
            "SELECT * FROM orders WHERE is_deleted = 0 AND order_manager = ? ORDER BY order_number, line_number",
            (scope,)
        )

    # חישוב מדדי KPI ועמודת פיגור בימים
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
    k1.markdown(f"<div class='kpi-card'><div class='kpi-num'>{total_rows}</div><div class='kpi-label'>שורות הזמנה פתוחות ({scope})</div></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='kpi-card'><div class='kpi-num'>{avg_delay}</div><div class='kpi-label'>ממוצע ימי פיגור</div></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='kpi-card'><div class='kpi-num'>🟢 {updated_this_week}</div><div class='kpi-label'>עודכנו השבוע ע\"י ספק</div></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='kpi-card'><div class='kpi-num'>🚩 {attention_count}</div><div class='kpi-label'>דורשות מענה מדור</div></div>", unsafe_allow_html=True)

    st.write("")
    tabs = st.tabs([
        "📋 טבלת הזמנות ומענה מדור",
        "📎 שרטוטים, שרשור תגובות והיסטוריה",
        "📲 מרכז וואטסאפ ותזכורות לספקים",
        "📥 טעינת אקסל ממודרת (VLOOKUP)",
        "📊 דשבורד מפקד ודוח שבועי",
        "🔐 ניהול ספקים, מחיקה רכה וגיבוי"
    ])

    # --- לשונית 1: טבלת הזמנות ושמירה דיפרנציאלית ---
    with tabs[0]:
        _render_tab_orders_table(db, user, all_orders)

    # --- לשונית 2: שרטוטים, שרשור תגובות והיסטוריית שורה ---
    with tabs[1]:
        _render_tab_attachments_and_history(db, user, all_orders)

    # --- לשונית 3: וואטסאפ ותזכורות לספקים שלא עדכנו מעל X ימים ---
    with tabs[2]:
        _render_tab_whatsapp(db, user, all_orders)

    # --- לשונית 4: טעינת אקסל לפי מדור עם תצוגה מקדימה ---
    with tabs[3]:
        _render_tab_excel_upload(db, user)

    # --- לשונית 5: דשבורד מפקד ודוח שבועי ---
    with tabs[4]:
        _render_tab_commander_dashboard(db, all_orders)

    # --- לשונית 6: ניהול סיסמאות ספקים, מחיקה רכה וגיבוי ---
    with tabs[5]:
        _render_tab_security_and_backup(db, user, all_orders)


def _render_tab_orders_table(db: DBWrapper, user: dict, all_orders: list[dict]):
    """מציג את טבלת ההזמנות עם אכיפת הרשאות שדות בצד השרת ושמירה דיפרנציאלית (תיקונים #7 ו-#10)."""
    role = user["role"]
    if not all_orders:
        st.info("אין הזמנות להצגה. ניתן לטעון קובץ אקסל בלשונית 'טעינת אקסל'.")
        return

    c_f1, c_f2, c_f3 = st.columns([1, 1, 1.5])
    mgr_filter = c_f1.selectbox("סינון לפי מנהל הזמנה (מדור):", ["הכל"] + ORDER_MANAGERS)
    att_only = c_f2.checkbox("🚩 הצג רק שורות הדורשות מענה מדור")
    search_q = c_f3.text_input("חיפוש חופשי (מס' הזמנה / מק\"ט / ספק / איש קשר):").strip()

    filtered = all_orders
    if mgr_filter != "הכל":
        filtered = [o for o in filtered if o["order_manager"] == mgr_filter]
    if att_only:
        filtered = [o for o in filtered if o.get("needs_attention")]
    if search_q:
        filtered = [
            o for o in filtered
            if search_q.lower() in f"{o['order_number']} {o['part_number']} {o['item_description']} {o['supplier_name']} {o['contact_person']}".lower()
        ]

    df_view = pd.DataFrame(filtered)
    display_cols = [
        "id", "order_manager", "order_number", "line_number", "part_number",
        "item_description", "quantity", "supplier_name", "contact_person",
        "supplier_phone", "due_date", "פיגור בימים", "סטטוס שבועי",
        "supplier_status", "expected_date", "supplier_note", "mador_response", "needs_attention"
    ]
    df_view = df_view[[c for c in display_cols if c in df_view.columns]]

    # נעילת עמודות לפי תפקיד (למדור נעולות עמודות הספק; למנהל הכל פתוח עם חלונית אישור)
    allowed_for_role = ROLE_ALLOWED_FIELDS.get(role, set())
    disabled_cols = [c for c in df_view.columns if c not in allowed_for_role]

    edited_df = st.data_editor(
        df_view,
        disabled=disabled_cols,
        hide_index=True,
        use_container_width=True,
        key="main_orders_editor"
    )

    # חישוב שינויים דיפרנציאליים (Delta) בלבד - תיקון #7 ו-#10
    changes = []
    orig_map = {row["id"]: row for row in filtered}
    for _, erow in edited_df.iterrows():
        oid = erow["id"]
        orig = orig_map.get(oid)
        if not orig:
            continue
        for field in allowed_for_role:
            if field in erow and str(erow[field]) != str(orig.get(field, "")):
                changes.append({
                    "id": oid,
                    "order_ref": f"{orig['order_number']}/{orig['line_number']}",
                    "field": field,
                    "old": str(orig.get(field, "")),
                    "new": str(erow[field])
                })

    if changes:
        st.warning(f"⚠️ זוהו {len(changes)} שינויים בטבלה. אנא בדוק את טבלת ההשוואה ואשר שמירה:")
        st.dataframe(pd.DataFrame(changes)[["order_ref", "field", "old", "new"]], hide_index=True, use_container_width=True)
        if st.button("✅ אשר ובצע שמירה דיפרנציאלית למסד הנתונים", type="primary"):
            now_s = datetime.now().strftime("%d/%m/%Y %H:%M")
            for ch in changes:
                field = ch["field"]
                # בדיקת Whitelist קשיחה בצד השרת
                if field not in ROLE_ALLOWED_FIELDS.get(role, set()):
                    continue
                val = int(ch["new"] == "True" or ch["new"] == "1") if field == "needs_attention" else safe_text(ch["new"])
                db.execute(f"UPDATE orders SET {field} = ?, last_updated = ? WHERE id = ?", (val, now_s, ch["id"]))
                log_audit(
                    db, user["entity_name"], role, "FIELD_UPDATE",
                    f"שדה {field} שונה מ-'{ch['old']}' ל-'{ch['new']}'", ch["order_ref"]
                )
            db.commit()
            st.success("השינויים נשמרו בהצלחה ללא דריסת שדות מקבילים!")
            st.rerun()

    # ייצוא לאקסל עם הגנה מפני הזרקת נוסחאות (תיקון #12)
    if st.button("📥 הורד דוח מאוחד ומוגן ל-Excel"):
        out = BytesIO()
        safe_df = df_view.copy()
        for col in safe_df.columns:
            safe_df[col] = safe_df[col].apply(sanitize_excel_value)
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            safe_df.to_excel(writer, index=False, sheet_name="Orders_Report")
        st.download_button(
            "⬇️ לחץ כאן להורדת קובץ האקסל",
            data=out.getvalue(),
            file_name=f"SAPakim_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


def _render_tab_attachments_and_history(db: DBWrapper, user: dict, all_orders: list[dict]):
    """ניהול מסמכים מצורפים (שרטוטים/מפרטים), שרשור תגובות והיסטוריית שינויים לשורה."""
    if not all_orders:
        st.info("אין הזמנות פעילות.")
        return

    options_map = {
        f"הזמנה {o['order_number']} | שורה {o['line_number']} | {o['supplier_name']} ({o['item_description']})": o
        for o in all_orders
    }
    selected_label = st.selectbox("בחר שורת הזמנה לצפייה בשרשור תגובות, העלאת שרטוט או היסטוריית שינויים:", list(options_map.keys()))
    selected_order = options_map[selected_label]

    render_Attachments_and_comments_widget(db, selected_order, user)
    st.divider()
    st.markdown("#### 📜 היסטוריית שינויים מלאה לשורה זו (Row Audit Trail)")
    ref = f"{selected_order['order_number']}/{selected_order['line_number']}"
    hist = db.fetchall("SELECT timestamp, actor_name, actor_role, action_type, details FROM audit_logs WHERE order_ref = ? ORDER BY id DESC", (ref,))
    if hist:
        st.dataframe(pd.DataFrame(hist), use_container_width=True, hide_index=True)
    else:
        st.caption("טרם נרשמו שינויים בהיסטוריה לשורה זו.")


def _render_tab_whatsapp(db: DBWrapper, user: dict, all_orders: list[dict]):
    """מרכז שיגור וואטסאפ + סינון ספקים שלא עדכנו מעל X ימים (ללא חשיפת PIN בהודעה)."""
    st.markdown("#### 📲 שיגור הודעות ותזכורות וואטסאפ לספקים")
    c1, c2 = st.columns([1, 1])
    stale_days = c1.number_input("סנן ספקים שלא עדכנו סטטוס מעל X ימים (0 = כל הספקים הפתוחים):", min_value=0, max_value=90, value=0)
    portal_url = c2.text_input("כתובת הפורטל לשליחה:", value="https://sapakim-portal.streamlit.app")

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

    selected_suppliers = st.multiselect("בחר ספקים לשיגור הודעת וואטסאפ מרוכזת:", list(sup_groups.keys()), default=list(sup_groups.keys())[:5])

    for sname in selected_suppliers:
        s_orders = sup_groups[sname]
        contact = s_orders[0].get("contact_person", "")
        phone_wa = normalize_phone_whatsapp(s_orders[0].get("supplier_phone", ""))
        msg = build_whatsapp_message(sname, contact, s_orders, portal_url)
        encoded = urllib.parse.quote(msg)
        wa_url = f"https://web.whatsapp.com/send?phone={phone_wa}&text={encoded}" if phone_wa else ""

        with st.expander(f"📨 {sname} (איש קשר: {contact or 'לא הוגדר'} | טלפון: {s_orders[0].get('supplier_phone') or 'חסר'}) - {len(s_orders)} שורות"):
            st.code(msg, language="text")
            if wa_url:
                st.link_button(f"🚀 פתח צ'אט וואטסאפ מול {sname}", wa_url)
            else:
                st.warning("חסר מספר טלפון תקין לספק זה.")


def _render_tab_excel_upload(db: DBWrapper, user: dict):
    """טעינת אקסל ממודרת לפי מדור עם תצוגה מקדימה לפני כתיבה למסד (תיקונים #8 ו-#9)."""
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
        order_num = str(r_dict.get("מספר הזמנה", "") or r_dict.get("הזמנה", "")).strip().split(".")[0]
        line_num = str(r_dict.get("שורה", "") or r_dict.get("מספר שורה", "10")).strip().split(".")[0]
        if not order_num or order_num == "nan":
            continue

        mgr = infer_order_manager(r_dict)
        # אכיפת מידור טעינת אקסל: מדור יכול לטעון אך ורק שורות של המדור שלו (תיקון #8)
        if role != "admin" and scope != "ALL" and mgr != scope:
            skipped_by_scope += 1
            continue

        sup_note_raw = str(r_dict.get("תגובת ספק", "") or "").strip()
        if any(p in sup_note_raw for p in GENERIC_PHRASES_TO_CLEAN) or sup_note_raw == "nan":
            sup_note_raw = ""

        preview_rows.append({
            "order_manager": mgr,
            "order_number": safe_text(order_num),
            "line_number": safe_text(line_num),
            "part_number": safe_text(r_dict.get("מק\"ט", "") or r_dict.get("מקט", "")),
            "item_description": safe_text(r_dict.get("תיאור מוצר", "") or r_dict.get("שם פריט", "") or r_dict.get("פרט", "")),
            "quantity": safe_text(r_dict.get("כמות", "1")),
            "supplier_name": safe_text(r_dict.get("חברה", "") or r_dict.get("שם ספק", "") or r_dict.get("ספק", "")),
            "contact_person": safe_text(r_dict.get("איש קשר", "")),
            "supplier_phone": normalize_phone_display(r_dict.get("מספר טלפון", "") or r_dict.get("טלפון", "")),
            "due_date": safe_text(str(r_dict.get("תאריך אספקה", "") or r_dict.get("תאריך יעד", ""))[:10]),
            "internal_status": safe_text(r_dict.get("סטטוס אחרון", "")),
            "supplier_note_excel": safe_text(sup_note_raw)
        })

    st.info(f"🔎 תצוגה מקדימה לפני כתיבה למסד: נמצאו **{len(preview_rows)}** שורות מורשות לטעינה (דולגו {skipped_by_scope} שורות של מדורים אחרים).")
    if preview_rows:
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
        if st.button("⚡ אשר וטען שורות אלו למסד הנתונים (ללא דריסת תגובות קיימות)", type="primary"):
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
                    # מיזוג חכם (VLOOKUP) ללא דריסת תשובות ספק או מענה מדור קיימים
                    db.execute("""
                        UPDATE orders
                        SET order_manager = ?, part_number = ?, item_description = ?, quantity = ?,
                            supplier_name = ?,
                            contact_person = CASE WHEN ? != '' THEN ? ELSE contact_person END,
                            supplier_phone = CASE WHEN ? != '' THEN ? ELSE supplier_phone END,
                            due_date = CASE WHEN ? != '' THEN ? ELSE due_date END,
                            internal_status = CASE WHEN ? != '' THEN ? ELSE internal_status END,
                            last_updated = ?
                        WHERE id = ?
                    """, (
                        pr["order_manager"], pr["part_number"], pr["item_description"], pr["quantity"],
                        pr["supplier_name"], pr["contact_person"], pr["contact_person"],
                        pr["supplier_phone"], pr["supplier_phone"], pr["due_date"], pr["due_date"],
                        pr["internal_status"], pr["internal_status"], now_s, existing["id"]
                    ))
            log_audit(db, user["entity_name"], role, "EXCEL_SYNC", f"נטענו/סונכרנו {len(preview_rows)} שורות מאקסל")
            db.commit()
            st.success("הסנכרון הושלם בהצלחה!")
            st.rerun()


def _render_tab_commander_dashboard(db: DBWrapper, all_orders: list[dict]):
    """דשבורד מפקד ודוח שבועי לפי מדור ולפי ספק."""
    st.markdown("#### 🎖️ דשבורד מפקד ודוח ביצועים שבועי")
    if not all_orders:
        st.info("אין נתונים להצגה.")
        return

    df = pd.DataFrame(all_orders)
    df["בפיגור"] = df["פיגור בימים"].apply(lambda x: 1 if "🔴" in str(x) else 0)
    df["עודכן_השבוע"] = df["סטטוס שבועי"].apply(lambda x: 1 if "🟢" in str(x) else 0)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**📊 סיכום לפי מדור (מנהל ההזמנה):**")
        mador_summary = df.groupby("order_manager", as_index=False).agg(
            סהכ_שורות=("id", "count"),
            שורות_בפיגור=("בפיגור", "sum"),
            עודכנו_השבוע=("עודכן_השבוע", "sum"),
            דורשות_מענה=("needs_attention", "sum")
        )
        st.dataframe(mador_summary, use_container_width=True, hide_index=True)

    with col2:
        st.markdown("**🏭 10 הספקים עם כמות השורות הפתוחות הגבוהה ביותר:**")
        sup_summary = df.groupby("supplier_name", as_index=False).agg(
            סהכ_שורות=("id", "count"),
            שורות_בפיגור=("בפיגור", "sum"),
            עודכנו_השבוע=("עודכן_השבוע", "sum")
        ).sort_values(by="שורות_בפיגור", ascending=False).head(10)
        st.dataframe(sup_summary, use_container_width=True, hide_index=True)


def _render_tab_security_and_backup(db: DBWrapper, user: dict, all_orders: list[dict]):
    """ניהול סיסמאות ספקים ע"י מנהל בלבד, מחיקה רכה (Soft Delete) וגיבוי מערכת נקי מסיסמאות."""
    if user["role"] != "admin":
        st.warning("לשונית זו מיועדת למנהל המערכת (Admin) בלבד.")
        return

    st.markdown("#### 🔑 הנפקת סיסמה זמנית / PIN לספק ונעילת חשבונות (Admin Only)")
    suppliers = db.fetchall("SELECT id, entity_name, contact_person, phone, is_locked, failed_attempts, last_login FROM users WHERE role = 'supplier' ORDER BY entity_name")
    if suppliers:
        st.dataframe(pd.DataFrame(suppliers), use_container_width=True, hide_index=True)
        c1, c2 = st.columns(2)
        target_sup = c1.selectbox("בחר ספק לאיפוס סיסמה / הנפקת קישור ו-PIN חדשים:", [s["entity_name"] for s in suppliers])
        if c1.button("🔄 הנפק סיסמה זמנית + PIN + קישור 128-ביט חדשים", type="primary"):
            creds = issue_new_supplier_credentials(db, target_sup, user["entity_name"])
            st.success(f"אמצעי זיהוי חדשים הונפקו עבור **{target_sup}** (מוצגים כעת בלבד ואינם נשמרים בטקסט גלוי):")
            st.code(
                f"שם ספק לכניסה: {creds['supplier_name']}\n"
                f"סיסמה זמנית חד-פעמית: {creds['temp_password']}\n"
                f"קוד PIN נפרד (אל תשלח יחד עם הקישור!): {creds['pin']}\n"
                f"קישור 128-ביט (בתוקף עד {creds['expires_at']}):\n"
                f"https://sapakim-portal.streamlit.app/?token={creds['raw_token']}",
                language="text"
            )

        lock_sup = c2.selectbox("בחר ספק לנעילה / שחרור נעילה (Kill Switch):", [s["entity_name"] for s in suppliers], key="lock_sel")
        if c2.button("🔒 החלף מצב נעילה לספק"):
            cur = db.fetchone("SELECT is_locked FROM users WHERE role = 'supplier' AND entity_name = ?", (lock_sup,))
            new_lock = 0 if cur and cur["is_locked"] else 1
            db.execute("UPDATE users SET is_locked = ?, failed_attempts = 0, locked_until = '' WHERE role = 'supplier' AND entity_name = ?", (new_lock, lock_sup))
            log_audit(db, user["entity_name"], "admin", "TOGGLE_LOCK", f"מצב נעילה לספק {lock_sup} שונה ל-{new_lock}")
            db.commit()
            st.success("מצב הנעילה עודכן!")
            st.rerun()

    st.divider()
    st.markdown("#### 🗑️ מחיקה רכה (Soft Delete) ושחזור הזמנות (מותנה בקבלת מענה ספק - תיקון #9)")
    eligible_for_delete = [
        o for o in all_orders
        if (o.get("supplier_status") and o["supplier_status"] != "טרם עודכן") or o.get("supplier_note")
    ]
    del_map = {f"הזמנה {o['order_number']}/{o['line_number']} ({o['supplier_name']} - {o['supplier_status']})": o["id"] for o in eligible_for_delete}
    sel_del = st.multiselect("בחר שורות שקיבלו מענה ספק להעברה לארכיון (מחיקה רכה):", list(del_map.keys()))
    if sel_del and st.button("🗑️ העבר שורות נבחרות לארכיון (מחיקה רכה)"):
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
        if sel_rest and st.button("♻️ שחזר שורות נבחרות לפורטל"):
            for lbl in sel_rest:
                db.execute("UPDATE orders SET is_deleted = 0, deleted_at = '', deleted_by = '' WHERE id = ?", (rest_map[lbl],))
                log_audit(db, user["entity_name"], "admin", "RESTORE_ROW", f"שורה שוחזרה מהארכיון: {lbl}")
            db.commit()
            st.success("השורות שוחזרו בהצלחה!")
            st.rerun()

    st.divider()
    st.markdown("#### 💾 גיבוי מערכת מלא ל-Excel (ללא חשיפת סיסמאות או אסימונים - תיקון #1 ו-#4)")
    if st.button("📦 הפק קובץ גיבוי מערכת מלא (Orders + Users Metadata + Audit Log)"):
        out = BytesIO()
        orders_df = pd.DataFrame(db.fetchall("SELECT * FROM orders")).applymap(sanitize_excel_value)
        users_df = pd.DataFrame(db.fetchall(
            "SELECT id, username, role, entity_name, order_manager_scope, contact_person, phone, is_locked, last_login FROM users"
        )).applymap(sanitize_excel_value)
        logs_df = pd.DataFrame(db.fetchall("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 2000")).applymap(sanitize_excel_value)

        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            orders_df.to_excel(writer, index=False, sheet_name="Orders")
            users_df.to_excel(writer, index=False, sheet_name="Users_Safe")
            logs_df.to_excel(writer, index=False, sheet_name="Audit_Logs")

        st.download_button(
            "⬇️ הורד גיבוי מערכת מלא (.xlsx)",
            data=out.getvalue(),
            file_name=f"SAPakim_Full_Backup_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# ==============================================================================
# פרק 7: נקודת כניסה ראשית וניהול פג תוקף חיבור (Main Entry & Session Timeout)
# ==============================================================================

def main():
    inject_custom_css()
    init_db()
    db = DBWrapper()

    if "user" not in st.session_state:
        st.session_state.user = None
    if "last_activity" not in st.session_state:
        st.session_state.last_activity = datetime.now()

    # אכיפת ניתוק אוטומטי לאחר חוסר פעילות (תיקון #5 ו-#14)
    if st.session_state.user:
        elapsed = (datetime.now() - st.session_state.last_activity).total_seconds() / 60.0
        if elapsed > SESSION_TIMEOUT_MINUTES:
            st.session_state.user = None
            st.query_params.clear()
            st.warning("נותקת אוטומטית מהמערכת עקב חוסר פעילות. אנא התחבר מחדש.")
            st.stop()
        else:
            st.session_state.last_activity = datetime.now()

    if not st.session_state.user:
        render_login_view(db)
        st.markdown("<div class='watermark'>Powered by BEN HUR</div>", unsafe_allow_html=True)
        db.close()
        return

    user = st.session_state.user
    contact_suffix = f" (איש קשר: {user['contact_person']})" if user["role"] == "supplier" and user.get("contact_person") else ""

    col_h, col_b = st.columns([5, 1])
    with col_h:
        st.markdown(f"""
            <div class="header-box">
                <div class="header-title">🛡️ SAPakim | שלום, {safe_text(user['entity_name'])}{safe_text(contact_suffix)}</div>
                <div class="header-sub">מחובר בהרשאת: {safe_text(user['role'])}</div>
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
    db.close()


if __name__ == "__main__":
    main()
