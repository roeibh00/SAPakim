"""SAPakim - פורטל הזמנות ספקים (Streamlit + SQLite)

מבנה הקובץ:
  1. קונפיגורציה וקבועים
  2. עיצוב (CSS)
  3. מסד נתונים
  4. פונקציות עזר
  5. מסכים: כניסה / מנהל ומדורים / ספק
  6. main()
"""
import json
import secrets
import sqlite3
import urllib.parse
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="SAPakim - פורטל הזמנות",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==================== 1. קונפיגורציה וקבועים ====================
DB_PATH = "sapakim_cloud.db"
APP_URL = "https://sapakim-kukmcxaux8yf9tfjrygif9.streamlit.app"
MAX_LOGIN_ATTEMPTS = 5
DONE_STATUS = "סופק"

STATUS_OPTIONS = [
    "טרם עודכן", "תקין - בייצור", "בטיפול - שבוע הבא", "בטיפול מיידי",
    "מוכן לאספקה", 'ממתין לבק"מ', "חסר שרטוט / דרוש מענה מדור",
    "מעוכב - חוסר חומר גלם", "עיכוב / בפיגור", DONE_STATUS,
]
# סטטוס שמכיל אחת מהמילים האלה (או הערת ספק) מסמן "דורש תשומת לב מהמדור"
ALERT_WORDS = ("שרטוט", "עיכוב", "מעוכב")

# מפתחות צוות. מומלץ להעביר ל-st.secrets (ראה הערה בסוף ההודעה) ולא להשאיר בקוד ציבורי.
STAFF_KEYS = [
    ("BH-ADMIN-9920", "admin", "רועי - מנהל מערכת ראשי"),
    ("NAMER-7741", "mador", 'מדור נמ"ר'),
    ("MERKAVA-5582", "mador", "מדור מרכבה"),
    ("MANHAR-3319", "mador", 'מנה"ר רכש'),
]

# שמות אפשריים לכל עמודה בקובץ האקסל (הראשון שנמצא - נבחר)
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

# עמודות שלא נדרסות בטעינת אקסל אם הערך החדש ריק
KEEP_IF_EMPTY = [
    "part_number", "item_description", "contact_person", "supplier_phone", "due_date",
    "internal_status", "supplier_status", "expected_date", "supplier_note", "mador_response",
]

# ייצוא לאקסל: כותרת בעברית -> עמודה בבסיס הנתונים
EXPORT_MAP = {
    "מספר הזמנה": "order_number", "שורה": "line_number", "שם פריט": "item_description",
    'מק"ט': "part_number", "תאריך אספקה": "due_date", "חברה": "supplier_name",
    "סטטוס אחרון": "internal_status", "איש קשר": "contact_person",
    "מספר טלפון": "supplier_phone", "צפי ספק": "expected_date",
    "סטטוס עדכני": "supplier_status", "תגובת ספק": "supplier_note",
    "מענה מדור": "mador_response", "תאריך_עדכון_אחרון": "last_updated",
}

