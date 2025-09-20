# app.py — DGCC Follow-up (clean single-file version)
import sqlite3
import json
import io
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="DGCC Follow-up (Clean)", page_icon="🗂️", layout="wide")
st.title("DGCC Follow-up (Clean)")

DB_PATH = Path("followup.db")
STATUSES = ["Not started", "In progress", "Blocked", "Done"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]

# ---------- DB helpers ----------
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _connect(); cur = conn.cursor()
    # Base tables
    cur.execute("""
    CREATE TABLE IF NOT EXISTS deliverables(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unit TEXT,
        name TEXT NOT NULL,
        owner TEXT,
        owner_email TEXT,
        notes TEXT,
        due_date TEXT,
        status TEXT,
        priority TEXT,
        category TEXT,
        tags TEXT,
        expected_hours REAL,
        start_date TEXT,
        last_update TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        deliverable_id INTEGER,
        task TEXT NOT NULL,
        owner TEXT,
        notes TEXT,
        due_date TEXT,
        status TEXT,
        priority TEXT,
        tags TEXT,
        expected_hours REAL,
        start_date TEXT,
        last_update TEXT,
        blocked_reason TEXT,
        FOREIGN KEY(deliverable_id) REFERENCES deliverables(id) ON DELETE CASCADE
    )""")
    conn.commit(); conn.close()

def insert_deliverable(**kw):
    kw.setdefault("start_date", dt.date.today().isoformat())
    kw.setdefault("last_update", dt.datetime.utcnow().isoformat())
    cols = ["unit","name","owner","owner_email","notes","due_date","status",
            "priority","category","tags","expected_hours","start_date","last_update"]
    conn = _connect(); cur = conn.cursor()
    cur.execute(f"""
        INSERT INTO deliverables({",".join(cols)})
        VALUES ({",".join("?" for _ in cols)})
    """, tuple(kw.get(c) for c in cols))
    conn.commit(); did = cur.lastrowid; conn.close()
    return did

def insert_task(**kw):
    kw.setdefault("start_date", dt.date.today().isoformat())
    kw.setdefault("last_update", dt.datetime.utcnow().isoformat())
    cols = ["deliverable_id","task","owner","notes","due_date","status",
            "priority","tags","expected_hours","start_date","last_update","blocked_reason"]
    conn = _connect(); cur = conn.cursor()
    cur.execute(f"""
        INSERT INTO tasks({",".join(cols)})
        VALUES ({",".join("?" for _ in cols)})
    """, tuple(kw.get(c) for c in cols))
    conn.commit(); conn.close()

