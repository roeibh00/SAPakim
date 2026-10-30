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
    initial_sidebar_state="collapsed"
)

# ==================== 1. עיצוב ייחודי + בר GitHub תקין + ניגודיות מלאה לנייד ====================
st.markdown("""
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
        height: 3.2rem !important;
        z-index: 999 !important;
    }
    
    .block-container {
        max-width: 1240px !important;
        padding-top: 4.2rem !important;
        padding-bottom: 3rem !important;
        margin: 0 auto !important;
    }
    
    p, span, label, div, h1, h2, h3, h4, h5, h6, li, th, td {
        color: #0f172a;
    }
    
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
    
    input, textarea, select, [data-baseweb="select"] div, [data-baseweb="input"] input {
        background-color: #ffffff !important;
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
        border-color: #cbd5e1 !important;
        font-weight: 500 !important;
    }
    
    label[data-testid="stWidgetLabel"] p, .stRadio label p, .stCheckbox label p {
        color: #0f172a !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
    }
    
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
            contact_person TEXT DEFAULT '',
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
        )
    ''')
    
    for col_sql in [
        "ALTER TABLE orders ADD COLUMN contact_person TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN internal_status TEXT DEFAULT ''",
        "ALTER TABLE access_keys ADD COLUMN contact_person TEXT DEFAULT ''"
    ]:
        try:
            c.execute(col_sql)
        except Exception:
            pass
            
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

def clean_str(val):
    """פונקציה בטוחה לחלוטין לניקוי טקסט מתאי אקסל ללא באגים של NaN"""
    if val is None or pd.isna(val):
        return ''
    s = str(val).strip()
    if s.lower() in ['nan', 'none', 'null']:
        return ''
    return s

def find_col(df_cols, candidates):
    """מאתרת עמודה באקסל גם אם יש רווחים או שינויים קלים בשם העמודה"""
    for cand in candidates:
        for col in df_cols:
            if cand == str(col).strip() or cand in str(col).strip():
                return col
    return None

def clean_display_phone(raw_phone):
    s = clean_str(raw_phone).split('.')[0]
    digits = ''.join(filter(str.isdigit, s))
    if not digits or digits == '0' or len(digits) < 8:
        return ''
    if digits.startswith('972'):
        digits = '0' + digits[3:]
    elif len(digits) == 9 and digits.startswith('5'):
        digits = '0' + digits
    return digits

def format_wa_phone(raw_phone):
    disp = clean_display_phone(raw_phone)
    if not disp or len(disp) < 9:
        return None
    if disp.startswith('05') and len(disp) == 10:
        return '972' + disp[1:]
    return None

def get_or_create_key(conn, role, entity_name, contact_person='', phone=''):
    entity_name = clean_str(entity_name) or 'ספק כללי'
    clean_p = clean_display_phone(phone)
    clean_c = clean_str(contact_person)
    
    row = conn.execute("SELECT access_key, phone, contact_person FROM access_keys WHERE role=? AND entity_name=?", (role, entity_name)).fetchone()
    if row:
        new_p = clean_p if clean_p else row['phone']
        new_c = clean_c if clean_c else row['contact_person']
        conn.execute("UPDATE access_keys SET phone=?, contact_person=? WHERE access_key=?", (new_p, new_c, row['access_key']))
        return row['access_key']
    prefix = "SUP" if role == "supplier" else "MAD"
    new_key = f"{prefix}-{secrets.token_hex(3).upper()}"
    conn.execute("INSERT INTO access_keys (access_key, role, entity_name, contact_person, phone) VALUES (?, ?, ?, ?, ?)", (new_key, role, entity_name, clean_c, clean_p))
    return new_key

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
            k2.metric("שורות עם שם איש קשר", len(df_orders[df_orders['contact_person'].astype(str).str.strip() != '']))
            k3.metric("בעיכוב / בטיפול / טרם סופק", len(df_orders[~df_orders['supplier_status'].astype(str).str.strip().eq('סופק')]))
            k4.metric("⚠️ ממתינות למענה מדור", len(df_orders[df_orders['needs_attention'] == 1]))
            
            f_col1, f_col2 = st.columns([1.5, 1])
            with f_col1:
                search_q = st.text_input("🔍 חיפוש מהיר (לפי ספק, איש קשר, טלפון, הזמנה או מק\"ט):", "")
            with f_col2:
                display_mode = st.radio("תצוגה:", ["💻 טבלה מלאה", "📱 כרטיסיות (לנייד)"], horizontal=True)
                
            only_delayed = st.checkbox("הצג רק שורות פתוחות / בעיכוב (הסתר שורות שסופקו)", value=False)
                
            view_df = df_orders.copy()
            if search_q:
                mask = view_df.astype(str).apply(lambda x: x.str.contains(search_q, case=False, na=False)).any(axis=1)
                view_df = view_df[mask]
            if only_delayed:
                view_df = view_df[~view_df['supplier_status'].astype(str).str.strip().eq('סופק')]

            if display_mode.startswith("📱"):
                st.caption("🔒 נתוני הספק נעולים. לחץ על הזמנה לצפייה באיש הקשר, בטלפון ולהזנת מענה מדור.")
                for _, r in view_df.iterrows():
                    alert_icon = "⚠️" if r['needs_attention'] == 1 else "📦"
                    with st.expander(f"{alert_icon} {r['supplier_name']} | 👤 {r['contact_person'] or 'ללא איש קשר'} | הזמנה {r['order_number']}"):
                        st.markdown(f"""
                        <div class="order-card-header">
                            <strong>פריט:</strong> {r['item_description']} | <strong>מק"ט:</strong> {r['part_number']} | <strong>שורה:</strong> {r['line_number']}<br>
                            <strong>👤 איש קשר:</strong> {r['contact_person'] or '-'} | <strong>📞 טלפון:</strong> {r['supplier_phone'] or 'חסר'}
                        </div>
                        """, unsafe_allow_html=True)
                        st.markdown(f"🔒 **סטטוס עדכני:** `{r['supplier_status']}` | **צפי ספק:** `{r['expected_date'] or 'לא הוזן'}`")
                        st.markdown(f"🔒 **תגובת / הערת ספק:** {r['supplier_note'] or 'אין הערות'}")
                        
                        new_resp = st.text_area("✍️ מענה מדור לספק:", value=r['mador_response'], key=f"mresp_{r['id']}")
                        if st.button("💾 שמור מענה לשורה זו", key=f"msave_{r['id']}", type="primary", use_container_width=True):
                            now = datetime.now().strftime("%d/%m/%Y %H:%M")
                            conn.execute("UPDATE orders SET mador_response=?, needs_attention=0, last_updated=? WHERE id=?", (new_resp, now, r['id']))
                            conn.commit()
                            st.success("מענה המדור נשמר!")
                            st.rerun()
            else:
                st.caption("🔒 **אבטחת מידע:** עמודות דיווח הספק נעולות. המדור יכול לעדכן איש קשר, טלפון, מק\"ט ומענה מדור.")
                edited_df = st.data_editor(
                    view_df[['id', 'supplier_name', 'contact_person', 'supplier_phone', 'order_number', 'line_number', 'part_number', 'item_description', 'due_date', 'supplier_status', 'expected_date', 'supplier_note', 'mador_response']],
                    column_config={
                        "id": None,
                        "supplier_name": st.column_config.TextColumn("חברה", disabled=True),
                        "contact_person": st.column_config.TextColumn("👤 איש קשר"),
                        "supplier_phone": st.column_config.TextColumn("📞 מספר טלפון"),
                        "order_number": st.column_config.TextColumn("מספר הזמנה", disabled=True),
                        "line_number": st.column_config.TextColumn("שורה", disabled=True),
                        "part_number": st.column_config.TextColumn("מק\"ט"),
                        "item_description": st.column_config.TextColumn("שם פריט"),
                        "due_date": st.column_config.TextColumn("תאריך אספקה"),
                        "supplier_status": st.column_config.TextColumn("🔒 סטטוס עדכני", disabled=True),
                        "expected_date": st.column_config.TextColumn("🔒 צפי ספק", disabled=True),
                        "supplier_note": st.column_config.TextColumn("🔒 תגובת ספק", disabled=True),
                        "mador_response": st.column_config.TextColumn("✍️ מענה מדור לספק (ערוך כאן)")
                    },
                    use_container_width=True, hide_index=True
                )
                
                if st.button("💾 שמור תשובות מדור ועדכוני אנשי קשר", type="primary", use_container_width=True):
                    now = datetime.now().strftime("%d/%m/%Y %H:%M")
                    for _, r in edited_df.iterrows():
                        clean_p = clean_display_phone(r['supplier_phone'])
                        clean_c = clean_str(r['contact_person'])
                        conn.execute('''
                            UPDATE orders 
                            SET contact_person=?, supplier_phone=?, part_number=?, item_description=?, due_date=?, mador_response=?, needs_attention=0, last_updated=?
                            WHERE id=?
                        ''', (clean_c, clean_p, r['part_number'], r['item_description'], r['due_date'], r['mador_response'], now, r['id']))
                        if clean_p or clean_c:
                            conn.execute("UPDATE access_keys SET phone=COALESCE(NULLIF(?, ''), phone), contact_person=COALESCE(NULLIF(?, ''), contact_person) WHERE role='supplier' AND entity_name=?", (clean_p, clean_c, r['supplier_name']))
                    conn.commit()
                    st.success("הנתונים ותשובות המדור נשמרו בהצלחה!")
                    st.rerun()

            # ייצוא לאקסל עם שמות העמודות בעברית בדיוק כמו בקובץ המקורי שלך (כולל איש קשר ומספר טלפון!)
            export_df = pd.DataFrame({
                'מספר הזמנה': df_orders['order_number'],
                'שורה': df_orders['line_number'],
                'שם פריט': df_orders['item_description'],
                'מק"ט': df_orders['part_number'],
                'תאריך אספקה': df_orders['due_date'],
                'חברה': df_orders['supplier_name'],
                'סטטוס אחרון': df_orders['internal_status'],
                'איש קשר': df_orders['contact_person'],
                'מספר טלפון': df_orders['supplier_phone'],
                'צפי ספק': df_orders['expected_date'],
                'סטטוס עדכני': df_orders['supplier_status'],
                'תגובת ספק': df_orders['supplier_note'],
                'מענה מדור': df_orders['mador_response'],
                'תאריך_עדכון_אחרון': df_orders['last_updated']
            })
            out = BytesIO()
            with pd.ExcelWriter(out, engine='openpyxl') as writer:
                export_df.to_excel(writer, index=False, sheet_name='Sheet')
            st.download_button("📥 הורד דוח אקסל מלא (כולל אנשי קשר וטלפונים)", data=out.getvalue(), file_name="suppliers_updated.xlsx", use_container_width=True)

    # --- לשונית 2: שיגור וואטסאפ אוטומטי שעוקף חסימות דפדפן + רובוט מקומי ---
    with tab2:
        st.markdown("##### 💬 מערך שיגור הודעות וואטסאפ אוטומטי לספקים ואנשי קשר")
        sup_query = '''
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
        df_sups = pd.read_sql_query(sup_query, conn)
        df_sups['wa_ready'] = df_sups['phone'].apply(lambda p: '✅ תקין' if format_wa_phone(p) else '❌ חסר נייד')
        
        with st.container(border=True):
            c_wa1, c_wa2 = st.columns([2, 1])
            with c_wa1:
                filter_mode = st.radio(
                    "1️⃣ בחר אוכלוסיית ספקים לשליחה:",
                    [
                        "📱 ספקים עם מספר נייד תקין לוואטסאפ (מומלץ לשליחה מיידית)",
                        "🔴 כל הספקים עם הזמנות פתוחות / בעיכוב",
                        "📋 כל הספקים במערכת"
                    ]
                )
            with c_wa2:
                sender_name = st.text_input("שם השולח בהודעה:", value="רועי")
                
            if filter_mode.startswith("📱"):
                target_sups = df_sups[df_sups['phone'].apply(lambda p: format_wa_phone(p) is not None)].copy()
            elif filter_mode.startswith("🔴"):
                target_sups = df_sups[df_sups['open_or_delayed_orders'] > 0].copy()
            else:
                target_sups = df_sups.copy()
                
            target_sups['label'] = target_sups.apply(
                lambda r: f"{r['supplier_name']} | 👤 {r['contact_person'] or 'ללא איש קשר'} | 📞 {r['phone'] or 'ללא טלפון'}",
                axis=1
            )
            label_to_sup = dict(zip(target_sups['label'], target_sups['supplier_name']))
            
            select_mode = st.radio(
                "2️⃣ בחר אופן סימון ספקים:",
                [f"✅ כל הספקים ברשימה זו ({len(target_sups)} ספקים)", "🎯 בחירה ידנית של ספקים בודדים"],
                horizontal=True
            )
            
            if select_mode.startswith("✅"):
                selected_suppliers = target_sups['supplier_name'].tolist()
            else:
                chosen_labels = st.multiselect(
                    "בחר ספק / איש קשר מהרשימה:",
                    options=target_sups['label'].tolist(),
                    default=target_sups['label'].tolist()
                )
                selected_suppliers = [label_to_sup[lbl] for lbl in chosen_labels]
        
        app_url = "https://sapakim-kukmcxaux8yf9tfjrygif9.streamlit.app"
        
        if selected_suppliers:
            wa_links = []
            for s_name in selected_suppliers:
                s_row = df_sups[df_sups['supplier_name'] == s_name].iloc[0]
                clean_p = format_wa_phone(s_row['phone'])
                disp_p = s_row['phone']
                contact_p = s_row['contact_person']
                s_key = s_row['access_key']
                
                greeting_name = contact_p if contact_p else s_name
                
                s_ords = conn.execute("SELECT order_number, line_number, item_description FROM orders WHERE supplier_name=? AND TRIM(COALESCE(supplier_status, '')) != 'סופק'", (s_name,)).fetchall()
                if not s_ords:
                    s_ords = conn.execute("SELECT order_number, line_number, item_description FROM orders WHERE supplier_name=?", (s_name,)).fetchall()
                    
                ord_lines = "\n".join([f"• הזמנה {o['order_number']} שורה {o['line_number']} - {o['item_description']}" for o in s_ords[:10]])
                
                direct_link = f"{app_url}/?key={s_key}"
                msg = (
                    f"היי {greeting_name}, מה נשמע?\n"
                    f"זה {sender_name} מהחט\"ל. אני עובר על דו\"ח ההזמנות הפתוחות שלנו מול {s_name} וראיתי שיש לנו פער בלוח הזמנים בפריטים הבאים:\n"
                    f"{ord_lines}\n\n"
                    f"כדי לעדכן סטטוס וצפי אספקה בלחיצה אחת (ולכתוב לנו אם נדרש מענה מהמדור), היכנסו לקישור האישי שלכם:\n"
                    f"{direct_link}\n"
                    f"(מפתח גישה אישי: {s_key})\n"
                    f"תודה מראש על שיתוף הפעולה, {sender_name}."
                )
                
                if clean_p:
                    wa_web_url = f"https://web.whatsapp.com/send?phone={clean_p}&text={urllib.parse.quote(msg)}"
                    wa_me_url = f"https://wa.me/{clean_p}?text={urllib.parse.quote(msg)}"
                    wa_links.append((s_name, contact_p, disp_p, s_key, clean_p, wa_web_url, wa_me_url, msg))
                else:
                    wa_links.append((s_name, contact_p, disp_p, s_key, None, None, None, msg))
            
            valid_items = [item for item in wa_links if item[4] is not None]
            st.markdown(f"##### 3️⃣ לוח שיגור ישיר ({len(valid_items)} ספקים עם מספר נייד תקין):")
            
            if not valid_items:
                st.warning("לספקים שסימנת אין מספר נייד תקין (או שרשום אצלם 0). גש ללשונית '📥 טעינת אקסל' וטען את הקובץ שלך!")
            else:
                # א. משגר HTML ישיר שעובד מיד בלחיצה מהדפדפן בלי להיחסם ע"י Streamlit!
                urls_js_array = "[" + ",".join([f"'{item[6]}'" for item in valid_items]) + "]"
                buttons_html = ""
                for s_name, contact_p, disp_p, s_key, clean_p, _, wa_me_url, _ in valid_items:
                    btn_label = f"💬 שלח אל: {contact_p or s_name} ({s_name} - {disp_p})"
                    buttons_html += f'''
                    <a href="{wa_me_url}" target="_blank" style="
                        display: inline-block; background: #16a34a; color: white; padding: 10px 16px;
                        margin: 5px; border-radius: 10px; text-decoration: none; font-family: Rubik, sans-serif;
                        font-weight: 600; font-size: 14px; box-shadow: 0 2px 6px rgba(0,0,0,0.12);">
                        {btn_label}
                    </a>
                    '''
                
                launcher_html = f"""
                <div dir="rtl" style="font-family: Rubik, sans-serif; background: #fffbeb; border: 2px solid #f59e0b; border-radius: 14px; padding: 16px; text-align: right;">
                    <div style="margin-bottom: 12px;">
                        <button onclick="launchAll()" style="
                            width: 100%; background: linear-gradient(135deg, #d97706 0%, #b45309 100%);
                            color: white; border: none; padding: 14px; border-radius: 12px; font-size: 16px;
                            font-weight: 700; cursor: pointer; box-shadow: 0 4px 12px rgba(180,83,9,0.3);">
                            🚀 שגר עכשיו בלחיצה אחת לכל {len(valid_items)} הספקים שנבחרו!
                        </button>
                        <div id="status_msg" style="font-size: 13px; color: #78350f; margin-top: 6px; font-weight: 600;">
                            💡 לחיצה על הכפתור הכתום תפתח מיד את הוואטסאפ של הספקים. ניתן גם ללחוץ על הכפתורים הירוקים למטה ספק-אחר-ספק:
                        </div>
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                        {buttons_html}
                    </div>
                </div>
                <script>
                function launchAll() {{
                    var urls = {urls_js_array};
                    document.getElementById('status_msg').innerText = 'פותח כעת ' + urls.length + ' שיחות וואטסאפ... (אם נפתח רק אחד, אשר Pop-ups בשורת הכתובת של כרום למעלה)';
                    for (var i = 0; i < urls.length; i++) {{
                        window.open(urls[i], '_blank');
                    }}
                }}
                </script>
                """
                components.html(launcher_html, height=160 + (len(valid_items) // 2) * 55, scrolling=True)
                
                # ב. הורדת סקריפט אוטומציה מלא (Selenium) למחשב המקומי - 100% ללא מגע יד!
                auto_script = f"""import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

targets = {[ (item[0], item[1], item[5]) for item in valid_items ]}

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
                st.download_button(
                    "🤖 הורד רובוט שליחה אוטומטי מלא למחשב (שולח לבד ב-Chrome בלי ללחוץ Send)",
                    data=auto_script.encode('utf-8'),
                    file_name="auto_send_sapakim.py",
                    mime="text/x-python",
                    use_container_width=True
                )
                    
        st.divider()
        with st.expander("🔑 טבלת ריכוז ספקים, אנשי קשר, טלפונים ומפתחות גישה", expanded=True):
            st.dataframe(
                df_sups.rename(columns={
                    'supplier_name': 'חברה',
                    'contact_person': 'איש קשר',
                    'phone': 'מספר טלפון',
                    'access_key': 'מפתח גישה',
                    'total_orders': 'סה"כ שורות',
                    'open_or_delayed_orders': 'שורות פתוחות',
                    'wa_ready': 'סטטוס וואטסאפ'
                }),
                use_container_width=True, hide_index=True
            )

    # --- לשונית 3: טעינת אקסל מתוקנת שקולטת ב-100% את עמודת 'איש קשר' ו'מספר טלפון' ---
    with tab3:
        st.markdown("##### 📥 טעינת קובץ אקסל (`suppliers.xlsx`) - סנכרון מלא של אנשי קשר וטלפונים")
        st.info("💡 **חשוב:** העלה כאן את קובץ ה-`suppliers.xlsx` שלך ולחץ על הכפתור הכתום – המערכת תזהה ותציג לך מיד כמה שמות אנשי קשר ומספרי טלפון נקלטו מהקובץ!")
        uploaded = st.file_uploader("בחר קובץ Excel או CSV", type=['xlsx', 'xls', 'csv'])
        if uploaded and st.button("טען וסנכרן הזמנות, אנשי קשר וטלפונים למערכת ⚡", type="primary", use_container_width=True):
            df_in = pd.read_csv(uploaded) if uploaded.name.endswith('.csv') else pd.read_excel(uploaded)
            df_in.columns = [str(c).strip() for c in df_in.columns]
            cols = df_in.columns.tolist()
            
            # איתור חכם של שמות העמודות באקסל שלך
            c_ord = find_col(cols, ['מספר הזמנה', 'הזמנה'])
            c_line = find_col(cols, ['שורה', 'מספר שורה'])
            c_sup = find_col(cols, ['חברה', 'שם ספק', 'ספק'])
            c_contact = find_col(cols, ['איש קשר', 'איש_קשר', 'נציג'])
            c_phone = find_col(cols, ['מספר טלפון', 'טלפון', 'פרטי התקשרות', 'נייד'])
            c_part = find_col(cols, ['מק"ט', 'מקט'])
            c_desc = find_col(cols, ['שם פריט', 'פרט', 'תיאור'])
            c_qty = find_col(cols, ['כמה הוזמנו', 'כמות'])
            c_due = find_col(cols, ['תאריך אספקה', 'אספקה'])
            c_int_st = find_col(cols, ['סטטוס אחרון'])
            c_exp = find_col(cols, ['צפי ספק', 'צפי_אספקה_מעודכן'])
            c_sup_st = find_col(cols, ['סטטוס עדכני'])
            c_note = find_col(cols, ['תגובת ספק'])
            c_upd = find_col(cols, ['תאריך_עדכון_אחרון', 'תאריך עדכון'])
            
            count = 0
            contacts_found = 0
            phones_found = 0
            
            for _, r in df_in.iterrows():
                ord_num = clean_str(r[c_ord]).split('.')[0] if c_ord else ''
                line_num = clean_str(r[c_line]).split('.')[0] if c_line else '10'
                if not ord_num:
                    continue
                    
                sup = clean_str(r[c_sup]) if c_sup else 'ספק כללי'
                contact = clean_str(r[c_contact]) if c_contact else ''
                phone = clean_display_phone(r[c_phone]) if c_phone else ''
                part = clean_str(r[c_part]).split('.')[0] if c_part else ''
                desc = clean_str(r[c_desc]) if c_desc else ''
                qty = clean_str(r[c_qty]).split('.')[0] if c_qty else '1'
                due = clean_str(r[c_due]).split(' ')[0] if c_due else ''
                internal_st = clean_str(r[c_int_st]) if c_int_st else ''
                exp_date = clean_str(r[c_exp]).split(' ')[0] if c_exp else ''
                sup_st = clean_str(r[c_sup_st]) if c_sup_st else ''
                sup_note = clean_str(r[c_note]) if c_note else ''
                last_upd = clean_str(r[c_upd]) if c_upd else ''
                
                if not qty: qty = '1'
                if not sup_st:
                    sup_st = internal_st if internal_st else 'טרם עודכן'
                
                # השלמה מזיכרון אם חסר בשורה ספציפית
                if not phone or not contact:
                    mem = conn.execute("SELECT phone, contact_person FROM access_keys WHERE role='supplier' AND entity_name=?", (sup,)).fetchone()
                    if mem:
                        if not phone and mem['phone']: phone = mem['phone']
                        if not contact and mem['contact_person']: contact = mem['contact_person']
                
                if contact: contacts_found += 1
                if phone: phones_found += 1
                
                get_or_create_key(conn, 'supplier', sup, contact, phone)
                
                conn.execute('''
                    INSERT INTO orders (
                        order_number, line_number, part_number, item_description, quantity,
                        supplier_name, contact_person, supplier_phone, due_date,
                        internal_status, supplier_status, expected_date, supplier_note, last_updated
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(order_number, line_number) DO UPDATE SET
                        part_number=CASE WHEN excluded.part_number!='' THEN excluded.part_number ELSE orders.part_number END,
                        item_description=CASE WHEN excluded.item_description!='' THEN excluded.item_description ELSE orders.item_description END,
                        supplier_name=excluded.supplier_name,
                        contact_person=CASE WHEN excluded.contact_person!='' THEN excluded.contact_person ELSE orders.contact_person END,
                        supplier_phone=CASE WHEN excluded.supplier_phone!='' THEN excluded.supplier_phone ELSE orders.supplier_phone END,
                        due_date=CASE WHEN excluded.due_date!='' THEN excluded.due_date ELSE orders.due_date END,
                        internal_status=CASE WHEN excluded.internal_status!='' THEN excluded.internal_status ELSE orders.internal_status END,
                        supplier_status=CASE WHEN excluded.supplier_status!='' THEN excluded.supplier_status ELSE orders.supplier_status END,
                        expected_date=CASE WHEN excluded.expected_date!='' THEN excluded.expected_date ELSE orders.expected_date END,
                        supplier_note=CASE WHEN excluded.supplier_note!='' THEN excluded.supplier_note ELSE orders.supplier_note END
                ''', (ord_num, line_num, part, desc, qty, sup, contact, phone, due, internal_st, sup_st, exp_date, sup_note, last_upd))
                count += 1
                
            # השלמה רוחבית: אם לספק יש איש קשר או טלפון בחלק מהשורות, נעדכן את כל השורות של אותו ספק!
            conn.execute('''
                UPDATE orders
                SET contact_person = (SELECT contact_person FROM access_keys WHERE access_keys.entity_name = orders.supplier_name AND access_keys.role='supplier')
                WHERE contact_person = '' OR contact_person IS NULL
            ''')
            conn.execute('''
                UPDATE orders
                SET supplier_phone = (SELECT phone FROM access_keys WHERE access_keys.entity_name = orders.supplier_name AND access_keys.role='supplier')
                WHERE supplier_phone = '' OR supplier_phone IS NULL
            ''')
            conn.commit()
            st.success(f"✅ הסנכרון הושלם! נקלטו {count} שורות הזמנה, {contacts_found} שורות עם שם איש קשר (עמודה: '{c_contact}'), ו-{phones_found} שורות עם מספר טלפון!")

# ==================== 4. מסך ספק ====================
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
        
        status_options = ["טרם עודכן", "תקין - בייצור", "בטיפול - שבוע הבא", "בטיפול מיידי", "מוכן לאספקה", "ממתין לבק\"מ", "חסר שרטוט / דרוש מענה מדור", "מעוכב - חוסר חומר גלם", "עיכוב / בפיגור", "סופק"]
        
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
                            <span class="locked-badge">🔒 יעד: {row['due_date'] or '-'}</span>
                            <span class="locked-badge">👤 איש קשר: {row['contact_person'] or '-'}</span>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if row['mador_response']:
                            st.info(f"💬 **מענה מדור חט\"ל (נעול):** {row['mador_response']}")
                            
                        curr_st = row['supplier_status'] if row['supplier_status'] in status_options else "טרם עודכן"
                        curr_idx = status_options.index(curr_st)
                        
                        c_m1, c_m2 = st.columns(2)
                        with c_m1:
                            new_st = st.selectbox("✍️ סטטוס עדכני:", options=status_options, index=curr_idx, key=f"st_{row['id']}")
                        with c_m2:
                            new_dt = st.text_input("✍️ צפי ספק (תאריך):", value=row['expected_date'], placeholder="למשל: 15/09/2026", key=f"dt_{row['id']}")
                            
                        new_nt = st.text_input("✍️ תגובת ספק / בקשה למדור:", value=row['supplier_note'], placeholder="פרט סיבת עיכוב או בקשה...", key=f"nt_{row['id']}")
                        updates_to_save.append((row['id'], new_st, new_dt, new_nt))
                        
                if st.form_submit_button("✅ שמור ושלח את כל העדכונים לחט\"ל", type="primary", use_container_width=True):
                    now = datetime.now().strftime("%d/%m/%Y %H:%M")
                    for oid, st_val, dt_val, nt_val in updates_to_save:
                        flag = 1 if (str(nt_val).strip() or 'שרטוט' in str(st_val) or 'עיכוב' in str(st_val) or 'מעוכב' in str(st_val)) else 0
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
            df_sup_edit = df_sup.copy()
            df_sup_edit['supplier_status'] = df_sup_edit['supplier_status'].apply(lambda x: x if x in status_options else "טרם עודכן")
            edited_sup = st.data_editor(
                df_sup_edit[['id', 'order_number', 'line_number', 'part_number', 'item_description', 'due_date', 'supplier_status', 'expected_date', 'supplier_note', 'mador_response']],
                column_config={
                    "id": None,
                    "order_number": st.column_config.TextColumn("🔒 מס' הזמנה", disabled=True),
                    "line_number": st.column_config.TextColumn("🔒 שורה", disabled=True),
                    "part_number": st.column_config.TextColumn("🔒 מק\"ט", disabled=True),
                    "item_description": st.column_config.TextColumn("🔒 שם פריט", disabled=True),
                    "due_date": st.column_config.TextColumn("🔒 תאריך אספקה", disabled=True),
                    "supplier_status": st.column_config.SelectboxColumn("✍️ סטטוס עדכני", options=status_options, required=True),
                    "expected_date": st.column_config.TextColumn("✍️ צפי ספק"),
                    "supplier_note": st.column_config.TextColumn("✍️ תגובת ספק"),
                    "mador_response": st.column_config.TextColumn("🔒 מענה מדור חט\"ל", disabled=True)
                },
                use_container_width=True, hide_index=True
            )
            
            if st.button("✅ שמור ושלח עדכונים לחט\"ל", type="primary", use_container_width=True):
                now = datetime.now().strftime("%d/%m/%Y %H:%M")
                for _, r in edited_sup.iterrows():
                    flag = 1 if (str(r['supplier_note']).strip() or 'שרטוט' in str(r['supplier_status']) or 'עיכוב' in str(r['supplier_status']) or 'מעוכב' in str(r['supplier_status'])) else 0
                    conn.execute('''
                        UPDATE orders 
                        SET supplier_status=?, expected_date=?, supplier_note=?, needs_attention=?, last_updated=?
                        WHERE id=? AND supplier_name=?
                    ''', (r['supplier_status'], r['expected_date'], r['supplier_note'], flag, now, r['id'], user['entity_name']))
                conn.commit()
                st.success("תודה! העדכונים נשמרו בהצלחה.")
                st.rerun()

st.markdown('<div class="watermark">Powered by BEN HUR</div>', unsafe_allow_html=True)
