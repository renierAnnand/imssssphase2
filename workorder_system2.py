"""
AMIC Work Order & Procurement Management System
Phase 2: Demand List → RFQ → Brigade Pre-Approval → Ministry Approval
"""
import streamlit as st
import pandas as pd
import sqlite3
import random
from datetime import datetime, date, timedelta
from io import BytesIO

st.set_page_config(
    page_title="AMIC OMSS — Work Order & Procurement",
    page_icon="⚙",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
.main .block-container { padding-top: 1.2rem; }
.kpi-card { background:#161b22; border:1px solid #21262d; border-radius:8px; padding:14px 18px; margin-bottom:4px; }
.kpi-label { font-family:'IBM Plex Mono',monospace; font-size:10px; letter-spacing:.08em; text-transform:uppercase; color:#8b949e; }
.kpi-value { font-family:'IBM Plex Mono',monospace; font-size:24px; font-weight:600; color:#f0f6fc; }
.status-pending   { background:#1a1200; border:1px solid #d29922; color:#d29922; padding:2px 8px; border-radius:3px; font-size:11px; font-family:'IBM Plex Mono',monospace; }
.status-approved  { background:#0d2818; border:1px solid #3fb950; color:#3fb950; padding:2px 8px; border-radius:3px; font-size:11px; font-family:'IBM Plex Mono',monospace; }
.status-critical  { background:#1a0a0a; border:1px solid #f85149; color:#f85149; padding:2px 8px; border-radius:3px; font-size:11px; font-family:'IBM Plex Mono',monospace; }
.status-blue      { background:#0a1628; border:1px solid #58a6ff; color:#58a6ff; padding:2px 8px; border-radius:3px; font-size:11px; font-family:'IBM Plex Mono',monospace; }
.section-hdr { font-family:'IBM Plex Mono',monospace; font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:#8b949e; border-bottom:1px solid #21262d; padding-bottom:6px; margin:16px 0 12px; }
.page-title { font-family:'IBM Plex Mono',monospace; font-size:20px; font-weight:600; color:#f0f6fc; border-left:3px solid #1f6feb; padding-left:12px; }
</style>
""", unsafe_allow_html=True)

# ── DATABASE ─────────────────────────────────────────────────────────────────
DB = "amic_omss.db"

def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS work_orders (
        wo_number TEXT PRIMARY KEY,
        creation_date TEXT,
        brigade TEXT,
        vehicle_type TEXT,
        vehicle_id TEXT,
        description TEXT,
        status TEXT DEFAULT 'Open',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS wo_parts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wo_number TEXT,
        mng_part_number TEXT,
        oem_part_number TEXT,
        description_en TEXT,
        description_ar TEXT,
        required_qty REAL,
        procurement_status TEXT DEFAULT 'Procurement Needed',
        expected_delivery_date TEXT,
        rfq_batch_number TEXT,
        indexing_status TEXT DEFAULT 'Completed',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(wo_number) REFERENCES work_orders(wo_number)
    );

    CREATE TABLE IF NOT EXISTS rfq_batches (
        batch_number TEXT PRIMARY KEY,
        created_date TEXT,
        status TEXT DEFAULT 'Draft',
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS rfq_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_number TEXT,
        wo_part_id INTEGER,
        wo_number TEXT,
        mng_part_number TEXT,
        oem_part_number TEXT,
        description_en TEXT,
        description_ar TEXT,
        qty REAL,
        brigade TEXT,
        vehicle_type TEXT,
        vehicle_id TEXT,
        procurement_status TEXT DEFAULT 'Initiated for Procurement',
        expected_delivery_date TEXT,
        FOREIGN KEY(batch_number) REFERENCES rfq_batches(batch_number)
    );

    CREATE TABLE IF NOT EXISTS brigade_approvals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        approval_number TEXT UNIQUE,
        rfq_batch_number TEXT,
        brigade TEXT,
        status TEXT DEFAULT 'Waiting Approval',
        is_outdated INTEGER DEFAULT 0,
        created_date TEXT,
        last_updated TEXT,
        FOREIGN KEY(rfq_batch_number) REFERENCES rfq_batches(batch_number)
    );

    CREATE TABLE IF NOT EXISTS brigade_approval_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        approval_number TEXT,
        rfq_item_id INTEGER,
        wo_number TEXT,
        mng_part_number TEXT,
        oem_part_number TEXT,
        description_en TEXT,
        description_ar TEXT,
        qty REAL,
        vehicle_type TEXT,
        vehicle_id TEXT,
        sector TEXT,
        workshop TEXT,
        FOREIGN KEY(approval_number) REFERENCES brigade_approvals(approval_number)
    );
    """)
    conn.commit()
    conn.close()

def seed_data():
    conn = get_conn()
    c = conn.cursor()
    if c.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0] > 0:
        conn.close()
        return

    random.seed(42)
    brigades    = ["Brigade 1 – Riyadh", "Brigade 2 – Tabuk", "Brigade 3 – Khamis Mushait", "Brigade 4 – Hafar Al-Batin"]
    vtypes      = ["Land Rover Defender", "MRAP Caiman", "HMMWV M1114", "Mercedes Unimog", "IVECO LMV"]
    parts = [
        ("MNG-ENG-001","OEM-LR-4432","Engine Oil Filter","فلتر زيت المحرك"),
        ("MNG-ENG-002","OEM-CM-8812","Air Filter Assembly","مجموعة فلتر الهواء"),
        ("MNG-ENG-003","OEM-LR-9921","Cylinder Head Gasket","طوق رأس الأسطوانة"),
        ("MNG-TRN-001","OEM-MM-3341","Gearbox Filter","فلتر علبة التروس"),
        ("MNG-SUS-001","OEM-LR-7723","Front Shock Absorber","ماص الصدمة الأمامي"),
        ("MNG-SUS-002","OEM-HM-4421","Leaf Spring Rear","ربيع ورقي خلفي"),
        ("MNG-ELC-001","OEM-IV-5512","Alternator 90A","مولد 90 أمبير"),
        ("MNG-ELC-002","OEM-LR-3312","Starter Motor 24V","محرك بدء التشغيل 24 فولت"),
        ("MNG-HYD-001","OEM-MM-9823","Hydraulic Pump","مضخة هيدروليكية"),
        ("MNG-TYR-001","OEM-GN-1122","Tyre 365/85R20 MIL","إطار عسكري"),
        ("MNG-FLT-001","OEM-LR-2211","Fuel Filter","فلتر الوقود"),
        ("MNG-ARM-001","OEM-SY-7741","Periscope Assembly","مجموعة المنظار"),
    ]

    wo_data = []
    for i in range(1, 21):
        wo_num    = f"WO-2026-{i:04d}"
        brig      = random.choice(brigades)
        vtype     = random.choice(vtypes)
        vid       = f"MNG-{random.randint(1000,9999)}"
        cr_date   = (date.today() - timedelta(days=random.randint(1, 45))).isoformat()
        c.execute("INSERT INTO work_orders VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                  (wo_num, cr_date, brig, vtype, vid, f"Maintenance – {vtype}", "Procurement Needed"))
        wo_data.append((wo_num, brig, vtype, vid))

    for wo_num, brig, vtype, vid in wo_data:
        n_parts = random.randint(1, 4)
        for part in random.sample(parts, n_parts):
            mng, oem, en, ar = part
            qty = random.randint(1, 6)
            c.execute("""INSERT INTO wo_parts
                (wo_number,mng_part_number,oem_part_number,description_en,description_ar,
                 required_qty,procurement_status,indexing_status)
                VALUES (?,?,?,?,?,?,'Procurement Needed','Completed')""",
                (wo_num, mng, oem, en, ar, qty))

    conn.commit()
    conn.close()

init_db()
seed_data()

# ── HELPERS ──────────────────────────────────────────────────────────────────
def load_demand_list():
    conn = get_conn()
    df = pd.read_sql("""
        SELECT p.id, p.wo_number, w.creation_date, w.brigade, w.vehicle_type, w.vehicle_id,
               p.mng_part_number, p.oem_part_number, p.description_en, p.description_ar,
               p.required_qty, p.procurement_status, p.rfq_batch_number
        FROM wo_parts p
        JOIN work_orders w ON w.wo_number = p.wo_number
        WHERE p.procurement_status = 'Procurement Needed'
        AND p.indexing_status = 'Completed'
        AND (p.rfq_batch_number IS NULL OR p.rfq_batch_number = '')
        ORDER BY w.creation_date ASC, p.wo_number
    """, conn)
    conn.close()
    return df

def load_rfq_batches():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM rfq_batches ORDER BY created_at DESC", conn)
    conn.close()
    return df

def load_rfq_items(batch_number):
    conn = get_conn()
    df = pd.read_sql("""
        SELECT * FROM rfq_items WHERE batch_number = ? ORDER BY brigade, wo_number
    """, conn, params=(batch_number,))
    conn.close()
    return df

def load_brigade_approvals():
    conn = get_conn()
    df = pd.read_sql("""
        SELECT ba.*, COUNT(bi.id) as item_count
        FROM brigade_approvals ba
        LEFT JOIN brigade_approval_items bi ON bi.approval_number = ba.approval_number
        GROUP BY ba.id ORDER BY ba.created_date DESC
    """, conn)
    conn.close()
    return df

def next_batch_number():
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM rfq_batches").fetchone()[0]
    conn.close()
    return f"RFQ-{date.today().year}-{count+1:04d}"

def next_approval_number(brigade, batch):
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM brigade_approvals").fetchone()[0]
    conn.close()
    brig_code = brigade.split()[1] if len(brigade.split()) > 1 else brigade[:3].upper()
    return f"BAL-{brig_code}-{date.today().year}-{count+1:04d}"

PROC_STATUSES = [
    "Initiated for Procurement",
    "Under Quotation",
    "Pending MNG Procurement Approval",
    "Purchase Order Sent – Pending Delivery",
    "Delivered Partially",
    "Delivered in Full",
]

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:16px 0 20px;">
        <div style="font-family:'IBM Plex Mono',monospace;font-size:15px;font-weight:600;color:#f0f6fc;">⚙ AMIC OMSS</div>
        <div style="font-size:10px;color:#58a6ff;font-family:'IBM Plex Mono',monospace;letter-spacing:.06em;margin-top:3px;">WORK ORDER · PROCUREMENT</div>
    </div>""", unsafe_allow_html=True)

    page = st.radio("MODULE", [
        "📊  Overview",
        "📋  Demand List",
        "📄  RFQ Management",
        "🏴  Brigade Pre-Approval",
        "🔍  Work Order Visibility",
    ])

    st.markdown("<hr style='border-color:#21262d;margin:16px 0;'>", unsafe_allow_html=True)

    conn = get_conn()
    total_wo    = conn.execute("SELECT COUNT(*) FROM work_orders WHERE status='Procurement Needed'").fetchone()[0]
    total_parts = conn.execute("SELECT COUNT(*) FROM wo_parts WHERE procurement_status='Procurement Needed' AND (rfq_batch_number IS NULL OR rfq_batch_number='')").fetchone()[0]
    total_rfq   = conn.execute("SELECT COUNT(*) FROM rfq_batches").fetchone()[0]
    pending_bal = conn.execute("SELECT COUNT(*) FROM brigade_approvals WHERE status='Waiting Approval'").fetchone()[0]
    conn.close()

    for label, val, color in [
        ("OPEN WORK ORDERS", total_wo,    "#d29922"),
        ("PARTS IN DEMAND",  total_parts, "#f85149"),
        ("ACTIVE RFQ LISTS", total_rfq,   "#58a6ff"),
        ("PENDING APPROVAL", pending_bal, "#d29922"),
    ]:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value" style="color:{color};font-size:20px;">{val}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='font-size:10px;color:#484f58;font-family:IBM Plex Mono,monospace;margin-top:16px;'>ALKHORAYEF GROUP · 2026<br>Phase 2 – Procurement Workflow</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊  Overview":
    st.markdown('<div class="page-title">Procurement Workflow Overview</div>', unsafe_allow_html=True)
    st.markdown('<div style="color:#8b949e;font-size:13px;padding-left:15px;margin-bottom:20px;">End-to-end demand management — Demand List → RFQ → Brigade Approval → Oracle</div>', unsafe_allow_html=True)

    col1, col2, col3, col4, col5 = st.columns(5)
    for col, step, label, color in [
        (col1, "1", "Demand List",       "#1f6feb"),
        (col2, "2", "RFQ Creation",      "#d29922"),
        (col3, "3", "Supplier Alignment","#8b949e"),
        (col4, "4", "Brigade Approval",  "#3fb950"),
        (col5, "5", "Oracle Execution",  "#484f58"),
    ]:
        col.markdown(f"""
        <div style="background:#161b22;border:1px solid {color};border-radius:8px;padding:16px;text-align:center;">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:22px;font-weight:600;color:{color};">{step}</div>
            <div style="font-size:12px;color:#c9d1d9;margin-top:6px;">{label}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    conn = get_conn()
    # Work Order status breakdown
    st.markdown('<div class="section-hdr">Work Order Procurement Status Breakdown</div>', unsafe_allow_html=True)
    status_data = pd.read_sql("""
        SELECT procurement_status, COUNT(*) as count, SUM(required_qty) as total_qty
        FROM wo_parts GROUP BY procurement_status ORDER BY count DESC
    """, conn)
    st.dataframe(status_data.rename(columns={
        "procurement_status":"Status","count":"Parts","total_qty":"Total Qty"
    }), use_container_width=True, hide_index=True)

    st.markdown('<div class="section-hdr">Brigade Demand Summary</div>', unsafe_allow_html=True)
    brig_data = pd.read_sql("""
        SELECT w.brigade, COUNT(DISTINCT p.wo_number) as work_orders,
               COUNT(p.id) as parts,
               SUM(p.required_qty) as total_qty
        FROM wo_parts p JOIN work_orders w ON w.wo_number=p.wo_number
        WHERE p.procurement_status='Procurement Needed'
        GROUP BY w.brigade ORDER BY parts DESC
    """, conn)
    st.dataframe(brig_data.rename(columns={
        "brigade":"Brigade","work_orders":"Work Orders","parts":"Parts","total_qty":"Total Qty"
    }), use_container_width=True, hide_index=True)
    conn.close()

# ══════════════════════════════════════════════════════════════════════════════
# DEMAND LIST
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋  Demand List":
    st.markdown('<div class="page-title">Demand List</div>', unsafe_allow_html=True)
    st.markdown('<div style="color:#8b949e;font-size:13px;padding-left:15px;margin-bottom:20px;">All Work Orders requiring procurement · Status = Procurement Needed · Indexing = Completed</div>', unsafe_allow_html=True)

    demand_df = load_demand_list()

    # Filters
    f1, f2, f3, f4 = st.columns(4)
    brigades = ["All"] + sorted(demand_df["brigade"].unique().tolist()) if not demand_df.empty else ["All"]
    vtypes   = ["All"] + sorted(demand_df["vehicle_type"].unique().tolist()) if not demand_df.empty else ["All"]
    parts_list = ["All"] + sorted(demand_df["mng_part_number"].unique().tolist()) if not demand_df.empty else ["All"]

    sel_brigade = f1.selectbox("Brigade", brigades)
    sel_vtype   = f2.selectbox("Vehicle Type", vtypes)
    sel_part    = f3.selectbox("Part Number", parts_list)
    search_wo   = f4.text_input("Search Work Order", placeholder="WO-2026-...")

    filtered = demand_df.copy()
    if sel_brigade != "All":   filtered = filtered[filtered.brigade == sel_brigade]
    if sel_vtype   != "All":   filtered = filtered[filtered.vehicle_type == sel_vtype]
    if sel_part    != "All":   filtered = filtered[filtered.mng_part_number == sel_part]
    if search_wo:              filtered = filtered[filtered.wo_number.str.contains(search_wo, case=False)]

    st.markdown(f'<div class="section-hdr">Demand Lines — {len(filtered)} parts across {filtered["wo_number"].nunique() if not filtered.empty else 0} Work Orders</div>', unsafe_allow_html=True)

    if filtered.empty:
        st.success("✅ No parts currently awaiting procurement.")
    else:
        # Checkbox selection
        filtered_reset = filtered.reset_index(drop=True)
        selected_ids   = []

        cols = st.columns([0.4, 1.2, 1.1, 1.2, 1.3, 1.3, 1.3, 1.3, 1.5, 1.0])
        headers = ["✓", "WO Number", "Date", "Brigade", "Vehicle Type", "Vehicle ID", "MNG Part No", "OEM Part No", "Description (EN)", "Qty"]
        for col, h in zip(cols, headers):
            col.markdown(f"**{h}**")

        st.markdown("<hr style='margin:4px 0;border-color:#21262d;'>", unsafe_allow_html=True)

        checkboxes = {}
        for idx, row in filtered_reset.iterrows():
            cols = st.columns([0.4, 1.2, 1.1, 1.2, 1.3, 1.3, 1.3, 1.3, 1.5, 1.0])
            checkboxes[row["id"]] = cols[0].checkbox("", key=f"chk_{row['id']}")
            cols[1].markdown(f"<span style='font-family:IBM Plex Mono;font-size:12px;color:#58a6ff'>{row['wo_number']}</span>", unsafe_allow_html=True)
            cols[2].markdown(f"<span style='font-size:12px;color:#8b949e'>{row['creation_date']}</span>", unsafe_allow_html=True)
            cols[3].markdown(f"<span style='font-size:12px'>{row['brigade']}</span>", unsafe_allow_html=True)
            cols[4].markdown(f"<span style='font-size:12px'>{row['vehicle_type']}</span>", unsafe_allow_html=True)
            cols[5].markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px;color:#8b949e'>{row['vehicle_id']}</span>", unsafe_allow_html=True)
            cols[6].markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px;color:#f0f6fc'>{row['mng_part_number']}</span>", unsafe_allow_html=True)
            cols[7].markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px;color:#8b949e'>{row['oem_part_number']}</span>", unsafe_allow_html=True)
            cols[8].markdown(f"<span style='font-size:12px'>{row['description_en']}</span>", unsafe_allow_html=True)
            cols[9].markdown(f"<span style='font-family:IBM Plex Mono;font-weight:600;color:#3fb950'>{int(row['required_qty'])}</span>", unsafe_allow_html=True)

        selected_ids = [pid for pid, checked in checkboxes.items() if checked]

        st.markdown("<br>", unsafe_allow_html=True)
        bc1, bc2 = st.columns([2, 8])
        if bc1.button("📄 Create RFQ List", type="primary", disabled=(len(selected_ids) == 0)):
            if selected_ids:
                batch_no = next_batch_number()
                conn = get_conn()
                conn.execute("INSERT INTO rfq_batches (batch_number, created_date, status) VALUES (?,?,?)",
                             (batch_no, date.today().isoformat(), "Draft"))

                for pid in selected_ids:
                    row = demand_df[demand_df["id"] == pid].iloc[0]
                    conn.execute("""
                        INSERT INTO rfq_items
                        (batch_number, wo_part_id, wo_number, mng_part_number, oem_part_number,
                         description_en, description_ar, qty, brigade, vehicle_type, vehicle_id)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """, (batch_no, pid, row["wo_number"], row["mng_part_number"],
                          row["oem_part_number"], row["description_en"], row["description_ar"],
                          row["required_qty"], row["brigade"], row["vehicle_type"], row["vehicle_id"]))
                    conn.execute("UPDATE wo_parts SET rfq_batch_number=? WHERE id=?", (batch_no, pid))

                conn.commit()
                conn.close()
                st.success(f"✅ RFQ List **{batch_no}** created with {len(selected_ids)} parts. Go to RFQ Management to edit and export.")
                st.rerun()

        if selected_ids:
            bc2.info(f"ℹ {len(selected_ids)} line(s) selected")

# ══════════════════════════════════════════════════════════════════════════════
# RFQ MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📄  RFQ Management":
    st.markdown('<div class="page-title">RFQ Management</div>', unsafe_allow_html=True)
    st.markdown('<div style="color:#8b949e;font-size:13px;padding-left:15px;margin-bottom:20px;">Create, edit and export RFQ lists · Align with supplier quotations · Generate Brigade Approvals</div>', unsafe_allow_html=True)

    batches = load_rfq_batches()

    if batches.empty:
        st.info("No RFQ lists yet. Go to Demand List and select parts to create one.")
    else:
        # Batch selector
        batch_options = batches["batch_number"].tolist()
        sel_batch = st.selectbox("Select RFQ Batch", batch_options)

        batch_info = batches[batches.batch_number == sel_batch].iloc[0]
        rfq_items  = load_rfq_items(sel_batch)

        # Header info
        h1, h2, h3, h4 = st.columns(4)
        h1.markdown(f"""<div class="kpi-card kpi-blue"><div class="kpi-label">BATCH NUMBER</div><div class="kpi-value" style="font-size:16px;color:#58a6ff">{sel_batch}</div></div>""", unsafe_allow_html=True)
        h2.markdown(f"""<div class="kpi-card"><div class="kpi-label">CREATED</div><div class="kpi-value" style="font-size:16px;">{batch_info['created_date']}</div></div>""", unsafe_allow_html=True)
        status_color = {"Draft":"#d29922","Finalized":"#3fb950","Submitted":"#58a6ff"}.get(batch_info["status"],"#8b949e")
        h3.markdown(f"""<div class="kpi-card"><div class="kpi-label">STATUS</div><div class="kpi-value" style="font-size:16px;color:{status_color}">{batch_info['status']}</div></div>""", unsafe_allow_html=True)
        h4.markdown(f"""<div class="kpi-card"><div class="kpi-label">TOTAL LINES</div><div class="kpi-value" style="font-size:16px;">{len(rfq_items)}</div></div>""", unsafe_allow_html=True)

        tabs = st.tabs(["📋 RFQ Items", "➕ Add Parts", "📊 Status Updates", "📤 Export", "🏴 Brigade Approval"])

        # ── TAB 1: RFQ Items ────────────────────────────────────────────────
        with tabs[0]:
            st.markdown('<div class="section-hdr">RFQ Line Items — Editable</div>', unsafe_allow_html=True)
            if rfq_items.empty:
                st.warning("No items in this RFQ batch.")
            else:
                remove_ids = []
                for _, row in rfq_items.iterrows():
                    c1,c2,c3,c4,c5,c6,c7,c8 = st.columns([1.2,1.1,1.3,1.4,1.6,0.8,1.5,0.6])
                    c1.markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px;color:#58a6ff'>{row['wo_number']}</span>", unsafe_allow_html=True)
                    c2.markdown(f"<span style='font-size:11px;color:#8b949e'>{row['brigade']}</span>", unsafe_allow_html=True)
                    c3.markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px'>{row['mng_part_number']}</span>", unsafe_allow_html=True)
                    c4.markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px;color:#8b949e'>{row['oem_part_number']}</span>", unsafe_allow_html=True)
                    c5.markdown(f"<span style='font-size:12px'>{row['description_en']}</span>", unsafe_allow_html=True)
                    c6.markdown(f"<span style='font-family:IBM Plex Mono;font-weight:600;color:#3fb950'>{int(row['qty'])}</span>", unsafe_allow_html=True)
                    status_col = {"Initiated for Procurement":"status-blue","Under Quotation":"status-pending",
                                  "Pending MNG Procurement Approval":"status-pending","Purchase Order Sent – Pending Delivery":"status-blue",
                                  "Delivered Partially":"status-pending","Delivered in Full":"status-approved"}.get(row.get("procurement_status",""),"")
                    c7.markdown(f"<span class='{status_col}' style='font-size:10px'>{row.get('procurement_status','')}</span>", unsafe_allow_html=True)
                    if c8.button("🗑", key=f"rm_{row['id']}", help="Remove from RFQ (returns to Demand List)"):
                        remove_ids.append((row["id"], row["wo_part_id"]))

                if remove_ids:
                    conn = get_conn()
                    for rfq_id, part_id in remove_ids:
                        conn.execute("DELETE FROM rfq_items WHERE id=?", (rfq_id,))
                        conn.execute("UPDATE wo_parts SET rfq_batch_number=NULL WHERE id=?", (part_id,))
                        conn.execute("""
                            UPDATE brigade_approvals SET is_outdated=1, last_updated=?
                            WHERE rfq_batch_number=?
                        """, (datetime.now().isoformat(), sel_batch))
                    conn.commit()
                    conn.close()
                    st.success("✅ Part(s) removed and returned to Demand List. Brigade Approval Lists flagged as Outdated.")
                    st.rerun()

                # Finalize button
                st.markdown("<br>", unsafe_allow_html=True)
                if batch_info["status"] == "Draft":
                    if st.button("✅ Finalize RFQ List", type="primary"):
                        conn = get_conn()
                        conn.execute("UPDATE rfq_batches SET status='Finalized' WHERE batch_number=?", (sel_batch,))
                        conn.commit()
                        conn.close()
                        st.success("✅ RFQ List finalized. Ready for Brigade Approval generation.")
                        st.rerun()
                else:
                    st.success(f"🔒 RFQ Status: **{batch_info['status']}**")

        # ── TAB 2: Add Parts ────────────────────────────────────────────────
        with tabs[1]:
            st.markdown('<div class="section-hdr">Add Parts from Demand List</div>', unsafe_allow_html=True)
            available = load_demand_list()
            if available.empty:
                st.info("No parts available in Demand List.")
            else:
                add_ids = []
                for _, row in available.head(30).iterrows():
                    c1,c2,c3,c4,c5,c6 = st.columns([0.4,1.2,1.2,1.4,1.6,0.8])
                    cb = c1.checkbox("", key=f"add_{row['id']}")
                    if cb: add_ids.append(row["id"])
                    c2.markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px;color:#58a6ff'>{row['wo_number']}</span>", unsafe_allow_html=True)
                    c3.markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px'>{row['mng_part_number']}</span>", unsafe_allow_html=True)
                    c4.markdown(f"<span style='font-size:11px;color:#8b949e'>{row['brigade']}</span>", unsafe_allow_html=True)
                    c5.markdown(f"<span style='font-size:12px'>{row['description_en']}</span>", unsafe_allow_html=True)
                    c6.markdown(f"<span style='font-family:IBM Plex Mono;color:#3fb950'>{int(row['required_qty'])}</span>", unsafe_allow_html=True)

                if st.button("➕ Add Selected to RFQ", type="primary", disabled=len(add_ids)==0):
                    conn = get_conn()
                    demand_full = load_demand_list()
                    for pid in add_ids:
                        row = demand_full[demand_full["id"]==pid].iloc[0]
                        conn.execute("""
                            INSERT INTO rfq_items
                            (batch_number,wo_part_id,wo_number,mng_part_number,oem_part_number,
                             description_en,description_ar,qty,brigade,vehicle_type,vehicle_id)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """, (sel_batch, pid, row["wo_number"], row["mng_part_number"],
                              row["oem_part_number"], row["description_en"], row["description_ar"],
                              row["required_qty"], row["brigade"], row["vehicle_type"], row["vehicle_id"]))
                        conn.execute("UPDATE wo_parts SET rfq_batch_number=? WHERE id=?", (sel_batch, pid))
                        conn.execute("UPDATE brigade_approvals SET is_outdated=1 WHERE rfq_batch_number=?", (sel_batch,))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ {len(add_ids)} part(s) added to {sel_batch}.")
                    st.rerun()

        # ── TAB 3: Status Updates ───────────────────────────────────────────
        with tabs[2]:
            st.markdown('<div class="section-hdr">Update Procurement Status per Part</div>', unsafe_allow_html=True)
            if rfq_items.empty:
                st.warning("No items in this RFQ.")
            else:
                for _, row in rfq_items.iterrows():
                    c1,c2,c3,c4,c5 = st.columns([1.2,1.4,1.6,2.0,1.4])
                    c1.markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px;color:#58a6ff'>{row['wo_number']}</span>", unsafe_allow_html=True)
                    c2.markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px'>{row['mng_part_number']}</span>", unsafe_allow_html=True)
                    c3.markdown(f"<span style='font-size:12px'>{row['description_en']}</span>", unsafe_allow_html=True)
                    cur_idx = PROC_STATUSES.index(row["procurement_status"]) if row["procurement_status"] in PROC_STATUSES else 0
                    new_status = c4.selectbox("", PROC_STATUSES, index=cur_idx, key=f"ps_{row['id']}", label_visibility="collapsed")
                    exp_del = c5.date_input("", value=date.today() + timedelta(days=30), key=f"ed_{row['id']}", label_visibility="collapsed")

                    if new_status != row["procurement_status"] or str(exp_del) != str(row.get("expected_delivery_date","")):
                        conn = get_conn()
                        conn.execute("""
                            UPDATE rfq_items SET procurement_status=?, expected_delivery_date=? WHERE id=?
                        """, (new_status, str(exp_del), row["id"]))
                        conn.execute("""
                            UPDATE wo_parts SET procurement_status=?, expected_delivery_date=?, rfq_batch_number=?
                            WHERE id=?
                        """, (new_status, str(exp_del), sel_batch, row["wo_part_id"]))
                        conn.commit()
                        conn.close()

        # ── TAB 4: Export ───────────────────────────────────────────────────
        with tabs[3]:
            st.markdown('<div class="section-hdr">Export RFQ to Excel (for Oracle Fusion upload)</div>', unsafe_allow_html=True)
            if rfq_items.empty:
                st.warning("No items to export.")
            else:
                export_df = rfq_items[["batch_number","wo_number","mng_part_number","oem_part_number",
                                        "description_en","description_ar","qty","brigade","vehicle_type","vehicle_id"]].copy()
                export_df.columns = ["Batch Number","WO Number","MNG Part No","OEM Part No",
                                      "Description (EN)","Description (AR)","Qty","Brigade","Vehicle Type","Vehicle ID"]
                buf = BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    export_df.to_excel(writer, index=False, sheet_name="RFQ List")
                buf.seek(0)
                st.download_button(
                    "📥 Download RFQ Excel",
                    data=buf,
                    file_name=f"{sel_batch}_RFQ.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
                st.dataframe(export_df, use_container_width=True, hide_index=True)

        # ── TAB 5: Brigade Approval ─────────────────────────────────────────
        with tabs[4]:
            st.markdown('<div class="section-hdr">Generate / Regenerate Brigade Pre-Approval Lists</div>', unsafe_allow_html=True)

            # Check for outdated
            conn = get_conn()
            outdated = conn.execute("""
                SELECT COUNT(*) FROM brigade_approvals WHERE rfq_batch_number=? AND is_outdated=1
            """, (sel_batch,)).fetchone()[0]
            conn.close()

            if outdated > 0:
                st.warning(f"⚠️ {outdated} Brigade Pre-Approval List(s) are **Outdated** due to RFQ changes. Regeneration required.")

            if batch_info["status"] != "Finalized":
                st.error("❌ RFQ must be **Finalized** before generating Brigade Approval Lists. Go to RFQ Items tab and click Finalize.")
            else:
                brigades_in_rfq = rfq_items["brigade"].unique().tolist() if not rfq_items.empty else []
                gen_option = st.radio("Regeneration Option", ["All Brigades", "Selected Brigade(s)"])

                if gen_option == "Selected Brigade(s)":
                    sel_brigades = st.multiselect("Select Brigade(s)", brigades_in_rfq)
                else:
                    sel_brigades = brigades_in_rfq

                if st.button("🏴 Generate Brigade Approval Lists", type="primary", disabled=not sel_brigades):
                    conn = get_conn()
                    for brig in sel_brigades:
                        brig_items = rfq_items[rfq_items["brigade"] == brig]
                        if brig_items.empty:
                            continue

                        # Check if exists — replace
                        existing = conn.execute("""
                            SELECT approval_number FROM brigade_approvals
                            WHERE rfq_batch_number=? AND brigade=?
                        """, (sel_batch, brig)).fetchone()

                        if existing:
                            appr_no = existing[0]
                            conn.execute("DELETE FROM brigade_approval_items WHERE approval_number=?", (appr_no,))
                            conn.execute("""
                                UPDATE brigade_approvals SET status='Waiting Approval', is_outdated=0, last_updated=?
                                WHERE approval_number=?
                            """, (datetime.now().isoformat(), appr_no))
                        else:
                            appr_no = next_approval_number(brig, sel_batch)
                            conn.execute("""
                                INSERT INTO brigade_approvals
                                (approval_number, rfq_batch_number, brigade, status, is_outdated, created_date, last_updated)
                                VALUES (?,?,?,'Waiting Approval',0,?,?)
                            """, (appr_no, sel_batch, brig, date.today().isoformat(), datetime.now().isoformat()))

                        for _, item in brig_items.iterrows():
                            sector   = "Sector " + item["brigade"].split()[1] if len(item["brigade"].split()) > 1 else "S1"
                            workshop = f"WS-{item['vehicle_type'][:3].upper()}"
                            conn.execute("""
                                INSERT INTO brigade_approval_items
                                (approval_number,rfq_item_id,wo_number,mng_part_number,oem_part_number,
                                 description_en,description_ar,qty,vehicle_type,vehicle_id,sector,workshop)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                            """, (appr_no, item["id"], item["wo_number"], item["mng_part_number"],
                                  item["oem_part_number"], item["description_en"], item["description_ar"],
                                  item["qty"], item["vehicle_type"], item["vehicle_id"], sector, workshop))

                    conn.commit()
                    conn.close()
                    st.success(f"✅ Brigade Pre-Approval Lists generated for: {', '.join(sel_brigades)}")
                    st.rerun()

                # Show existing approvals for this batch
                conn = get_conn()
                existing_approvals = pd.read_sql("""
                    SELECT approval_number, brigade, status, is_outdated, created_date, last_updated
                    FROM brigade_approvals WHERE rfq_batch_number=? ORDER BY brigade
                """, conn, params=(sel_batch,))
                conn.close()

                if not existing_approvals.empty:
                    st.markdown('<div class="section-hdr">Existing Brigade Approval Lists for this RFQ</div>', unsafe_allow_html=True)
                    for _, row in existing_approvals.iterrows():
                        c1,c2,c3,c4 = st.columns([1.5,2,1.2,1])
                        c1.markdown(f"<span style='font-family:IBM Plex Mono;font-size:12px;color:#58a6ff'>{row['approval_number']}</span>", unsafe_allow_html=True)
                        c2.markdown(f"<span style='font-size:12px'>{row['brigade']}</span>", unsafe_allow_html=True)
                        status_cls = "status-approved" if row["status"]=="Approved" else "status-pending"
                        c3.markdown(f"<span class='{status_cls}'>{row['status']}</span>{'&nbsp;<span style=\"color:#f85149;font-size:10px\">⚠ OUTDATED</span>' if row['is_outdated'] else ''}", unsafe_allow_html=True)
                        c4.markdown(f"<span style='font-size:11px;color:#8b949e'>{row['last_updated'][:10] if row['last_updated'] else ''}</span>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# BRIGADE PRE-APPROVAL
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🏴  Brigade Pre-Approval":
    st.markdown('<div class="page-title">Brigade Pre-Approval Lists</div>', unsafe_allow_html=True)
    st.markdown('<div style="color:#8b949e;font-size:13px;padding-left:15px;margin-bottom:20px;">Review, approve or return Brigade Pre-Approval Lists for Commander sign-off</div>', unsafe_allow_html=True)

    approvals = load_brigade_approvals()

    if approvals.empty:
        st.info("No Brigade Pre-Approval Lists generated yet. Go to RFQ Management to generate them.")
    else:
        # Filter
        f1, f2 = st.columns(2)
        brigades_list = ["All"] + sorted(approvals["brigade"].unique().tolist())
        status_list   = ["All"] + sorted(approvals["status"].unique().tolist())
        sel_brig   = f1.selectbox("Brigade", brigades_list)
        sel_status = f2.selectbox("Status", status_list)

        filtered_approvals = approvals.copy()
        if sel_brig   != "All": filtered_approvals = filtered_approvals[filtered_approvals.brigade == sel_brig]
        if sel_status != "All": filtered_approvals = filtered_approvals[filtered_approvals.status == sel_status]

        # Summary KPIs
        k1,k2,k3,k4 = st.columns(4)
        k1.metric("Total Lists",      len(approvals))
        k2.metric("Waiting Approval", len(approvals[approvals.status=="Waiting Approval"]))
        k3.metric("Approved",         len(approvals[approvals.status=="Approved"]))
        k4.metric("Outdated",         len(approvals[approvals.is_outdated==1]))

        st.markdown('<div class="section-hdr">Brigade Pre-Approval List Register</div>', unsafe_allow_html=True)

        for _, row in filtered_approvals.iterrows():
            with st.expander(f"{'⚠️ OUTDATED — ' if row['is_outdated'] else ''}{row['approval_number']} · {row['brigade']} · {row['status']} · {row['item_count']} parts"):

                # Show items
                conn = get_conn()
                items = pd.read_sql("""
                    SELECT sector, workshop, wo_number, mng_part_number, oem_part_number,
                           description_en, description_ar, qty, vehicle_type, vehicle_id
                    FROM brigade_approval_items WHERE approval_number=?
                """, conn, params=(row["approval_number"],))
                conn.close()

                st.markdown(f"**RFQ:** {row['rfq_batch_number']} &nbsp;|&nbsp; **Created:** {row['created_date']} &nbsp;|&nbsp; **Last Updated:** {row['last_updated'][:10] if row['last_updated'] else '—'}")
                st.dataframe(items.rename(columns={
                    "sector":"Sector","workshop":"Workshop","wo_number":"WO Number",
                    "mng_part_number":"MNG Part No","oem_part_number":"OEM Part No",
                    "description_en":"Description (EN)","description_ar":"Description (AR)",
                    "qty":"Qty","vehicle_type":"Vehicle Type","vehicle_id":"Vehicle ID"
                }), use_container_width=True, hide_index=True, height=min(200, len(items)*38+50))

                # Print export
                if not items.empty:
                    buf = BytesIO()
                    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                        items.to_excel(writer, index=False, sheet_name=f"Brigade Approval")
                    buf.seek(0)
                    st.download_button(
                        f"🖨 Print / Export {row['approval_number']}",
                        data=buf,
                        file_name=f"{row['approval_number']}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                # Approval actions
                if row["is_outdated"]:
                    st.error("⚠️ This list is OUTDATED. Regenerate from RFQ Management before approving.")
                elif row["status"] == "Waiting Approval":
                    col_a, col_b = st.columns(2)
                    if col_a.button("✅ Approve", key=f"approve_{row['id']}", type="primary"):
                        conn = get_conn()
                        conn.execute("""
                            UPDATE brigade_approvals SET status='Approved', last_updated=? WHERE id=?
                        """, (datetime.now().isoformat(), row["id"]))
                        conn.commit()
                        conn.close()
                        st.success("✅ List Approved and Locked.")
                        st.rerun()
                    if col_b.button("↩ Return for Amendment", key=f"reject_{row['id']}"):
                        conn = get_conn()
                        conn.execute("""
                            UPDATE brigade_approvals SET status='Returned for Amendment', last_updated=? WHERE id=?
                        """, (datetime.now().isoformat(), row["id"]))
                        conn.commit()
                        conn.close()
                        st.warning("↩ List returned for amendment. Edit the RFQ list and regenerate.")
                        st.rerun()
                elif row["status"] == "Approved":
                    st.success("🔒 This list is **Approved and Locked**. No edits allowed.")
                elif row["status"] == "Returned for Amendment":
                    st.error("↩ Returned for Amendment — Edit RFQ List and regenerate.")

# ══════════════════════════════════════════════════════════════════════════════
# WORK ORDER VISIBILITY
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔍  Work Order Visibility":
    st.markdown('<div class="page-title">Work Order Visibility</div>', unsafe_allow_html=True)
    st.markdown('<div style="color:#8b949e;font-size:13px;padding-left:15px;margin-bottom:20px;">Part-level procurement status across all Work Orders · Auto-updated from RFQ</div>', unsafe_allow_html=True)

    conn = get_conn()
    wo_list = pd.read_sql("""
        SELECT w.wo_number, w.creation_date, w.brigade, w.vehicle_type, w.vehicle_id, w.status,
               COUNT(p.id) as total_parts,
               SUM(CASE WHEN p.procurement_status='Delivered in Full' THEN 1 ELSE 0 END) as delivered,
               SUM(CASE WHEN p.rfq_batch_number IS NOT NULL AND p.rfq_batch_number!='' THEN 1 ELSE 0 END) as in_rfq
        FROM work_orders w
        LEFT JOIN wo_parts p ON p.wo_number = w.wo_number
        GROUP BY w.wo_number ORDER BY w.creation_date DESC
    """, conn)
    conn.close()

    # Search
    search = st.text_input("🔍 Search Work Order", placeholder="WO-2026-...")
    if search:
        wo_list = wo_list[wo_list.wo_number.str.contains(search, case=False)]

    f1, f2 = st.columns(2)
    brig_filter = f1.selectbox("Brigade", ["All"] + sorted(wo_list["brigade"].unique().tolist()) if not wo_list.empty else ["All"])
    if brig_filter != "All":
        wo_list = wo_list[wo_list.brigade == brig_filter]

    st.markdown(f'<div class="section-hdr">{len(wo_list)} Work Orders</div>', unsafe_allow_html=True)

    for _, wo in wo_list.iterrows():
        pct = int((wo["delivered"] / wo["total_parts"] * 100)) if wo["total_parts"] > 0 else 0
        with st.expander(f"{wo['wo_number']} · {wo['brigade']} · {wo['vehicle_type']} · {wo['vehicle_id']} · {wo['total_parts']} parts · {pct}% delivered"):

            st.markdown(f"**Created:** {wo['creation_date']} &nbsp;|&nbsp; **Parts in RFQ:** {int(wo['in_rfq'])} / {int(wo['total_parts'])}")
            st.progress(pct / 100)

            conn = get_conn()
            parts = pd.read_sql("""
                SELECT mng_part_number, oem_part_number, description_en, required_qty,
                       procurement_status, expected_delivery_date, rfq_batch_number
                FROM wo_parts WHERE wo_number=? ORDER BY mng_part_number
            """, conn, params=(wo["wo_number"],))
            conn.close()

            status_colors = {
                "Procurement Needed":             "#f85149",
                "Initiated for Procurement":      "#58a6ff",
                "Under Quotation":                "#d29922",
                "Pending MNG Procurement Approval":"#d29922",
                "Purchase Order Sent – Pending Delivery":"#58a6ff",
                "Delivered Partially":            "#d29922",
                "Delivered in Full":              "#3fb950",
            }

            for _, p in parts.iterrows():
                pc1,pc2,pc3,pc4,pc5,pc6 = st.columns([1.3,1.3,1.8,0.7,2.2,1.3])
                pc1.markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px;color:#f0f6fc'>{p['mng_part_number']}</span>", unsafe_allow_html=True)
                pc2.markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px;color:#8b949e'>{p['oem_part_number']}</span>", unsafe_allow_html=True)
                pc3.markdown(f"<span style='font-size:12px'>{p['description_en']}</span>", unsafe_allow_html=True)
                pc4.markdown(f"<span style='font-family:IBM Plex Mono;font-weight:600;color:#3fb950'>{int(p['required_qty'])}</span>", unsafe_allow_html=True)
                color = status_colors.get(p['procurement_status'], '#8b949e')
                pc5.markdown(f"<span style='font-size:10px;color:{color};font-family:IBM Plex Mono'>{p['procurement_status']}</span>", unsafe_allow_html=True)
                rfq_display = p['rfq_batch_number'] if p['rfq_batch_number'] else "—"
                pc6.markdown(f"<span style='font-family:IBM Plex Mono;font-size:11px;color:#58a6ff'>{rfq_display}</span>", unsafe_allow_html=True)