def fetch_deliverables():
    conn = _connect(); cur = conn.cursor()
    cur.execute("""
      SELECT * FROM deliverables
      ORDER BY COALESCE(due_date,'9999-12-31') ASC, priority DESC, id ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close(); return rows

def fetch_tasks_flat():
    conn = _connect(); cur = conn.cursor()
    cur.execute("""
      SELECT t.*, d.name AS deliverable_name
      FROM tasks t LEFT JOIN deliverables d ON d.id = t.deliverable_id
      ORDER BY COALESCE(t.due_date,'9999-12-31') ASC, t.priority DESC, t.id ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close(); return rows

def delete_deliverable(deliverable_id: int):
    conn = _connect(); cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE deliverable_id=?", (deliverable_id,))
    cur.execute("DELETE FROM deliverables WHERE id=?", (deliverable_id,))
    conn.commit(); conn.close()

# ---------- Utils ----------
def _iso_date_or_none(enabled: bool, val):
    if not enabled or not val: return None
    if isinstance(val, dt.date): return val.isoformat()
    return None

def _download_excel_button(filename: str, sheets: dict[str, pd.DataFrame], label: str):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
    st.download_button(label, data=buf.getvalue(), file_name=filename)

# ---------- App ----------
init_db()

with st.sidebar:
    st.header("Options")
    due_window = st.number_input("Due soon window (days)", min_value=0, value=3, step=1)

st.subheader("Create deliverable & tasks")
with st.form("create", clear_on_submit=True):
    c1,c2,c3 = st.columns(3)
    with c1:
        d_unit = st.text_input("Unit", placeholder="DGCC")
        d_name = st.text_input("Deliverable title*", placeholder="e.g., Policy rollout v1")
        d_owner = st.text_input("Owner", placeholder="Nora")
        d_email = st.text_input("Owner email")
    with c2:
        d_status = st.selectbox("Status", STATUSES, index=0)
        d_priority = st.selectbox("Priority", PRIORITIES, index=1)
        d_category = st.text_input("Category", placeholder="Audit / Policy / System")
        d_due_enabled = st.checkbox("Has due date?")
        d_due = st.date_input("Due date", value=None, disabled=not d_due_enabled)
    with c3:
        d_tags = st.text_input("Tags (comma-separated)")
        d_hours = st.number_input("Expected hours", min_value=0.0, step=0.5)
        d_notes = st.text_area("Notes", height=90)

    st.markdown("**Optional tasks (add any titles you want; empty rows are ignored):**")
    task_rows = []
    for i in range(1, 6):
        t1,t2,t3,t4 = st.columns([2,1,1,1])
        with t1:
            t_title = st.text_input(f"Task {i} title", key=f"t{i}_title")
            t_owner = st.text_input(f"Owner {i}", key=f"t{i}_owner")
        with t2:
            t_status = st.selectbox(f"Status {i}", STATUSES, index=0, key=f"t{i}_status")
            t_priority = st.selectbox(f"Priority {i}", PRIORITIES, index=0, key=f"t{i}_prio")
        with t3:
            t_due_enabled = st.checkbox(f"Due {i}?", key=f"t{i}_due_on")
            t_due = st.date_input(f"Due {i}", value=None, disabled=not t_due_enabled, key=f"t{i}_due")
        with t4:
            t_hours = st.number_input(f"Hours {i}", min_value=0.0, step=0.5, key=f"t{i}_hrs")
            t_tags = st.text_input(f"Tags {i}", key=f"t{i}_tags")
            t_blocked = st.text_input(f"Blocked reason {i}", key=f"t{i}_blk")
        t_notes = st.text_area(f"Notes {i}", key=f"t{i}_notes")
        task_rows.append(dict(
            task=(t_title or "").strip(),
            owner=t_owner or None, status=t_status, priority=t_priority,
            due_date=_iso_date_or_none(t_due_enabled, t_due),
            expected_hours=t_hours if t_hours else None,
            tags=t_tags or None, blocked_reason=t_blocked or None,
            notes=t_notes or None,
        ))

    if st.form_submit_button("➕ Save", type="primary"):
        if not d_name.strip():
            st.error("Deliverable title is required.")
        else:
            did = insert_deliverable(
                unit=d_unit or None, name=d_name.strip(), owner=d_owner or None, owner_email=d_email or None,
                notes=d_notes or None, due_date=_iso_date_or_none(d_due_enabled, d_due),
                status=d_status, priority=d_priority, category=d_category or None,
                tags=d_tags or None, expected_hours=d_hours if d_hours else None
            )
            created = 0
            for tr in task_rows:
                if tr["task"]:
                    insert_task(deliverable_id=did, **tr)
                    created += 1
            st.success(f"Saved deliverable #{did} with {created} task(s).")

# ---------- Tables ----------
st.subheader("Deliverables")
dels = fetch_deliverables()
if dels:
    df_d = pd.DataFrame(dels)
    if "due_date" in df_d:
        def flag(d):
            try:
                if not d: return ""
                delta = (dt.date.fromisoformat(d) - dt.date.today()).days
                return "⚠️" if 0 <= delta <= due_window else ""
            except Exception:
                return ""
        df_d["due_soon"] = df_d["due_date"].map(flag)
        cols = ["due_soon","id","unit","name","owner","owner_email","status",
                "priority","category","tags","expected_hours","start_date","due_date","last_update","notes"]
    else:
        cols = list(df_d.columns)
    st.dataframe(df_d[cols], use_container_width=True)
    _download_excel_button("deliverables.xlsx", {"Deliverables": df_d}, "Download deliverables.xlsx")
else:
    st.info("No deliverables yet.")

st.subheader("Tasks")
tasks = fetch_tasks_flat()
if tasks:
    df_t = pd.DataFrame(tasks)
    cols_t = ["id","deliverable_id","deliverable_name","task","owner","status","priority",
              "tags","expected_hours","blocked_reason","start_date","due_date","last_update","notes"]
    cols_t = [c for c in cols_t if c in df_t.columns]
    st.dataframe(df_t[cols_t], use_container_width=True)
    _download_excel_button("tasks.xlsx", {"Tasks": df_t}, "Download tasks.xlsx")
else:
    st.info("No tasks yet.")

# ---------- Danger zone ----------
with st.expander("Danger zone"):
    if dels:
        choices = {f'#{d["id"]} — {d["name"]}': d["id"] for d in dels}
        choice = st.selectbox("Delete deliverable (and its tasks)", list(choices))
        if st.button("Delete selected"):
            delete_deliverable(choices[choice])
            st.warning("Deleted.")
