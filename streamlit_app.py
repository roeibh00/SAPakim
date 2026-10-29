import os
import secrets
import sqlite3
import urllib.parse
from datetime import datetime
from io import BytesIO
import pandas as pd
import streamlit as st

st.set_page_config(page_title="SAPakim - פורטל הזמנות", page_icon="🛡️", layout="wide")

# יישור מלא לימין (RTL) ועיצוב חם
st.markdown("""
<style>
    .stApp { direction: rtl; text-align: right; }
    th, td { text-align: right !important; }
    div[data-testid="stMetricValue"] { direction: ltr; text-align: right; }
</style>
""", unsafe_allow_html=True)

DB_PATH = "sapakim_cloud.db"
ADMIN_KEY = "ADMIN-ROEY"

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
    c.execute("INSERT OR IGNORE INTO access_keys (access_key, role, entity_name) VALUES (?, 'admin', 'רועי - מנהל מערכת ראשי')", (ADMIN_KEY,))
    c.execute("INSERT OR IGNORE INTO access_keys (access_key, role, entity_name) VALUES ('MAD-NAMER', 'mador', 'מדור נמ\"ר')")
    c.execute("INSERT OR IGNORE INTO access_keys (access_key, role, entity_name) VALUES ('MAD-MANHAR', 'mador', 'מנה\"ר רכש')")
    conn.commit()
    conn.close()

init_db()

def get_or_create_key(conn, role, entity_name, phone=''):
    entity_name = str(entity_name).strip()
    if not entity_name or entity_name.lower() == 'nan':
        entity_name = 'ספק כללי'
    row = conn.execute("SELECT access_key FROM access_keys WHERE role=? AND entity_name=?", (role, entity_name)).fetchone()
    if row:
        if phone and phone.lower() != 'nan':
            conn.execute("UPDATE access_keys SET phone=? WHERE access_key=?", (phone, row['access_key']))
        return row['access_key']
    prefix = "SUP" if role == "supplier" else "MAD"
    new_key = f"{prefix}-{secrets.token_hex(3).upper()}"
    conn.execute("INSERT INTO access_keys (access_key, role, entity_name, phone) VALUES (?, ?, ?, ?)", (new_key, role, entity_name, phone))
    return new_key

# זיהוי אוטומטי של מפתח גישה מהקישור בוואטסאפ (?key=SUP-XXXX)
query_params = st.query_params
url_key = query_params.get("key", "").strip().upper()

if "user" not in st.session_state:
    st.session_state.user = None

if url_key and not st.session_state.user:
    conn = get_db()
    u = conn.execute("SELECT * FROM access_keys WHERE UPPER(access_key)=?", (url_key,)).fetchone()
    conn.close()
    if u:
        st.session_state.user = dict(u)

# ==================== מסך התחברות ====================
if not st.session_state.user:
    st.title("🛡️ SAPakim - פורטל הזמנות ותקשורת ספקים")
    st.subheader("הזן מפתח גישה אישי (ספק / מדור / מנהל)")
    
    key_input = st.text_input("מפתח גישה (Access Key):", placeholder="לדוגמה: ADMIN-ROEY או MAD-NAMER או SUP-XXXX").strip().upper()
    if st.button("כניסה למערכת 🚀", type="primary"):
        conn = get_db()
        u = conn.execute("SELECT * FROM access_keys WHERE UPPER(access_key)=?", (key_input,)).fetchone()
        conn.close()
        if u:
            st.session_state.user = dict(u)
            st.rerun()
        else:
            st.error("מפתח גישה שגוי. בדוק את הקוד שקיבלת.")
    
    st.info("💡 **מפתחות לבדיקה ראשונית:** מנהל ראשי: `ADMIN-ROEY` | מדור נמ\"ר: `MAD-NAMER` (מפתחות ל-300 הספקים נוצרים אוטומטית בטעינת האקסל).")
    st.stop()

# ==================== משתמש מחובר ====================
user = st.session_state.user
col_t1, col_t2 = st.columns([4, 1])
with col_t1:
    st.title(f"🛡️ SAPakim | שלום, {user['entity_name']}")
    st.caption(f"תפקיד: {user['role']} | מפתח גישה אישי: `{user['access_key']}`")
with col_t2:
    if st.button("התנתק 🚪"):
        st.session_state.user = None
        st.query_params.clear()
        st.rerun()

conn = get_db()

