import secrets
import sqlite3
import time
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
    initial_sidebar_state="collapsed"
)

# ==================== 1. עיצוב ייחודי + החזרת בר GitHub + תיקון מוחלט של כתב לבן בנייד ====================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700&display=swap');
    
    /* כפיית מצב תצוגה בהיר כדי שמכשירים ניידים ב-Dark Mode לא יהפכו את הכתב ללבן! */
    :root, html, body, .stApp {
        color-scheme: light !important;
        font-family: 'Rubik', sans-serif !important;
        direction: rtl;
        text-align: right;
        background: linear-gradient(180deg, #fffbeb 0%, #f8fafc 35%, #f1f5f9 100%) !important;
        color: #0f172a !important;
    }
    
    /* 1. החזרת הבר העליון של GitHub/Streamlit ושמירה שלא יעלה על תוכן הדף */
    header[data-testid="stHeader"] {
        background-color: rgba(255, 251, 235, 0.92) !important;
        backdrop-filter: blur(6px);
        border-bottom: 1px solid #fde68a;
        height: 3.2rem !important;
        z-index: 999 !important;
    }
    
    /* מרווח עליון מותאם כך שהבר העליון לעולם לא יסתיר את כותרת האתר */
    .block-container {
        max-width: 1140px !important;
        padding-top: 4.2rem !important;
        padding-bottom: 3rem !important;
        margin: 0 auto !important;
    }
    
    /* נעילת צבע טקסט כהה וברור בכל האלמנטים בנייד ובמחשב */
    p, span, label, div, h1, h2, h3, h4, h5, h6, li, th, td {
        color: #0f172a;
    }
    
    /* כותרת ראשית ייחודית (Navy & Gold Bronze) */
    .header-box {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 65%, #78350f 100%);
        color: #ffffff !important;
        padding: 1.3rem 1.8rem;
        border-radius: 16px;
        border-bottom: 4px solid #f59e0b;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12);
        margin-bottom: 1.4rem;
        text-align: center;
    }
    .header-title {
        font-size: 1.45rem !important;
        font-weight: 700 !important;
        color: #ffffff !important;
        margin: 0 !important;
    }
    .header-sub {
        font-size: 0.88rem !important;
        color: #fcd34d !important;
        margin-top: 0.3rem !important;
        font-weight: 500;
    }
    
    /* עיצוב כרטיסיות מדדים (KPIs) ייחודי וברור */
    div[data-testid="metric-container"] {
        background: #ffffff !important;
        padding: 0.9rem 1.1rem !important;
        border-radius: 14px !important;
        border: 1px solid #e2e8f0 !important;
        border-right: 5px solid #d97706 !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04) !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: #0f172a !important;
        direction: ltr;
        text-align: right;
    }
    div[data-testid="stMetricLabel"] p {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        color: #475569 !important;
    }
    
    /* תיקון שדות קלט, תיבות בחירה וטפסים בנייד שלא יהיו לבן על לבן */
    input, textarea, select, [data-baseweb="select"] div, [data-baseweb="input"] input {
        background-color: #ffffff !important;
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
        border-color: #cbd5e1 !important;
        font-weight: 500 !important;
    }
    
    /* תוויות מעל שדות (Labels) */
    label[data-testid="stWidgetLabel"] p, .stRadio label p, .stCheckbox label p {
        color: #0f172a !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
    }
    
    /* עיצוב כרטיסיית הזמנה ייחודית לנייד */
    .order-card-header {
        background: linear-gradient(90deg, #fef3c7 0%, #fffbeb 100%);
        color: #78350f !important;
        padding: 0.75rem 1rem;
        border-radius: 10px;
        border-right: 5px solid #d97706;
        margin-bottom: 0.7rem;
        font-size: 0.92rem;
    }
    .order-card-header strong, .order-card-header span {
        color: #78350f !important;
    }
    .locked-badge {
        background: #e2e8f0;
        color: #1e293b !important;
        padding: 0.3rem 0.65rem;
        border-radius: 8px;
        font-size: 0.82rem;
        font-weight: 600;
        display: inline-block;
        margin-left: 0.4rem;
        margin-bottom: 0.4rem;
    }
    
    /* כפתורים ראשיים בולטים בגוון אמבר-זהב */
    button[kind="primary"] {
        background: linear-gradient(135deg, #d97706 0%, #b45309 100%) !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        box-shadow: 0 3px 10px rgba(180, 83, 9, 0.25) !important;
    }
    button[kind="primary"] p, button[kind="primary"] span {
        color: #ffffff !important;
    }
    button[kind="secondary"] {
        background-color: #ffffff !important;
        color: #0f172a !important;
        border: 1.5px solid #cbd5e1 !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
    }
    button[kind="secondary"] p {
        color: #0f172a !important;
    }

    .watermark {
        text-align: center;
        font-size: 0.78rem;
        color: #64748b !important;
        margin-top: 2.2rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }

    /* התאמות מסך לטלפון נייד */
    @media (max-width: 768px) {
        .block-container {
            padding-top: 3.8rem !important;
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
        }
        .header-box {
            padding: 0.95rem 1.1rem;
            border-radius: 12px;
        }
        .header-title {
            font-size: 1.18rem !important;
        }
        input, select, textarea {
            font-size: 16px !important;
        }
    }
</style>
""", unsafe_allow_html=True)

DB_PATH = "sapakim_cloud.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS access_keys (
            access_key TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            UNIQUE(role, entity_name)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT NOT NULL,
            line_number TEXT NOT NULL,
            part_number TEXT DEFAULT '',
            item_description TEXT DEFAULT '',
            quantity TEXT DEFAULT '1',
            supplier_name TEXT DEFAULT 'ספק כללי',
            supplier_phone TEXT DEFAULT '',
            mador_name TEXT DEFAULT 'מדור נמ"ר',
            due_date TEXT DEFAULT '',
            supplier_status TEXT DEFAULT 'טרם עודכן',
            expected_date TEXT DEFAULT '',
            supplier_note TEXT DEFAULT '',
            mador_response TEXT DEFAULT '',
            needs_attention INTEGER DEFAULT 0,
            last_updated TEXT DEFAULT '',
            UNIQUE(order_number, line_number)
        )
    ''')
    
    c.execute("DELETE FROM access_keys WHERE access_key IN ('ADMIN-ROEY', 'MAD-NAMER', 'MAD-MANHAR')")
    secure_keys = [
        ('BH-ADMIN-9920', 'admin', 'רועי - מנהל מערכת ראשי'),
        ('NAMER-7741', 'mador', 'מדור נמ"ר'),
        ('MERKAVA-5582', 'mador', 'מדור מרכבה'),
        ('MANHAR-3319', 'mador', 'מנה"ר רכש')
    ]
    for k, r, name in secure_keys:
        c.execute("INSERT OR REPLACE INTO access_keys (access_key, role, entity_name) VALUES (?, ?, ?)", (k, r, name))
        
    conn.commit()
    conn.close()

init_db()

def get_or_create_key(conn, role, entity_name, phone=''):
    entity_name = str(entity_name).strip()
    if not entity_name or entity_name.lower() == 'nan':
        entity_name = 'ספק כללי'
    row = conn.execute("SELECT access_key, phone FROM access_keys WHERE role=? AND entity_name=?", (role, entity_name)).fetchone()
    if row:
        if phone and phone.lower() != 'nan' and phone.strip() != '':
            conn.execute("UPDATE access_keys SET phone=? WHERE access_key=?", (phone, row['access_key']))
        return row['access_key']
    prefix = "SUP" if role == "supplier" else "MAD"
    new_key = f"{prefix}-{secrets.token_hex(3).upper()}"
    conn.execute("INSERT INTO access_keys (access_key, role, entity_name, phone) VALUES (?, ?, ?, ?)", (new_key, role, entity_name, phone))
    return new_key

def format_wa_phone(raw_phone):
    if not raw_phone or str(raw_phone).lower() == 'nan':
        return None
    p = ''.join(filter(str.isdigit, str(raw_phone).split('.')[0]))
    if p.startswith('972'):
        p = '0' + p[3:]
    if p.startswith('5') and len(p) == 9:
        p = '0' + p
    if not p.startswith('05') or len(p) != 10:
        return None
    return '972' + p[1:]

query_params = st.query_params
url_key = query_params.get("key", "").strip().upper()

if "user" not in st.session_state:
    st.session_state.user = None
if "failed_attempts" not in st.session_state:
    st.session_state.failed_attempts = 0

if url_key and not st.session_state.user:
    conn = get_db()
    u = conn.execute("SELECT * FROM access_keys WHERE UPPER(access_key)=?", (url_key,)).fetchone()
    conn.close()
    if u:
        st.session_state.user = dict(u)

# ==================== 2. מסך כניסה מאובטח ====================
if not st.session_state.user:
    col_l, col_center, col_r = st.columns([0.8, 2, 0.8])
    with col_center:
        st.markdown("""
        <div class="header-box">
            <div class="header-title">🛡️ פורטל SAPakim</div>
            <div class="header-sub">מערכת ארגונית מאובטחת לבקרת הזמנות ותקשורת ספקים</div>
        </div>
        """, unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("##### הזדהות וכניסה למערכת")
            st.caption("אנא הזן את מפתח הגישה האישי (Access Key) שלך.")
            
            if st.session_state.failed_attempts >= 5:
                st.error("הגעת למספר הניסיונות המקסימלי. אנא רענן את הדף או פנה למנהל המערכת.")
                st.stop()
                
            key_input = st.text_input("מפתח גישה סודי:", type="password", placeholder="••••••••••••").strip().upper()
            
            if st.button("התחבר למערכת 🔒", type="primary", use_container_width=True):
                conn = get_db()
                u = conn.execute("SELECT * FROM access_keys WHERE UPPER(access_key)=?", (key_input,)).fetchone()
                conn.close()
                if u:
                    st.session_state.failed_attempts = 0
                    st.session_state.user = dict(u)
                    st.rerun()
                else:
                    st.session_state.failed_attempts += 1
                    st.error(f"מפתח גישה שגוי או שאינו מורשה (ניסיון {st.session_state.failed_attempts}/5).")
                    
        st.markdown('<div class="watermark">Powered by BEN HUR</div>', unsafe_allow_html=True)
    st.stop()

# ==================== כותרת עליונה למשתמש מחובר ====================
user = st.session_state.user
top_c1, top_c2 = st.columns([4.5, 1])
with top_c1:
    st.markdown(f"""
    <div class="header-box" style="text-align: right;">
        <div class="header-title">🛡️ SAPakim | שלום, {user['entity_name']}</div>
        <div class="header-sub">מחובר בהרשאת: {user['role']}</div>
    </div>
    """, unsafe_allow_html=True)
with top_c2:
    if st.button("התנתק 🚪", use_container_width=True):
        st.session_state.user = None
        st.query_params.clear()
        st.rerun()

conn = get_db()

# ==================== 3. ממשק מנהל ומדורים ====================
if user['role'] in ['admin', 'mador']:
    tab1, tab2, tab3 = st.tabs([
        "📊 הזמנות ומענה",
        "💬 שיגור וואטסאפ אוטומטי",
        "📥 טעינת אקסל"
    ])
    
    with tab1:
        df_orders = pd.read_sql_query("SELECT * FROM orders ORDER BY needs_attention DESC, supplier_name, order_number", conn)
        if df_orders.empty:
            st.info("אין עדיין הזמנות במערכת. עבור ללשונית 'טעינת אקסל' כדי להעלות קובץ.")
        else:
            k1, k2 = st.columns(2)
            k3, k4 = st.columns(2)
            k1.metric("סה\"כ שורות הזמנה", len(df_orders))
            k2.metric("עודכנו ע\"י ספק", len(df_orders[df_orders['supplier_status'] != 'טרם עודכן']))
            k3.metric("בעיכוב / טרם עודכן", len(df_orders[(df_orders['supplier_status'] == 'טרם עודכן') | (df_orders['supplier_status'].str.contains('עיכוב|פיגור', na=False))]))
            k4.metric("⚠️ ממתינות למענה מדור", len(df_orders[df_orders['needs_attention'] == 1]))
            
            f_col1, f_col2 = st.columns([1.5, 1])
            with f_col1:
                search_q = st.text_input("🔍 חיפוש מהיר (ספק, הזמנה, מק\"ט או פריט):", "")
            with f_col2:
                display_mode = st.radio("תצוגה:", ["💻 טבלה", "📱 כרטיסיות"], horizontal=True)
                
            only_delayed = st.checkbox("הצג רק שורות בפיגור / ממתינות למענה מדור", value=False)
                
            view_df = df_orders.copy()
            if search_q:
                mask = view_df.astype(str).apply(lambda x: x.str.contains(search_q, case=False, na=False)).any(axis=1)
                view_df = view_df[mask]
            if only_delayed:
                view_df = view_df[(view_df['needs_attention'] == 1) | (view_df['supplier_status'].str.contains('עיכוב|פיגור|טרם', na=False))]

            if display_mode.startswith("📱"):
                st.caption("🔒 נתוני הספק נעולים. לחץ על הזמנה כדי להשיב לספק.")
                for _, r in view_df.iterrows():
                    alert_icon = "⚠️" if r['needs_attention'] == 1 else "📦"
                    with st.expander(f"{alert_icon} {r['supplier_name']} | הזמנה {r['order_number']} שורה {r['line_number']} ({r['supplier_status']})"):
                        st.markdown(f"""
                        <div class="order-card-header">
                            <strong>פריט:</strong> {r['item_description']} | <strong>מק"ט:</strong> {r['part_number']} | <strong>כמות:</strong> {r['quantity']}
                        </div>
                        """, unsafe_allow_html=True)
                        st.markdown(f"🔒 **סטטוס ספק:** `{r['supplier_status']}` | **צפי ספק:** `{r['expected_date'] or 'לא הוזן'}`")
                        st.markdown(f"🔒 **הערת / בקשת ספק:** {r['supplier_note'] or 'אין הערות'}")
                        
                        new_resp = st.text_area("✍️ מענה מדור לספק:", value=r['mador_response'], key=f"mresp_{r['id']}")
                        if st.button("💾 שמור מענה לשורה זו", key=f"msave_{r['id']}", type="primary", use_container_width=True):
                            now = datetime.now().strftime("%d/%m/%Y %H:%M")
                            conn.execute("UPDATE orders SET mador_response=?, needs_attention=0, last_updated=? WHERE id=?", (new_resp, now, r['id']))
                            conn.commit()
                            st.success("מענה המדור נשמר!")
                            st.rerun()
            else:
                st.caption("🔒 **אבטחת מידע:** עמודות דיווח הספק נעולות ולא ניתנות לשינוי ע\"י המדור.")
                edited_df = st.data_editor(
                    view_df[['id', 'supplier_name', 'order_number', 'line_number', 'part_number', 'item_description', 'quantity', 'due_date', 'supplier_status', 'expected_date', 'supplier_note', 'mador_response']],
                    column_config={
                        "id": None,
                        "supplier_name": st.column_config.TextColumn("ספק (נעול)", disabled=True),
                        "order_number": st.column_config.TextColumn("מס' הזמנה (נעול)", disabled=True),
                        "line_number": st.column_config.TextColumn("שורה (נעול)", disabled=True),
                        "part_number": st.column_config.TextColumn("מק\"ט"),
                        "item_description": st.column_config.TextColumn("תיאור פריט"),
                        "quantity": st.column_config.TextColumn("כמות"),
                        "due_date": st.column_config.TextColumn("מועד אספקה"),
                        "supplier_status": st.column_config.TextColumn("🔒 סטטוס ספק", disabled=True),
                        "expected_date": st.column_config.TextColumn("🔒 צפי ספק", disabled=True),
                        "supplier_note": st.column_config.TextColumn("🔒 בקשת / הערת ספק", disabled=True),
                        "mador_response": st.column_config.TextColumn("✍️ מענה מדור לספק (ערוך כאן)")
                    },
                    use_container_width=True, hide_index=True
                )
                
                if st.button("💾 שמור תשובות מדור ועדכונים", type="primary", use_container_width=True):
                    now = datetime.now().strftime("%d/%m/%Y %H:%M")
                    for _, r in edited_df.iterrows():
                        conn.execute('''
                            UPDATE orders 
                            SET part_number=?, item_description=?, quantity=?, due_date=?, mador_response=?, needs_attention=0, last_updated=?
                            WHERE id=?
                        ''', (r['part_number'], r['item_description'], r['quantity'], r['due_date'], r['mador_response'], now, r['id']))
                    conn.commit()
                    st.success("תשובות המדור נשמרו בהצלחה!")
                    st.rerun()

            out = BytesIO()
            with pd.ExcelWriter(out, engine='openpyxl') as writer:
                df_orders.to_excel(writer, index=False, sheet_name='דוח הזמנות מתוקף')
            st.download_button("📥 הורד דוח מאוחד ל-Excel", data=out.getvalue(), file_name="SAPakim_Report.xlsx", use_container_width=True)

    # --- לשונית 2: מערכת שליחת הודעות וואטסאפ אוטומטית בלחיצת כפתור ---
    with tab2:
        st.markdown("##### 💬 מערך שיגור הודעות וואטסאפ אוטומטי לספקים")
        sup_query = '''
            SELECT 
                u.entity_name AS supplier_name,
                u.access_key,
                COALESCE(NULLIF(u.phone, ''), MAX(o.supplier_phone)) AS phone,
                COUNT(o.id) AS total_orders,
                SUM(CASE WHEN o.supplier_status = 'טרם עודכן' OR o.supplier_status LIKE '%עיכוב%' OR o.supplier_status LIKE '%פיגור%' THEN 1 ELSE 0 END) AS lagging_orders
            FROM access_keys u
            LEFT JOIN orders o ON o.supplier_name = u.entity_name
            WHERE u.role = 'supplier'
            GROUP BY u.entity_name
            ORDER BY lagging_orders DESC, u.entity_name
        '''
        df_sups = pd.read_sql_query(sup_query, conn)
        
        with st.container(border=True):
            c_wa1, c_wa2 = st.columns([2, 1])
            with c_wa1:
                filter_mode = st.radio(
                    "1️⃣ בחר אוכלוסיית יעד לשליחה:",
                    ["🔴 ספקים שמאחרים / טרם עדכנו בלבד", "📋 כל הספקים במערכת"],
                    horizontal=True
                )
            with c_wa2:
                sender_name = st.text_input("שם השולח בחתימת ההודעה:", value="רועי")
                
            target_sups = df_sups[df_sups['lagging_orders'] > 0].copy() if filter_mode.startswith("🔴") else df_sups.copy()
            
            select_mode = st.radio(
                "2️⃣ בחר אופן סימון ספקים:",
                [f"✅ כל הספקים ברשימה זו ({len(target_sups)} ספקים)", "🎯 בחירה ידנית של חלק מהספקים"],
                horizontal=True
            )
            
            if select_mode.startswith("✅"):
                selected_suppliers = target_sups['supplier_name'].tolist()
            else:
                selected_suppliers = st.multiselect(
                    "בחר את הספקים הרצויים מהרשימה:",
                    options=target_sups['supplier_name'].tolist(),
                    default=[]
                )
        
        app_url = "https://sapakim-kukmcxaux8yf9tfjrygif9.streamlit.app"
        
        if selected_suppliers:
            wa_links = []
            for s_name in selected_suppliers:
                s_row = df_sups[df_sups['supplier_name'] == s_name].iloc[0]
                clean_p = format_wa_phone(s_row['phone'])
                s_key = s_row['access_key']
                
                s_ords = conn.execute("SELECT order_number, line_number, item_description FROM orders WHERE supplier_name=?", (s_name,)).fetchall()
                ord_lines = "\n".join([f"• הזמנה {o['order_number']} שורה {o['line_number']} ({o['item_description']})" for o in s_ords[:8]])
                
                direct_link = f"{app_url}/?key={s_key}"
                msg = (
                    f"היי {s_name}, מה נשמע?\n"
                    f"זה {sender_name} מהחט\"ל. אני עובר על ההזמנות הפתוחות שלנו וראיתי שיש לנו פער בלוח הזמנים בפריטים הבאים:\n"
                    f"{ord_lines}\n\n"
                    f"כדי לעדכן סטטוס וצפי אספקה בלחיצה אחת (ולכתוב לנו אם נדרש מענה מהמדור), היכנסו לקישור האישי שלכם:\n"
                    f"{direct_link}\n"
                    f"(מפתח גישה אישי: {s_key})\n"
                    f"תודה מראש על שיתוף הפעולה, {sender_name}."
                )
                
                if clean_p:
                    wa_web_url = f"https://web.whatsapp.com/send?phone={clean_p}&text={urllib.parse.quote(msg)}"
                    wa_me_url = f"https://wa.me/{clean_p}?text={urllib.parse.quote(msg)}"
                    wa_links.append((s_name, s_key, clean_p, wa_web_url, wa_me_url, msg))
                else:
                    wa_links.append((s_name, s_key, None, None, None, msg))
            
            valid_items = [item for item in wa_links if item[2] is not None]
            st.markdown(f"##### 3️⃣ שיגור אוטומטי ל-{len(valid_items)} ספקים בעלי מספר נייד תקין:")
            
            btn_c1, btn_c2 = st.columns(2)
            with btn_c1:
                if valid_items and st.button(f"🚀 שגר עכשיו בלחיצה לכל {len(valid_items)} הספקים (פתיחה מתוזמנת בדפדפן)", type="primary", use_container_width=True):
                    # פותח את הצ'אטים בדיליי מדורג כדי לא לתקוע את הדפדפן
                    js_code = "<script>"
                    for idx, item in enumerate(valid_items):
                        delay_ms = idx * 1200
                        js_code += f"setTimeout(function(){{ window.open('{item[4]}', '_blank'); }}, {delay_ms});"
                    js_code += "</script>"
                    components.html(js_code, height=0)
                    st.success(f"משגר כעת {len(valid_items)} שיחות וואטסאפ! (וודא שחלונות קופצים Pop-ups מאושרים בדפדפן).")

            with btn_c2:
                if valid_items and st.button(f"🤖 שגר אוטומטית מלא (Selenium במחשב מקומי)", use_container_width=True):
                    try:
                        from selenium import webdriver
                        from selenium.webdriver.common.by import By
                        from selenium.webdriver.support.ui import WebDriverWait
                        from selenium.webdriver.support import expected_conditions as EC
                        
                        st.info("מפעיל דפדפן אוטומטי... וודא שנסרק ה-QR ב-WhatsApp Web.")
                        options = webdriver.ChromeOptions()
                        options.add_argument(r"user-data-dir=C:\selenium_whatsapp_profile")
                        driver = webdriver.Chrome(options=options)
                        progress = st.progress(0)
                        
                        for idx, (s_name, s_key, clean_p, wa_web_url, _, _) in enumerate(valid_items):
                            driver.get(wa_web_url)
                            try:
                                send_btn = WebDriverWait(driver, 30).until(
                                    EC.element_to_be_clickable((By.XPATH, '//span[@data-icon="send"]/ancestor::button | //button[@aria-label="שליחה"] | //span[@data-icon="send"]'))
                                )
                                time.sleep(2)
                                send_btn.click()
                                time.sleep(6)
                            except Exception:
                                pass
                            progress.progress((idx + 1) / len(valid_items))
                        driver.quit()
                        st.success("כל ההודעות נשלחו אוטומטית בהצלחה!")
                    except Exception:
                        st.warning("שיגור Selenium ללא מגע יד זמין כאשר מריצים את המערכת מקומית על המחשב המשרדי. מהענן השתמש בכפתור השמאלי ('🚀 שגר עכשיו בלחיצה').")

            st.write("")
            for s_name, s_key, clean_p, _, wa_me_url, msg in wa_links:
                with st.expander(f"📲 {s_name} | מפתח: {s_key} | נייד: {clean_p or 'חסר מספר נייד'}"):
                    if wa_me_url:
                        st.link_button(f"💬 שלח וואטסאפ ישירות ל-{s_name}", wa_me_url, type="primary", use_container_width=True)
                    else:
                        st.warning("אין מספר נייד תקין באקסל. העתק הודעה:")
                    st.code(msg, language="text")
                    
        st.divider()
        with st.expander("🔑 צפייה בכל מפתחות הגישה של הספקים"):
            st.dataframe(df_sups, use_container_width=True, hide_index=True)

    # --- לשונית 3: טעינת אקסל ---
    with tab3:
        st.markdown("##### 📥 טעינת קובץ אקסל מהרשת הסגורה")
        uploaded = st.file_uploader("בחר קובץ Excel או CSV", type=['xlsx', 'xls', 'csv'])
        if uploaded and st.button("טען וסנכרן הזמנות למערכת ⚡", type="primary", use_container_width=True):
            df_in = pd.read_csv(uploaded) if uploaded.name.endswith('.csv') else pd.read_excel(uploaded)
            df_in.columns = df_in.columns.str.strip()
            count = 0
            for _, r in df_in.iterrows():
                ord_num = str(r.get('מספר הזמנה', r.get('הזמנה', ''))).split('.')[0].strip()
                line_num = str(r.get('שורה', '10')).split('.')[0].strip()
                if not ord_num or ord_num.lower() == 'nan':
                    continue
                sup = str(r.get('חברה', r.get('שם ספק', r.get('ספק', 'ספק כללי')))).strip()
                phone = str(r.get('פרטי התקשרות', r.get('טלפון', r.get('מספר טלפון', '')))).split('.')[0].strip()
                part = str(r.get('מק"ט', r.get('מקט', ''))).split('.')[0].strip()
                desc = str(r.get('שם פריט', r.get('פרט', r.get('תיאור', '')))).strip()
                qty = str(r.get('כמה הוזמנו', r.get('כמות', '1'))).split('.')[0].strip()
                due = str(r.get('אספקה', r.get('תאריך אספקה', ''))).strip()
                
                if phone.lower() == 'nan': phone = ''
                if part.lower() == 'nan': part = ''
                if desc.lower() == 'nan': desc = ''
                if due.lower() == 'nan': due = ''
                
                if not phone:
                    mem = conn.execute("SELECT phone FROM access_keys WHERE role='supplier' AND entity_name=? AND phone!=''", (sup,)).fetchone()
                    if mem:
                        phone = mem['phone']
                
                get_or_create_key(conn, 'supplier', sup, phone)
                conn.execute('''
                    INSERT INTO orders (order_number, line_number, part_number, item_description, quantity, supplier_name, supplier_phone, due_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(order_number, line_number) DO UPDATE SET
                        part_number=CASE WHEN excluded.part_number!='' THEN excluded.part_number ELSE orders.part_number END,
                        item_description=CASE WHEN excluded.item_description!='' THEN excluded.item_description ELSE orders.item_description END,
                        quantity=excluded.quantity,
                        supplier_name=excluded.supplier_name,
                        supplier_phone=CASE WHEN excluded.supplier_phone!='' THEN excluded.supplier_phone ELSE orders.supplier_phone END
                ''', (ord_num, line_num, part, desc, qty, sup, phone, due))
                count += 1
            conn.commit()
            st.success(f"נסרקו ועודכנו {count} שורות הזמנה בהצלחה!")

# ==================== 4. מסך ספק (מותאם לנייד עם טקסט כהה וברור 100%) ====================
else:
    st.markdown(f"##### 📦 ההזמנות הפתוחות של: {user['entity_name']}")
    
    df_sup = pd.read_sql_query("SELECT * FROM orders WHERE supplier_name=? ORDER BY order_number, CAST(line_number AS INTEGER)", conn, params=(user['entity_name'],))
    
    if df_sup.empty:
        st.warning("לא נמצאו הזמנות פתוחות המשויכות אליכם כרגע.")
    else:
        sup_view = st.radio(
            "בחר אופן תצוגה:",
            ["📱 תצוגת כרטיסיות (לנייד)", "💻 תצוגת טבלה מרוכזת (למחשב)"],
            horizontal=True
        )
        
        status_options = ["טרם עודכן", "תקין - בייצור", "מוכן לאספקה", "ממתין לבק\"מ", "חסר שרטוט / דרוש מענה מדור", "עיכוב / בפיגור", "סופק"]
        
        if sup_view.startswith("📱"):
            st.caption("🔒 פרטי ההזמנה ותשובות המדור נעולים. מלאו את הסטטוס והצפי לכל פריט ולחצו על כפתור השמירה בתחתית הדף.")
            
            with st.form("mobile_supplier_form"):
                updates_to_save = []
                for _, row in df_sup.iterrows():
                    with st.container(border=True):
                        st.markdown(f"""
                        <div class="order-card-header">
                            <strong>🔒 הזמנה: {row['order_number']} | שורה: {row['line_number']}</strong><br>
                            <span>{row['item_description'] or 'ללא תיאור'}</span>
                        </div>
                        <div>
                            <span class="locked-badge">🔒 מק"ט: {row['part_number'] or '-'}</span>
                            <span class="locked-badge">🔒 כמות: {row['quantity']}</span>
                            <span class="locked-badge">🔒 יעד: {row['due_date'] or '-'}</span>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if row['mador_response']:
                            st.info(f"💬 **מענה מדור חט\"ל (נעול):** {row['mador_response']}")
                            
                        curr_idx = status_options.index(row['supplier_status']) if row['supplier_status'] in status_options else 0
                        
                        c_m1, c_m2 = st.columns(2)
                        with c_m1:
                            new_st = st.selectbox("✍️ סטטוס הזמנה:", options=status_options, index=curr_idx, key=f"st_{row['id']}")
                        with c_m2:
                            new_dt = st.text_input("✍️ צפי אספקה (תאריך/שבוע):", value=row['expected_date'], placeholder="למשל: 15/11/2026", key=f"dt_{row['id']}")
                            
                        new_nt = st.text_input("✍️ הערה / בקשה למדור:", value=row['supplier_note'], placeholder="פרט סיבת עיכוב או בקשה לשרטוט...", key=f"nt_{row['id']}")
                        updates_to_save.append((row['id'], new_st, new_dt, new_nt))
                        
                if st.form_submit_button("✅ שמור ושלח את כל העדכונים לחט\"ל", type="primary", use_container_width=True):
                    now = datetime.now().strftime("%d/%m/%Y %H:%M")
                    for oid, st_val, dt_val, nt_val in updates_to_save:
                        flag = 1 if (str(nt_val).strip() or 'שרטוט' in str(st_val) or 'עיכוב' in str(st_val)) else 0
                        conn.execute('''
                            UPDATE orders 
                            SET supplier_status=?, expected_date=?, supplier_note=?, needs_attention=?, last_updated=?
                            WHERE id=? AND supplier_name=?
                        ''', (st_val, dt_val, nt_val, flag, now, oid, user['entity_name']))
                    conn.commit()
                    st.success("תודה! כל העדכונים נשמרו בהצלחה והועברו למדור הרלוונטי.")
                    st.rerun()
        else:
            st.caption("🔒 פרטי ההזמנה ותשובות המדור נעולים לשינוי.")
            edited_sup = st.data_editor(
                df_sup[['id', 'order_number', 'line_number', 'part_number', 'item_description', 'quantity', 'due_date', 'supplier_status', 'expected_date', 'supplier_note', 'mador_response']],
                column_config={
                    "id": None,
                    "order_number": st.column_config.TextColumn("🔒 מס' הזמנה", disabled=True),
                    "line_number": st.column_config.TextColumn("🔒 שורה", disabled=True),
                    "part_number": st.column_config.TextColumn("🔒 מק\"ט", disabled=True),
                    "item_description": st.column_config.TextColumn("🔒 תיאור פריט", disabled=True),
                    "quantity": st.column_config.TextColumn("🔒 כמות", disabled=True),
                    "due_date": st.column_config.TextColumn("🔒 תאריך חוזי", disabled=True),
                    "supplier_status": st.column_config.SelectboxColumn("✍️ סטטוס הזמנה", options=status_options, required=True),
                    "expected_date": st.column_config.TextColumn("✍️ צפי אספקה"),
                    "supplier_note": st.column_config.TextColumn("✍️ הערה / בקשה למדור"),
                    "mador_response": st.column_config.TextColumn("🔒 מענה מדור חט\"ל", disabled=True)
                },
                use_container_width=True, hide_index=True
            )
            
            if st.button("✅ שמור ושלח עדכונים לחט\"ל", type="primary", use_container_width=True):
                now = datetime.now().strftime("%d/%m/%Y %H:%M")
                for _, r in edited_sup.iterrows():
                    flag = 1 if (str(r['supplier_note']).strip() or 'שרטוט' in str(r['supplier_status']) or 'עיכוב' in str(r['supplier_status'])) else 0
                    conn.execute('''
                        UPDATE orders 
                        SET supplier_status=?, expected_date=?, supplier_note=?, needs_attention=?, last_updated=?
                        WHERE id=? AND supplier_name=?
                    ''', (r['supplier_status'], r['expected_date'], r['supplier_note'], flag, now, r['id'], user['entity_name']))
                conn.commit()
                st.success("תודה! העדכונים נשמרו בהצלחה.")
                st.rerun()

st.markdown('<div class="watermark">Powered by BEN HUR</div>', unsafe_allow_html=True)
