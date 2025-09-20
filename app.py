# app.py — DGCC Follow-up (single-file)
# Fixes added:
# - Date picker ALWAYS visible (disabled until "Has due date?" is checked)
# - Divider between Notes and Tasks, and between each Task row
# - "+" button to add more deliverable forms at top AND after each form
# - Collapsible deliverable cards with per-deliverable Excel download
# - Global Excel download for all deliverables + tasks

import sqlite3
import io
import datetime as dt
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
import streamlit as st

# ---------- Page ----------
st.set_page_config(page_title="DGCC Follow-up Manager", page_icon="🗂️", layout="wide")
st.title("DGCC Follow-up")

DB_PATH = Path("followup.db")
STATUSES = ["Not started", "In progress", "Blocked", "Done"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]


# ---------- DB helpers ----------
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
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
        )"""
    )
    cur.execute(
        """
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
        )"""
    )
    conn.commit()
    conn.close()


def insert_deliverable(**kw) -> int:
    kw.setdefault("start_date", dt.date.today().isoformat())
    kw.setdefault("last_update", dt.datetime.utcnow().isoformat())
    cols = [
        "unit", "name", "owner", "owner_email", "notes", "due_date",
        "status", "priority", "category", "tags", "expected_hours",
        "start_date", "last_update",
    ]
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO deliverables({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
        tuple(kw.get(c) for c in cols),
    )
    conn.commit()
    did = cur.lastrowid
    conn.close()
    return did


def insert_task(**kw) -> None:
    kw.setdefault("start_date", dt.date.today().isoformat())
    kw.setdefault("last_update", dt.datetime.utcnow().isoformat())
    cols = [
        "deliverable_id", "task", "owner", "notes", "due_date",
        "status", "priority", "tags", "expected_hours",
        "start_date", "last_update", "blocked_reason",
    ]
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO tasks({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
        tuple(kw.get(c) for c in cols),
    )
    conn.commit()
    conn.close()


def fetch_deliverables() -> List[Dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM deliverables
        ORDER BY COALESCE(due_date,'9999-12-31') ASC, priority DESC, id ASC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def fetch_tasks_for(deliverable_id: int) -> List[Dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM tasks
        WHERE deliverable_id=?
        ORDER BY COALESCE(due_date,'9999-12-31') ASC, priority DESC, id ASC
        """,
        (deliverable_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def fetch_tasks_flat() -> List[Dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT t.*, d.name AS deliverable_name, d.unit AS deliverable_unit
        FROM tasks t LEFT JOIN deliverables d ON d.id = t.deliverable_id
        ORDER BY COALESCE(t.due_date,'9999-12-31') ASC, t.priority DESC, t.id ASC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def delete_deliverable(deliverable_id: int):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE deliverable_id=?", (deliverable_id,))
    cur.execute("DELETE FROM deliverables WHERE id=?", (deliverable_id,))
    conn.commit()
    conn.close()


# ---------- Utils ----------
def _iso_date_or_none(enabled: bool, val):
    if not enabled or not val:
        return None
    if isinstance(val, dt.date):
        return val.isoformat()
    return None


def _download_excel_button(filename: str, sheets: dict[str, pd.DataFrame], label: str):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
    st.download_button(label, data=buf.getvalue(), file_name=filename)


def _task_line(task_row: Dict[str, Any]) -> str:
    """One-line, space-separated task summary."""
    fields = [
        task_row.get("task"),
        task_row.get("owner"),
        task_row.get("status"),
        task_row.get("priority"),
        task_row.get("due_date"),
        (str(task_row["expected_hours"]) if task_row.get("expected_hours") else None),
        task_row.get("tags"),
        task_row.get("blocked_reason"),
        task_row.get("notes"),
    ]
    return " ".join(str(x).strip() for x in fields if x not in (None, "", "None"))


# ---------- App start ----------
init_db()

with st.sidebar:
    st.header("Options")
    due_window = st.number_input("Due soon window (days)", min_value=0, value=3, step=1)
    st.caption("Per-deliverable and global Excel downloads are available below.")

# How many deliverable forms to show this session
if "form_count" not in st.session_state:
    st.session_state.form_count = 1

st.subheader("Create deliverable & 5 tasks each")

# "+" button at the top
if st.button("➕ Add another deliverable form", help="Add another deliverable + 5 tasks", key="add_top"):
    st.session_state.form_count += 1

saved_any = False

for form_idx in range(st.session_state.form_count):
    st.markdown(f"### Deliverable form {form_idx + 1}")
    with st.form(f"create_{form_idx}", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            d_unit = st.text_input("Unit", placeholder="DGCC", key=f"unit_{form_idx}")
            d_name = st.text_input("Deliverable title*", placeholder="e.g., Policy rollout v1", key=f"name_{form_idx}")
            d_owner = st.text_input("Owner", placeholder="Nora", key=f"owner_{form_idx}")
            d_email = st.text_input("Owner email", key=f"email_{form_idx}")
        with c2:
            d_status = st.selectbox("Status", STATUSES, index=0, key=f"status_{form_idx}")
            d_priority = st.selectbox("Priority", PRIORITIES, index=1, key=f"priority_{form_idx}")
            d_category = st.text_input("Category", placeholder="Audit / Policy / System", key=f"cat_{form_idx}")
            d_due_enabled = st.checkbox("Has due date?", key=f"due_on_{form_idx}")
        with c3:
            # Always show date box; enable only if due is checked
            d_due = st.date_input("Due date", value=dt.date.today(), key=f"due_{form_idx}", disabled=not d_due_enabled)
            d_tags = st.text_input("Tags (comma-separated)", key=f"tags_{form_idx}")
            d_hours = st.number_input("Expected hours", min_value=0.0, step=0.5, key=f"hrs_{form_idx}")
        d_notes = st.text_area("Notes", height=90, key=f"notes_{form_idx}")

        # Divider + caption before the task section
        st.divider()
        st.markdown("**Tasks (5 max)**  \n_(No unit per task; each task is shown later as a single space-separated line.)_")

        task_rows = []
        for i in range(1, 6):
            # 4 columns: title/owner | status/priority | due | hours/tags/blocked
            t1, t2, t3, t4 = st.columns([2, 1.2, 1.3, 1.7], gap="small")
            with t1:
                t_title = st.text_input(f"Task {i} title", key=f"t{form_idx}_{i}_title")
                t_owner = st.text_input(f"Owner {i}", key=f"t{form_idx}_{i}_owner")
            with t2:
                t_status = st.selectbox(f"Status {i}", STATUSES, index=0, key=f"t{form_idx}_{i}_status")
                t_priority = st.selectbox(f"Priority {i}", PRIORITIES, index=0, key=f"t{form_idx}_{i}_prio")
            with t3:
                t_due_enabled = st.checkbox("Has due date?", key=f"t{form_idx}_{i}_due_on")
                t_due = st.date_input("Due date", value=dt.date.today(), key=f"t{form_idx}_{i}_due", disabled=not t_due_enabled)
            with t4:
                t_hours = st.number_input(f"Hours {i}", min_value=0.0, step=0.5, key=f"t{form_idx}_{i}_hrs")
                t_tags = st.text_input(f"Tags {i}", key=f"t{form_idx}_{i}_tags")
                t_blocked = st.text_input(f"Blocked reason {i}", key=f"t{form_idx}_{i}_blk")
            t_notes = st.text_area(f"Notes {i}", key=f"t{form_idx}_{i}_notes")

            task_rows.append(
                dict(
                    task=(t_title or "").strip(),
                    owner=t_owner or None,
                    status=t_status,
                    priority=t_priority,
                    due_date=_iso_date_or_none(t_due_enabled, t_due),
                    expected_hours=t_hours if t_hours else None,
                    tags=t_tags or None,
                    blocked_reason=t_blocked or None,
                    notes=t_notes or None,
                )
            )

            # ——— divider between tasks (except after the last one)
            if i < 5:
                st.markdown("<hr style='margin:8px 0; opacity:0.35;'/>", unsafe_allow_html=True)

        submitted = st.form_submit_button("💾 Save this deliverable", type="primary")
        if submitted:
            if not d_name.strip():
                st.error("Deliverable title is required.")
            else:
                did = insert_deliverable(
                    unit=d_unit or None,
                    name=d_name.strip(),
                    owner=d_owner or None,
                    owner_email=d_email or None,
                    notes=d_notes or None,
                    due_date=_iso_date_or_none(d_due_enabled, d_due),
                    status=d_status,
                    priority=d_priority,
                    category=d_category or None,
                    tags=d_tags or None,
                    expected_hours=d_hours if d_hours else None,
                )
                created = 0
                for tr in task_rows:
                    if tr["task"]:
                        insert_task(deliverable_id=did, **tr)
                        created += 1
                st.success(f"Saved deliverable #{did} with {created} task(s).")
                saved_any = True

    # "+" button again after each form (easier to add more)
    if st.button("➕ Add another deliverable form", key=f"add_after_{form_idx}"):
        st.session_state.form_count += 1
        st.experimental_rerun()

if saved_any:
    st.balloons()

# ---------- Display ----------
st.subheader("Deliverables (click the ▸ arrow to expand)")

dels = fetch_deliverables()
if dels:
    for d in dels:
        tasks = fetch_tasks_for(d["id"])
        title = f'#{d["id"]} — {d["name"]}'
        if d.get("unit"):
            title += f'  ({d["unit"]})'

        with st.expander(title, expanded=False):
            # Top actions row: Download + Delete
            cdl, cdel, _ = st.columns([2, 1.2, 6])
            df_del = pd.DataFrame([d])
            df_tasks = pd.DataFrame(tasks) if tasks else pd.DataFrame(
                columns=[
                    "id","deliverable_id","task","owner","status","priority","due_date",
                    "expected_hours","tags","blocked_reason","notes","start_date","last_update"
                ])
            with cdl:
                _download_excel_button(
                    f"deliverable_{d['id']}.xlsx",
                    {"Deliverable": df_del, "Tasks": df_tasks},
                    "⬇️ Download this deliverable (.xlsx)",
                )
            with cdel:
                if st.button(f"🗑️ Delete #{d['id']}", key=f"del_{d['id']}"):
                    delete_deliverable(d["id"])
                    st.warning("Deleted. Please refresh.")
            st.markdown("---")

            # Summary line
            info_parts = []
            for label, key in [("Status", "status"), ("Priority", "priority"),
                               ("Due", "due_date"), ("Owner", "owner"),
                               ("Email", "owner_email")]:
                if d.get(key):
                    info_parts.append(f"**{label}:** {d[key]}")
            st.markdown(" • ".join(info_parts) if info_parts else "_No meta info_")

            # Tasks as space-separated lines
            if tasks:
                st.markdown("**Tasks** (each line is fields joined by spaces):")
                lines = [_task_line(t) for t in tasks]
                st.code("\n".join(lines), language="text")
            else:
                st.info("No tasks yet for this deliverable.")

    # Global table + export
    st.markdown("---")
    st.subheader("All deliverables (table)")
    df_all = pd.DataFrame(dels)
    if "due_date" in df_all:
        def flag(due):
            try:
                if not due: return ""
                delta = (dt.date.fromisoformat(due) - dt.date.today()).days
                return "⚠️" if 0 <= delta <= due_window else ""
            except Exception:
                return ""
        df_all["due_soon"] = df_all["due_date"].map(flag)
        cols = [
            "due_soon","id","unit","name","owner","owner_email","status","priority",
            "category","tags","expected_hours","start_date","due_date","last_update","notes"
        ]
        cols = [c for c in cols if c in df_all.columns]
    else:
        cols = list(df_all.columns)

    st.dataframe(df_all[cols], use_container_width=True)
    _download_excel_button(
        "deliverables.xlsx",
        {"Deliverables": df_all, "Tasks": pd.DataFrame(fetch_tasks_flat())},
        "⬇️ Download ALL deliverables (.xlsx)",
    )
else:
    st.info("No deliverables yet — add one above, then the ▸ arrow will appear for each.")