# ==================== 2. עיצוב ====================
CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700&display=swap');

    :root, html, body, .stApp {
        color-scheme: light !important;
        font-family: 'Rubik', sans-serif !important;
        direction: rtl; text-align: right;
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
        max-width: 1240px !important; margin: 0 auto !important;
        padding-top: 4.2rem !important; padding-bottom: 3rem !important;
    }
    p, span, label, div, h1, h2, h3, h4, h5, h6, li, th, td { color: #0f172a; }

    /* ---------- כותרת ---------- */
    .header-box {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 65%, #78350f 100%);
        padding: 1.3rem 1.8rem; border-radius: 16px; border-bottom: 4px solid #f59e0b;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12); margin-bottom: 1.4rem; text-align: center;
    }
    .header-title { font-size: 1.45rem !important; font-weight: 700 !important; color: #fff !important; margin: 0 !important; }
    .header-sub { font-size: 0.88rem !important; color: #fcd34d !important; margin-top: 0.3rem !important; font-weight: 500; }

    /* ---------- מדדים ---------- */
    div[data-testid="metric-container"] {
        background: #fff !important; padding: 0.9rem 1.1rem !important; border-radius: 14px !important;
        border: 1px solid #e2e8f0 !important; border-right: 5px solid #d97706 !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04) !important;
    }
    div[data-testid="stMetricValue"] { font-size: 1.5rem !important; font-weight: 700 !important; direction: ltr; text-align: right; }
    div[data-testid="stMetricLabel"] p { font-size: 0.85rem !important; font-weight: 600 !important; color: #475569 !important; }

    /* ---------- שדות קלט ---------- */
    input, textarea, select, [data-baseweb="select"] > div, [data-baseweb="input"] input {
        background-color: #fff !important; color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important; border-color: #cbd5e1 !important; font-weight: 500 !important;
    }
    [data-baseweb="select"] svg { fill: #0f172a !important; }
    label[data-testid="stWidgetLabel"] p, .stRadio label p, .stCheckbox label p {
        color: #0f172a !important; font-weight: 600 !important; font-size: 0.9rem !important;
    }

    /* ---------- תיקון: רשימת הבחירה הנפתחת בנייד (רקע לבן + טקסט כהה בכל הרכיבים) ---------- */
    [data-baseweb="popover"], [data-baseweb="popover"] *,
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
    }
    [role="option"], [role="option"] * { min-height: 44px; }
    [role="option"]:hover, [role="option"]:hover *,
    [role="option"][aria-selected="true"], [role="option"][aria-selected="true"] * {
        background-color: #fef3c7 !important;
    }

    /* ---------- כרטיסי הזמנה ---------- */
    .order-card-header {
        background: linear-gradient(90deg, #fef3c7 0%, #fffbeb 100%); padding: 0.75rem 1rem;
        border-radius: 10px; border-right: 5px solid #d97706; margin-bottom: 0.7rem; font-size: 0.92rem;
    }
    .order-card-header, .order-card-header strong, .order-card-header span { color: #78350f !important; }
    .locked-badge {
        background: #e2e8f0; color: #1e293b !important; padding: 0.3rem 0.65rem; border-radius: 8px;
        font-size: 0.82rem; font-weight: 600; display: inline-block; margin-left: 0.4rem; margin-bottom: 0.4rem;
    }

    /* ---------- כפתורים (כולל כפתור שליחה בתוך form - היה אדום) ---------- */
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

    .watermark { text-align: center; font-size: 0.78rem; color: #64748b !important; margin-top: 2.2rem; font-weight: 600; letter-spacing: 0.5px; }

    @media (max-width: 768px) {
        .block-container { padding: 3.8rem 0.6rem 3rem 0.6rem !important; }
        .header-box { padding: 0.95rem 1.1rem; border-radius: 12px; }
        .header-title { font-size: 1.18rem !important; }
        input, select, textarea { font-size: 16px !important; }
    }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ==================== 3. מסד נתונים ====================
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


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
    conn.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    # מיגרציות לבסיסי נתונים ישנים (נכשל בשקט אם העמודה כבר קיימת)
    for sql in [
        "ALTER TABLE orders ADD COLUMN contact_person TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN internal_status TEXT DEFAULT ''",
        "ALTER TABLE access_keys ADD COLUMN contact_person TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass

    conn.execute("DELETE FROM access_keys WHERE access_key IN ('ADMIN-ROEY', 'MAD-NAMER', 'MAD-MANHAR')")
    for key, role, name in STAFF_KEYS:
        conn.execute("INSERT OR REPLACE INTO access_keys (access_key, role, entity_name) VALUES (?, ?, ?)", (key, role, name))
    conn.commit()
    conn.close()


def get_or_create_key(conn, entity_name, contact_person="", phone=""):
    """מחזיר מפתח גישה לספק (יוצר אם אין), ומעדכן איש קשר וטלפון אם התקבלו חדשים."""
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
    """שומר עדכוני ספק. updates = [(order_id, status, expected_date, note), ...]"""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    for order_id, status, expected, note in updates:
        conn.execute(
            """UPDATE orders
               SET supplier_status=?, expected_date=?, supplier_note=?, needs_attention=?, last_updated=?
               WHERE id=? AND supplier_name=?""",
            (status, expected, note, int(needs_attention(status, note)), now, order_id, supplier_name),
        )
    conn.commit()


# ==================== 4. פונקציות עזר ====================
def clean_str(val):
    """ניקוי בטוח של ערך מאקסל (NaN / None / רווחים)."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "null") else s


def find_col(columns, candidates):
    """מאתר עמודה באקסל גם אם שמה שונה מעט (רווחים / תוספות)."""
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
    """מחזיר מספר בפורמט בינלאומי (972...) רק לנייד ישראלי תקין, אחרת None."""
    disp = clean_display_phone(raw)
    return "972" + disp[1:] if disp.startswith("05") and len(disp) == 10 else None


def needs_attention(status, note):
    return bool(str(note).strip()) or any(w in str(status) for w in ALERT_WORDS)


def not_done(series):
    return ~series.astype(str).str.strip().eq(DONE_STATUS)


# ==================== 5א. מסך כניסה ====================
def render_login():
    _, center, _ = st.columns([0.8, 2, 0.8])
    with center:
        st.markdown("""
        <div class="header-box">
            <div class="header-title">🛡️ פורטל SAPakim</div>
            <div class="header-sub">מערכת ארגונית מאובטחת לבקרת הזמנות ותקשורת ספקים</div>
        </div>""", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("##### הזדהות וכניסה למערכת")
            st.caption("אנא הזן את מפתח הגישה האישי (Access Key) שלך.")

            if st.session_state.failed_attempts >= MAX_LOGIN_ATTEMPTS:
                st.error("הגעת למספר הניסיונות המקסימלי. אנא רענן את הדף או פנה למנהל המערכת.")
                st.stop()

            key_input = st.text_input("מפתח גישה סודי:", type="password", placeholder="••••••••••••").strip().upper()
            if st.button("התחבר למערכת 🔒", type="primary", use_container_width=True):
                if not login_with_key(key_input):
                    st.session_state.failed_attempts += 1
                    st.error(f"מפתח גישה שגוי או שאינו מורשה (ניסיון {st.session_state.failed_attempts}/{MAX_LOGIN_ATTEMPTS}).")
                else:
                    st.rerun()
        st.markdown('<div class="watermark">Powered by BEN HUR</div>', unsafe_allow_html=True)


def login_with_key(key):
    conn = get_db()
    row = conn.execute("SELECT * FROM access_keys WHERE UPPER(access_key)=?", (key,)).fetchone()
    conn.close()
    if row:
        st.session_state.user = dict(row)
        st.session_state.failed_attempts = 0
        return True
    return False


def render_top_bar(user):
    c1, c2 = st.columns([4.5, 1])
    with c1:
        st.markdown(f"""
        <div class="header-box" style="text-align: right;">
            <div class="header-title">🛡️ SAPakim | שלום, {user['entity_name']}</div>
            <div class="header-sub">מחובר בהרשאת: {user['role']}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        if st.button("התנתק 🚪", use_container_width=True):
            st.session_state.user = None
            st.session_state.submitted = False
            st.query_params.clear()
            st.rerun()


# ==================== 5ב. ממשק מנהל ומדורים ====================
def render_staff(conn):
    tab_orders, tab_wa, tab_upload = st.tabs(["📊 הזמנות ומענה", "💬 שיגור וואטסאפ אוטומטי", "📥 טעינת אקסל"])
    with tab_orders:
        render_orders_tab(conn)
    with tab_wa:
        render_whatsapp_tab(conn)
    with tab_upload:
        render_upload_tab(conn)


def render_orders_tab(conn):
    df = pd.read_sql_query("SELECT * FROM orders ORDER BY needs_attention DESC, supplier_name, order_number", conn)
    if df.empty:
        st.info("אין עדיין הזמנות במערכת. עבור ללשונית 'טעינת אקסל' כדי להעלות קובץ.")
        return

    k1, k2 = st.columns(2)
    k3, k4 = st.columns(2)
    k1.metric('סה"כ שורות הזמנה', len(df))
    k2.metric("שורות עם שם איש קשר", int((df["contact_person"].astype(str).str.strip() != "").sum()))
    k3.metric("בעיכוב / בטיפול / טרם סופק", int(not_done(df["supplier_status"]).sum()))
    k4.metric("⚠️ ממתינות למענה מדור", int((df["needs_attention"] == 1).sum()))

    f1, f2 = st.columns([1.5, 1])
    search = f1.text_input('🔍 חיפוש מהיר (לפי ספק, איש קשר, טלפון, הזמנה או מק"ט):', "")
    mode = f2.radio("תצוגה:", ["💻 טבלה מלאה", "📱 כרטיסיות (לנייד)"], horizontal=True)
    only_open = st.checkbox("הצג רק שורות פתוחות / בעיכוב (הסתר שורות שסופקו)", value=False)

    view = df.copy()
    if search:
        mask = view.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
        view = view[mask]
    if only_open:
        view = view[not_done(view["supplier_status"])]

    if mode.startswith("📱"):
        render_staff_cards(conn, view)
    else:
        render_staff_table(conn, view)

    st.download_button(
        "📥 הורד דוח אקסל מלא (כולל אנשי קשר וטלפונים)",
        data=export_excel(df), file_name="suppliers_updated.xlsx", use_container_width=True,
    )


def render_staff_cards(conn, view):
    st.caption("🔒 נתוני הספק נעולים. לחץ על הזמנה לצפייה באיש הקשר, בטלפון ולהזנת מענה מדור.")
    for _, r in view.iterrows():
        icon = "⚠️" if r["needs_attention"] == 1 else "📦"
        with st.expander(f"{icon} {r['supplier_name']} | 👤 {r['contact_person'] or 'ללא איש קשר'} | הזמנה {r['order_number']}"):
            st.markdown(f"""
            <div class="order-card-header">
                <strong>פריט:</strong> {r['item_description']} | <strong>מק"ט:</strong> {r['part_number']} | <strong>שורה:</strong> {r['line_number']}<br>
                <strong>👤 איש קשר:</strong> {r['contact_person'] or '-'} | <strong>📞 טלפון:</strong> {r['supplier_phone'] or 'חסר'}
            </div>""", unsafe_allow_html=True)
            st.markdown(f"🔒 **סטטוס עדכני:** `{r['supplier_status']}` | **צפי ספק:** `{r['expected_date'] or 'לא הוזן'}`")
            st.markdown(f"🔒 **תגובת / הערת ספק:** {r['supplier_note'] or 'אין הערות'}")

            reply = st.text_area("✍️ מענה מדור לספק:", value=r["mador_response"], key=f"mresp_{r['id']}")
            if st.button("💾 שמור מענה לשורה זו", key=f"msave_{r['id']}", type="primary", use_container_width=True):
                now = datetime.now().strftime("%d/%m/%Y %H:%M")
                conn.execute("UPDATE orders SET mador_response=?, needs_attention=0, last_updated=? WHERE id=?", (reply, now, r["id"]))
                conn.commit()
                st.success("מענה המדור נשמר!")
                st.rerun()


def render_staff_table(conn, view):
    st.caption('🔒 **אבטחת מידע:** עמודות דיווח הספק נעולות. המדור יכול לעדכן איש קשר, טלפון, מק"ט ומענה מדור.')
    cols = ["id", "supplier_name", "contact_person", "supplier_phone", "order_number", "line_number",
            "part_number", "item_description", "due_date", "supplier_status", "expected_date",
            "supplier_note", "mador_response"]
    T = st.column_config.TextColumn
    edited = st.data_editor(
        view[cols],
        column_config={
            "id": None,
            "supplier_name": T("חברה", disabled=True),
            "contact_person": T("👤 איש קשר"),
            "supplier_phone": T("📞 מספר טלפון"),
            "order_number": T("מספר הזמנה", disabled=True),
            "line_number": T("שורה", disabled=True),
            "part_number": T('מק"ט'),
            "item_description": T("שם פריט"),
            "due_date": T("תאריך אספקה"),
            "supplier_status": T("🔒 סטטוס עדכני", disabled=True),
            "expected_date": T("🔒 צפי ספק", disabled=True),
            "supplier_note": T("🔒 תגובת ספק", disabled=True),
            "mador_response": T("✍️ מענה מדור לספק (ערוך כאן)"),
        },
        use_container_width=True, hide_index=True,
    )

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


def export_excel(df):
    export_df = pd.DataFrame({heb: df[col] for heb, col in EXPORT_MAP.items()})
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
        SUM(CASE WHEN TRIM(COALESCE(o.supplier_status, '')) != 'סופק' THEN 1 ELSE 0 END) AS open_or_delayed_orders
    FROM access_keys u
    LEFT JOIN orders o ON o.supplier_name = u.entity_name
    WHERE u.role = 'supplier'
    GROUP BY u.entity_name
    ORDER BY open_or_delayed_orders DESC, u.entity_name
'''


def build_whatsapp_message(conn, sup, sender):
    """sup = שורה מטבלת הספקים. מחזיר טקסט הודעה אישי עם קישור כניסה."""
    name = sup["supplier_name"]
    rows = conn.execute(
        "SELECT order_number, line_number, item_description FROM orders "
        "WHERE supplier_name=? AND TRIM(COALESCE(supplier_status, '')) != ?", (name, DONE_STATUS)).fetchall()
    if not rows:
        rows = conn.execute(
            "SELECT order_number, line_number, item_description FROM orders WHERE supplier_name=?", (name,)).fetchall()
    lines = "\n".join(f"• הזמנה {o['order_number']} שורה {o['line_number']} - {o['item_description']}" for o in rows[:10])
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
    """סקריפט Selenium שרץ במחשב המקומי ושולח את ההודעות אוטומטית. targets = [(supplier, contact, url)]"""
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
    """items = [(supplier, contact, display_phone, wa_me_url)] -> כפתור 'שגר הכול' + כפתורים לכל ספק."""
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
    df_sups = pd.read_sql_query(SUPPLIERS_SQL, conn)
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

        pool["label"] = pool.apply(
            lambda r: f"{r['supplier_name']} | 👤 {r['contact_person'] or 'ללא איש קשר'} | 📞 {r['phone'] or 'ללא טלפון'}", axis=1)

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


# ---------- טעינת אקסל ----------
def render_upload_tab(conn):
    st.markdown("##### 📥 טעינת קובץ אקסל (`suppliers.xlsx`) - סנכרון מלא של אנשי קשר וטלפונים")
    st.info("💡 **חשוב:** העלה כאן את קובץ ה-`suppliers.xlsx` ולחץ על הכפתור הכתום – המערכת תציג כמה אנשי קשר וטלפונים נקלטו.")
    uploaded = st.file_uploader("בחר קובץ Excel או CSV", type=["xlsx", "xls", "csv"])
    if uploaded and st.button("טען וסנכרן הזמנות, אנשי קשר וטלפונים למערכת ⚡", type="primary", use_container_width=True):
        df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
        df.columns = [str(c).strip() for c in df.columns]
        result = import_orders(conn, df)
        st.success(
            f"✅ הסנכרון הושלם! נקלטו {result['rows']} שורות הזמנה, "
            f"{result['contacts']} שורות עם איש קשר, ו-{result['phones']} שורות עם טלפון!"
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

        # השלמה מהזיכרון אם חסר בשורה הספציפית
        if not phone or not contact:
            mem = conn.execute("SELECT phone, contact_person FROM access_keys WHERE role='supplier' AND entity_name=?", (supplier,)).fetchone()
            if mem:
                phone = phone or mem["phone"]
                contact = contact or mem["contact_person"]
        contacts += bool(contact)
        phones += bool(phone)

        get_or_create_key(conn, supplier, contact, phone)

        data = {
            "order_number": order_num,
            "line_number": get(r, "line").split(".")[0] or "10",
            "part_number": get(r, "part").split(".")[0],
            "item_description": get(r, "desc"),
            "quantity": get(r, "qty").split(".")[0] or "1",
            "supplier_name": supplier,
            "contact_person": contact,
            "supplier_phone": phone,
            "due_date": get(r, "due").split(" ")[0],
            "internal_status": internal,
            "supplier_status": get(r, "status"),  # ריק = לא נדרס אם כבר יש תשובת ספק
            "expected_date": get(r, "expected").split(" ")[0],
            "supplier_note": get(r, "note"),
            "mador_response": get(r, "mador"),
            "last_updated": get(r, "updated"),
        }
        names = ", ".join(data)
        placeholders = ", ".join(f":{k}" for k in data)
        keep = ", ".join(f"{c}=CASE WHEN excluded.{c}!='' THEN excluded.{c} ELSE orders.{c} END" for c in KEEP_IF_EMPTY)
        conn.execute(
            f"""INSERT INTO orders ({names}) VALUES ({placeholders})
                ON CONFLICT(order_number, line_number) DO UPDATE SET supplier_name=excluded.supplier_name, {keep}""",
            data,
        )
        rows += 1

    # שורות חדשות בלי סטטוס ספק: ברירת מחדל = סטטוס פנימי, ואם אין - "טרם עודכן"
    conn.execute("""UPDATE orders SET supplier_status = COALESCE(NULLIF(internal_status, ''), 'טרם עודכן')
                    WHERE supplier_status = '' OR supplier_status IS NULL""")

    # השלמה רוחבית: איש קשר / טלפון שנמצאו אצל ספק יועתקו לכל שורותיו
    for order_col, key_col in (("contact_person", "contact_person"), ("supplier_phone", "phone")):
        conn.execute(f"""
            UPDATE orders SET {order_col} = (
                SELECT {key_col} FROM access_keys
                WHERE access_keys.entity_name = orders.supplier_name AND access_keys.role='supplier')
            WHERE {order_col} = '' OR {order_col} IS NULL""")
    conn.commit()
    return {"rows": rows, "contacts": contacts, "phones": phones}


# ==================== 5ג. מסך ספק ====================
def render_supplier(conn, user):
    st.markdown(f"##### 📦 ההזמנות הפתוחות של: {user['entity_name']}")
    df = pd.read_sql_query(
        "SELECT * FROM orders WHERE supplier_name=? ORDER BY order_number, CAST(line_number AS INTEGER)",
        conn, params=(user["entity_name"],))

    if df.empty:
        st.warning("לא נמצאו הזמנות פתוחות המשויכות אליכם כרגע.")
        return

    # אחרי שליחה - מסך סיום עם אפשרות עריכה
    if st.session_state.submitted:
        render_done_screen(df)
        return

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
    """מחזיר רשימת עדכונים אם נלחץ 'שמור', אחרת None."""
    st.caption("🔒 פרטי ההזמנה ותשובות המדור נעולים. מלאו את הסטטוס והצפי לכל פריט ולחצו על כפתור השמירה בתחתית הדף.")
    updates = []
    with st.form("mobile_supplier_form"):
        for _, row in df.iterrows():
            with st.container(border=True):
                st.markdown(f"""
                <div class="order-card-header">
                    <strong>🔒 הזמנה: {row['order_number']} | שורה: {row['line_number']}</strong><br>
                    <span>{row['item_description'] or 'ללא תיאור'}</span>
                </div>
                <div>
                    <span class="locked-badge">🔒 מק"ט: {row['part_number'] or '-'}</span>
                    <span class="locked-badge">🔒 יעד: {row['due_date'] or '-'}</span>
                    <span class="locked-badge">👤 איש קשר: {row['contact_person'] or '-'}</span>
                </div>""", unsafe_allow_html=True)

                if row["mador_response"]:
                    st.info(f"💬 **מענה מדור חט\"ל (נעול):** {row['mador_response']}")

                current = row["supplier_status"] if row["supplier_status"] in STATUS_OPTIONS else STATUS_OPTIONS[0]
                c1, c2 = st.columns(2)
                status = c1.selectbox("✍️ סטטוס עדכני:", STATUS_OPTIONS, index=STATUS_OPTIONS.index(current), key=f"st_{row['id']}")
                expected = c2.text_input("✍️ צפי ספק (תאריך):", value=row["expected_date"], placeholder="למשל: 15/09/2026", key=f"dt_{row['id']}")
                note = st.text_input("✍️ תגובת ספק / בקשה למדור:", value=row["supplier_note"], placeholder="פרט סיבת עיכוב או בקשה...", key=f"nt_{row['id']}")
                updates.append((row["id"], status, expected, note))

        sent = st.form_submit_button('✅ שמור ושלח את כל העדכונים לחט"ל', type="primary", use_container_width=True)
    return updates if sent else None


def render_supplier_table(df):
    st.caption("🔒 פרטי ההזמנה ותשובות המדור נעולים לשינוי.")
    df = df.copy()
    df["supplier_status"] = df["supplier_status"].apply(lambda x: x if x in STATUS_OPTIONS else STATUS_OPTIONS[0])
    T = st.column_config.TextColumn
    edited = st.data_editor(
        df[["id", "order_number", "line_number", "part_number", "item_description", "due_date",
            "supplier_status", "expected_date", "supplier_note", "mador_response"]],
        column_config={
            "id": None,
            "order_number": T("🔒 מס' הזמנה", disabled=True),
            "line_number": T("🔒 שורה", disabled=True),
            "part_number": T('🔒 מק"ט', disabled=True),
            "item_description": T("🔒 שם פריט", disabled=True),
            "due_date": T("🔒 תאריך אספקה", disabled=True),
            "supplier_status": st.column_config.SelectboxColumn("✍️ סטטוס עדכני", options=STATUS_OPTIONS, required=True),
            "expected_date": T("✍️ צפי ספק"),
            "supplier_note": T("✍️ תגובת ספק"),
            "mador_response": T('🔒 מענה מדור חט"ל', disabled=True),
        },
        use_container_width=True, hide_index=True,
    )
    if st.button('✅ שמור ושלח עדכונים לחט"ל', type="primary", use_container_width=True):
        return [(r["id"], r["supplier_status"], r["expected_date"], r["supplier_note"]) for _, r in edited.iterrows()]
    return None


def render_done_screen(df):
    """מסך סיום: אישור, סיכום מה נשלח, וכפתור חזרה לעריכה."""
    st.success('✅ העדכונים נשלחו בהצלחה לחט"ל. תודה רבה!')
    last = df["last_updated"].replace("", pd.NA).dropna()
    if not last.empty:
        st.caption(f"עודכן לאחרונה: {last.iloc[-1]}")

    st.markdown("##### סיכום העדכונים ששלחתם")
    summary = df[["order_number", "line_number", "item_description", "supplier_status", "expected_date", "supplier_note", "mador_response"]]
    st.dataframe(
        summary.rename(columns={
            "order_number": "הזמנה", "line_number": "שורה", "item_description": "פריט",
            "supplier_status": "סטטוס", "expected_date": "צפי", "supplier_note": "הערתכם", "mador_response": 'מענה חט"ל',
        }),
        use_container_width=True, hide_index=True,
    )
    st.info("טעיתם בפרט כלשהו? אפשר לחזור ולתקן, ולשלוח שוב.")
    if st.button("✏️ עריכת התשובות", type="primary", use_container_width=True):
        st.session_state.submitted = False
        st.rerun()


# ==================== 6. main ====================
def main():
    init_db()
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("failed_attempts", 0)
    st.session_state.setdefault("submitted", False)

    # כניסה אוטומטית דרך קישור אישי (?key=...)
    url_key = st.query_params.get("key", "").strip().upper()
    if url_key and not st.session_state.user:
        login_with_key(url_key)

    if not st.session_state.user:
        render_login()
        st.stop()

    user = st.session_state.user
    render_top_bar(user)
    conn = get_db()
    if user["role"] in ("admin", "mador"):
        render_staff(conn)
    else:
        render_supplier(conn, user)
    st.markdown('<div class="watermark">Powered by BEN HUR</div>', unsafe_allow_html=True)


main()