# ==================== מסך מנהל ומדורים ====================
if user['role'] in ['admin', 'mador']:
    tab1, tab2, tab3 = st.tabs(["📊 טבלת הזמנות ומענה לספקים", "📥 טעינת אקסל והוספת הזמנות", "💬 מפתחות גישה ושליחת וואטסאפ לספקים"])
    
    with tab2:
        st.subheader("📥 טעינת קובץ אקסל מהרשת הסגורה (מיזוג חכם ללא דריסת תשובות)")
        uploaded = st.file_uploader("בחר קובץ Excel או CSV", type=['xlsx', 'xls', 'csv'])
        if uploaded and st.button("טען וסנכרן הזמנות למערכת ⚡", type="primary"):
            df_in = pd.read_csv(uploaded) if uploaded.name.endswith('.csv') else pd.read_excel(uploaded)
            df_in.columns = df_in.columns.str.strip()
            count = 0
            for _, r in df_in.iterrows():
                ord_num = str(r.get('מספר הזמנה', r.get('הזמנה', ''))).split('.')[0].strip()
                line_num = str(r.get('שורה', '10')).split('.')[0].strip()
                if not ord_num or ord_num.lower() == 'nan':
                    continue
                sup = str(r.get('חברה', r.get('שם ספק', r.get('ספק', 'ספק כללי')))).strip()
                phone = str(r.get('פרטי התקשרות', r.get('טלפון', ''))).split('.')[0].strip()
                part = str(r.get('מק"ט', r.get('מקט', ''))).split('.')[0].strip()
                desc = str(r.get('שם פריט', r.get('פרט', r.get('תיאור', '')))).strip()
                qty = str(r.get('כמה הוזמנו', r.get('כמות', '1'))).split('.')[0].strip()
                due = str(r.get('אספקה', r.get('תאריך אספקה', ''))).strip()
                
                get_or_create_key(conn, 'supplier', sup, phone)
                conn.execute('''
                    INSERT INTO orders (order_number, line_number, part_number, item_description, quantity, supplier_name, supplier_phone, due_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(order_number, line_number) DO UPDATE SET
                        part_number=excluded.part_number, item_description=excluded.item_description,
                        quantity=excluded.quantity, supplier_name=excluded.supplier_name
                ''', (ord_num, line_num, part, desc, qty, sup, phone, due))
                count += 1
            conn.commit()
            st.success(f"נסרקו ועודכנו {count} שורות הזמנה בהצלחה! מפתחות גישה נוצרו אוטומטית לכל הספקים.")

    with tab3:
        st.subheader("🔑 רשימת ספקים, מפתחות גישה ושיגור מהיר לוואטסאפ")
        keys_df = pd.read_sql_query("SELECT entity_name AS 'שם ספק', access_key AS 'מפתח גישה', phone AS 'טלפון' FROM access_keys WHERE role='supplier' ORDER BY entity_name", conn)
        st.dataframe(keys_df, use_container_width=True)
        
        st.markdown("### 📲 שליחת קישור אישי בוואטסאפ לספק:")
        selected_sup = st.selectbox("בחר ספק לשליחת הודעה עם קישור ישיר:", keys_df['שם ספק'].tolist() if not keys_df.empty else [])
        if selected_sup:
            sup_row = keys_df[keys_df['שם ספק'] == selected_sup].iloc[0]
            s_key = sup_row['מפתח גישה']
            s_phone = str(sup_row['טלפון']).strip()
            msg = f"היי {selected_sup}, מה נשמע?\nזה רועי מהחט\"ל. להיכנס לעדכון סטטוס ההזמנות הפתוחות שלכם במערכת SAPakim לחצו על הקישור האישי שלכם או הזינו מפתח גישה: {s_key}\nתודה!"
            if s_phone and len(s_phone) >= 9:
                clean_p = ''.join(filter(str.isdigit, s_phone))
                if clean_p.startswith('0'): clean_p = '972' + clean_p[1:]
                wa_url = f"https://web.whatsapp.com/send?phone={clean_p}&text={urllib.parse.quote(msg)}"
                st.link_button(f"💬 פתח וואטסאפ אל {selected_sup} ({s_key})", wa_url, type="primary")
            st.code(msg, language="text")

    with tab1:
        df_orders = pd.read_sql_query("SELECT * FROM orders ORDER BY needs_attention DESC, supplier_name, order_number", conn)
        if df_orders.empty:
            st.info("אין עדיין הזמנות במערכת. עבור ללשונית 'טעינת אקסל' כדי להעלות את הקובץ שלך.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("סה\"כ שורות הזמנה", len(df_orders))
            c2.metric("עודכנו ע\"י ספק", len(df_orders[df_orders['supplier_status'] != 'טרם עודכן']))
            c3.metric("⚠️ ממתינות למענה מדור", len(df_orders[df_orders['needs_attention'] == 1]))

            edited_df = st.data_editor(
                df_orders[['id', 'supplier_name', 'order_number', 'line_number', 'part_number', 'item_description', 'quantity', 'supplier_status', 'expected_date', 'supplier_note', 'mador_response']],
                column_config={
                    "id": None,
                    "supplier_name": st.column_config.TextColumn("ספק", disabled=True),
                    "order_number": st.column_config.TextColumn("מס' הזמנה", disabled=True),
                    "line_number": st.column_config.TextColumn("שורה", disabled=True),
                    "part_number": st.column_config.TextColumn("מק\"ט"),
                    "item_description": st.column_config.TextColumn("תיאור פריט"),
                    "quantity": st.column_config.TextColumn("כמות"),
                    "supplier_status": st.column_config.TextColumn("סטטוס ספק", disabled=True),
                    "expected_date": st.column_config.TextColumn("צפי ספק", disabled=True),
                    "supplier_note": st.column_config.TextColumn("בקשת / הערת ספק", disabled=True),
                    "mador_response": st.column_config.TextColumn("✍️ מענה מדור לספק (ערוך כאן)")
                },
                use_container_width=True, hide_index=True
            )
            if st.button("💾 שמור תשובות מדור ועדכונים", type="primary"):
                now = datetime.now().strftime("%d/%m/%Y %H:%M")
                for _, r in edited_df.iterrows():
                    conn.execute('''
                        UPDATE orders SET part_number=?, item_description=?, quantity=?, mador_response=?, needs_attention=0, last_updated=?
                        WHERE id=?
                    ''', (r['part_number'], r['item_description'], r['quantity'], r['mador_response'], now, r['id']))
                conn.commit()
                st.success("השינויים ותשובות המדור נשמרו בהצלחה!")
                st.rerun()

            # ייצוא לאקסל
            out = BytesIO()
            with pd.ExcelWriter(out, engine='openpyxl') as writer:
                df_orders.to_excel(writer, index=False, sheet_name='דוח הזמנות מתוקף')
            st.download_button("📥 הורד דוח מאוחד ומתוקף ל-Excel", data=out.getvalue(), file_name="SAPakim_Report.xlsx")

# ==================== מסך ספק (נעול לשינוי כמויות/מק"טים) ====================
else:
    st.subheader(f"📦 ההזמנות הפתוחות של {user['entity_name']}")
    st.info("שימו לב: פרטי ההזמנה והכמויות נעולים. אנא עדכנו בעמודות המסומנות את הסטטוס הנוכחי, צפי האספקה או בקשה למדור, ולחצו על 'שמור עדכונים' למטה.")
    
    df_sup = pd.read_sql_query("SELECT * FROM orders WHERE supplier_name=? ORDER BY order_number, CAST(line_number AS INTEGER)", conn, params=(user['entity_name'],))
    
    if df_sup.empty:
        st.warning("לא נמצאו הזמנות פתוחות המשויכות אליכם כרגע.")
    else:
        edited_sup = st.data_editor(
            df_sup[['id', 'order_number', 'line_number', 'part_number', 'item_description', 'quantity', 'due_date', 'supplier_status', 'expected_date', 'supplier_note', 'mador_response']],
            column_config={
                "id": None,
                "order_number": st.column_config.TextColumn("מס' הזמנה (נעול)", disabled=True),
                "line_number": st.column_config.TextColumn("שורה (נעול)", disabled=True),
                "part_number": st.column_config.TextColumn("מק\"ט (נעול)", disabled=True),
                "item_description": st.column_config.TextColumn("תיאור פריט (נעול)", disabled=True),
                "quantity": st.column_config.TextColumn("כמות (נעול)", disabled=True),
                "due_date": st.column_config.TextColumn("תאריך חוזי", disabled=True),
                "supplier_status": st.column_config.SelectboxColumn(
                    "✍️ סטטוס הזמנה (בחר)",
                    options=["טרם עודכן", "תקין - בייצור", "מוכן לאספקה", "ממתין לבק\"מ", "חסר שרטוט / דרוש מענה מדור", "עיכוב / בפיגור", "סופק"],
                    required=True
                ),
                "expected_date": st.column_config.TextColumn("✍️ צפי אספקה (תאריך)"),
                "supplier_note": st.column_config.TextColumn("✍️ הערה / בקשה למדור"),
                "mador_response": st.column_config.TextColumn("💬 תשובת מדור חט\"ל", disabled=True)
            },
            use_container_width=True, hide_index=True
        )
        
        if st.button("✅ שמור ושלח עדכונים לחט\"ל", type="primary"):
            now = datetime.now().strftime("%d/%m/%Y %H:%M")
            for _, r in edited_sup.iterrows():
                flag = 1 if (str(r['supplier_note']).strip() or 'שרטוט' in str(r['supplier_status']) or 'עיכוב' in str(r['supplier_status'])) else 0
                conn.execute('''
                    UPDATE orders SET supplier_status=?, expected_date=?, supplier_note=?, needs_attention=?, last_updated=?
                    WHERE id=? AND supplier_name=?
                ''', (r['supplier_status'], r['expected_date'], r['supplier_note'], flag, now, r['id'], user['entity_name']))
            conn.commit()
            st.success("תודה! העדכונים שלכם נשמרו והועברו למדורים בהצלחה.")
            st.rerun()