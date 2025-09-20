# app.py — DGCC Follow-up — Clean (with persistence + working due-dates)

from __future__ import annotations
import io, json, sqlite3, uuid
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# ───────────────────────────── Page + CSS ─────────────────────────────
st.set_page_config(page_title="DGCC Follow-up Manager", layout="wide")
st.title("DGCC Follow-up Manager")

st.markdown(
    """
<style>
.block-container {max-width: 1100px;}
[data-testid="stForm"] .stTextInput, 
[data-testid="stForm"] .stTextArea, 
[data-testid="stForm"] .stSelectbox,
[data-testid="stForm"] .stNumberInput,
[data-testid="stForm"] .stDateInput {
  margin-bottom: .35rem;
}
.stExpander {border: 1px solid #e5e7eb; border-radius: 12px;}
</style>
""",
    unsafe_allow_html=True,
)

# ───────────────────────────── Fixed choices ──────────────────────────
if "vars" not in st.session_state:
    st.session_state["vars"] = {
        "status":   ["Not started", "In progress", "Blocked", "Done"],
        "priority": ["Low", "Medium", "High"],
        "owners":   [],  # fill with names if you want a dropdown later
    }

# ───────────────────────────── Persistence (SQLite) ───────────────────
DB_PATH = Path("dgcc_followup.db")

def db_init() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS deliverables (
            id TEXT PRIMARY KEY,
            title TEXT,
            owner TEXT,
            unit TEXT,
            term TEXT,
            created_at TEXT,
            notes TEXT,
            tasks_json TEXT
        )
        """
    )
    conn.commit()
    conn.close()

def db_upsert_deliverable(d: Dict) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO deliverables
        (id, title, owner, unit, term, created_at, notes, tasks_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            d["id"],
            d.get("title", ""),
            d.get("owner", ""),
            d.get("unit", ""),
            d.get("term", ""),
            d.get("created_at", ""),
            d.get("notes", ""),
            json.dumps(d.get("tasks", []), default=str),
        ),
    )
    conn.commit()
    conn.close()

def db_delete_deliverable(deliv_id: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM deliverables WHERE id = ?", (deliv_id,))
    conn.commit()
    conn.close()

def db_read_all() -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, owner, unit, term, created_at, notes, tasks_json "
        "FROM deliverables ORDER BY datetime(created_at) DESC"
    )
    rows = cur.fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "title": r[1],
                "owner": r[2],
                "unit": r[3],
                "term": r[4],
                "created_at": r[5],
                "notes": r[6],
                "tasks": json.loads(r[7] or "[]"),
            }
        )
    return out

db_init()
if "deliverables" not in st.session_state:
    st.session_state["deliverables"] = db_read_all()

# ───────────────────────────── Utilities ──────────────────────────────
def generate_id() -> str:
    return uuid.uuid4().hex[:10]

def confirm_modal(prompt: str, state_key: str, match_id: str | None = None) -> bool:
    """
    Simple confirm dialog using st.modal. If match_id is given, modal opens only
    when st.session_state[state_key] == match_id.
    """
    if match_id is not None and st.session_state.get(state_key) != match_id:
        return False
    if st.session_state.get(state_key):
        with st.modal("Confirm action"):
            st.warning(prompt)
            c1, c2 = st.columns(2)
            yes = c1.button("Yes, proceed")
            no = c2.button("Cancel")
            if yes:
                st.session_state[state_key] = None if match_id is not None else False
                return True
            if no:
                st.session_state[state_key] = None if match_id is not None else False
                st.rerun()
    return False

def build_task(
    idx: int,
    title: str,
    status: str,
    hours: Optional[float],
    has_due: bool,
    due: Optional[date],
    notes: str,
    priority: str,
) -> Optional[Dict]:
    title = (title or "").strip()
    if not title:
        return None
    return {
        "row": idx,
        "title": title,
        "status": status,
        "priority": priority,
        "hours": float(hours) if hours not in (None, "") else None,
        "due_date": due.isoformat() if (has_due and due) else None,
        "notes": (notes or "").strip(),
    }

def task_row(idx: int) -> Optional[Dict]:
    """One task row (with working due-date toggle)."""
    vs = st.session_state["vars"]
    st.markdown(f"**Task {idx}**")
    t_title = st.text_input("Title", key=f"t{idx}_title")
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    with c1:
        t_status = st.selectbox("Status", vs["status"], key=f"t{idx}_status")
    with c2:
        t_priority = st.selectbox("Priority", vs["priority"], key=f"t{idx}_priority")
    with c3:
        t_has_due = st.checkbox("Has due date?", key=f"t{idx}_has_due")
        default_due = st.session_state.get(f"t{idx}_due", date.today())
        # Date input is enabled only if checkbox is checked
        t_due = st.date_input("Due date", value=default_due, disabled=not t_has_due, key=f"t{idx}_due")
    with c4:
        t_hours = st.number_input("Hours", min_value=0.0, step=0.5, key=f"t{idx}_hours")
    t_notes = st.text_area("Notes", height=60, key=f"t{idx}_notes")

    return build_task(idx, t_title, t_status, t_hours, t_has_due, t_due, t_notes, t_priority)

def collect_tasks(n: int = 5) -> List[Dict]:
    out: List[Dict] = []
    for i in range(1, n + 1):
        t = task_row(i)
        if t:
            out.append(t)
    return out

def filter_deliverables(items: List[Dict], term: str, owner: str, query: str) -> List[Dict]:
    term = (term or "").strip().lower()
    owner = (owner or "").strip().lower()
    query = (query or "").strip().lower()
    out = []
    for d in items:
        if term and term not in (d.get("term", "").lower()):
            continue
        if owner and owner not in (d.get("owner", "").lower()):
            continue
        hay = " ".join([d.get("title", ""), d.get("unit", ""), d.get("notes", "")]).lower()
        if query and query not in hay:
            continue
        out.append(d)
    return out

def paginate(items: List[Dict], page: int, per_page: int) -> Tuple[List[Dict], int]:
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], total

# ───────────────────────────── Exports ────────────────────────────────
def build_global_tables(items: List[Dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    d_rows, t_rows = [], []
    for d in items:
        d_rows.append(
            {
                "id": d["id"],
                "title": d.get("title", ""),
                "owner": d.get("owner", ""),
                "unit": d.get("unit", ""),
                "term": d.get("term", ""),
                "created_at": d.get("created_at", ""),
                "notes": d.get("notes", ""),
            }
        )
        for t in d.get("tasks", []) or []:
            t_rows.append(
                {
                    "deliverable_id": d["id"],
                    "deliverable_title": d.get("title", ""),
                    "row": t.get("row"),
                    "title": t.get("title"),
                    "status": t.get("status"),
                    "priority": t.get("priority"),
                    "hours": t.get("hours"),
                    "due_date": t.get("due_date"),
                    "notes": t.get("notes"),
                }
            )
    df_deliv = pd.DataFrame(d_rows)
    df_tasks = pd.DataFrame(t_rows)
    df_flat = df_tasks.copy() if len(df_tasks) else pd.DataFrame(
        columns=["deliverable_id","deliverable_title","row","title","status","priority","hours","due_date","notes"]
    )
    return df_deliv, df_tasks, df_flat

def export_filtered_csv(items: List[Dict]) -> bytes:
    _, _, df_flat = build_global_tables(items)
    buff = io.StringIO()
    df_flat.to_csv(buff, index=False)
    return buff.getvalue().encode("utf-8")

def export_filtered_excel(items: List[Dict]) -> bytes:
    df_deliv, df_tasks, df_flat = build_global_tables(items)
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="xlsxwriter") as w:
        df_deliv.to_excel(w, index=False, sheet_name="deliverables")
        df_tasks.to_excel(w, index=False, sheet_name="tasks")
        df_flat.to_excel(w, index=False, sheet_name="flattened")
    return buff.getvalue()

def export_summary_csv_one(d: Dict) -> bytes:
    """Per-deliverable CSV (tasks)."""
    df = pd.DataFrame(d.get("tasks", []) or [])
    buff = io.StringIO()
    df.to_csv(buff, index=False)
    return buff.getvalue().encode("utf-8")

def export_full_xlsx_one(d: Dict) -> bytes:
    """Per-deliverable Excel: deliverable + tasks + flattened."""
    df_deliv = pd.DataFrame([{
        "id": d["id"], "title": d.get("title",""), "owner": d.get("owner",""),
        "unit": d.get("unit",""), "term": d.get("term",""),
        "created_at": d.get("created_at",""), "notes": d.get("notes","")
    }])
    df_tasks = pd.DataFrame(d.get("tasks", []) or [])
    df_flat = df_tasks.copy()
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="xlsxwriter") as w:
        df_deliv.to_excel(w, index=False, sheet_name="deliverable")
        df_tasks.to_excel(w, index=False, sheet_name="tasks")
        df_flat.to_excel(w, index=False, sheet_name="flattened")
    return buff.getvalue()

# ───────────────────────────── Create form ────────────────────────────
def create_deliverable_form() -> None:
    with st.form("new_deliverable", clear_on_submit=True):
        st.subheader("Create deliverable")

        d_title = st.text_input("Deliverable title *")
        c0, c1, c2, c3 = st.columns([1,1,1,2])
        with c0:
            d_owner = st.text_input("Owner")
        with c1:
            d_unit = st.text_input("Unit")
        with c2:
            d_term = st.text_input("Term", help="e.g., 2025-1 or Fall 2025")
        with c3:
            d_notes = st.text_area("Deliverable notes", height=80)

        st.markdown("### Tasks (up to 5)")
        tasks = collect_tasks(5)

        submitted = st.form_submit_button("Save deliverable")
        if submitted:
            if not d_title.strip():
                st.error("Please enter a deliverable title.")
                st.stop()

            new_deliv = {
                "id": generate_id(),
                "title": d_title.strip(),
                "owner": d_owner.strip(),
                "unit": d_unit.strip(),
                "term": d_term.strip(),
                "notes": d_notes.strip(),
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                "tasks": tasks,
            }
            # Persist + keep in session
            db_upsert_deliverable(new_deliv)
            st.session_state["deliverables"].insert(0, new_deliv)

            # Reset filters and jump to first page so user sees it
            st.session_state["page"] = 1
            st.success("Deliverable added.")
            st.rerun()

# ───────────────────────────── Edit modal ─────────────────────────────
def edit_deliverable_modal(deliv: Dict) -> None:
    with st.modal(f"Edit: {deliv.get('title','')}"):
        d_title = st.text_input("Deliverable title *", value=deliv.get("title",""))
        c0, c1, c2, c3 = st.columns([1,1,1,2])
        with c0:
            d_owner = st.text_input("Owner", value=deliv.get("owner",""))
        with c1:
            d_unit = st.text_input("Unit", value=deliv.get("unit",""))
        with c2:
            d_term = st.text_input("Term", value=deliv.get("term",""))
        with c3:
            d_notes = st.text_area("Deliverable notes", value=deliv.get("notes",""), height=80)

        st.markdown("### Tasks (up to 5)")
        # Pre-fill 5 rows (existing first, then blanks)
        existing = deliv.get("tasks", []) or []
        for i in range(1, 6):
            if i <= len(existing):
                t = existing[i-1]
                st.session_state[f"t{i}_title"] = t.get("title","")
                st.session_state[f"t{i}_status"] = t.get("status", st.session_state["vars"]["status"][0])
                st.session_state[f"t{i}_priority"] = t.get("priority", st.session_state["vars"]["priority"][0])
                st.session_state[f"t{i}_hours"] = float(t["hours"]) if t.get("hours") is not None else 0.0
                has_due = t.get("due_date") is not None
                st.session_state[f"t{i}_has_due"] = has_due
                st.session_state[f"t{i}_due"] = date.fromisoformat(t["due_date"]) if has_due else date.today()
                st.session_state[f"t{i}_notes"] = t.get("notes","")
            task_row(i)  # reuses the widget keys we just set

        if st.button("Save changes"):
            if not d_title.strip():
                st.error("Please enter a deliverable title.")
                st.stop()
            tasks = collect_tasks(5)
            updated = {
                "id": deliv["id"],
                "title": d_title.strip(),
                "owner": d_owner.strip(),
                "unit": d_unit.strip(),
                "term": d_term.strip(),
                "notes": d_notes.strip(),
                "created_at": deliv.get("created_at") or datetime.utcnow().isoformat(timespec="seconds"),
                "tasks": tasks,
            }
            db_upsert_deliverable(updated)
            # update in session
            for i, x in enumerate(st.session_state["deliverables"]):
                if x["id"] == deliv["id"]:
                    st.session_state["deliverables"][i] = updated
                    break
            st.success("Deliverable updated.")
            st.rerun()

# ───────────────────────────── Render cards ───────────────────────────
def show_deliverable_card(deliv: Dict) -> None:
    with st.expander(f"{deliv['title']} — {deliv.get('owner','')}", expanded=False):
        st.caption(f"ID: `{deliv['id']}` • created {deliv.get('created_at','')}")
        if deliv.get("notes"):
            st.markdown(f"**Notes:** {deliv['notes']}")

        tasks = deliv.get("tasks", []) or []
        if not tasks:
            st.info("No tasks added.")
        else:
            df = pd.DataFrame(tasks)
            cols = ["row","title","status","priority","hours","due_date","notes"]
            df = df[[c for c in cols if c in df.columns]]
            st.dataframe(df.rename(columns={"row":"#", "due_date":"Due"}), use_container_width=True, hide_index=True)

        c1, c2, c3, c4 = st.columns([1,1,1,1])
        with c1:
            st.download_button(
                "Summary (CSV)",
                data=export_summary_csv_one(deliv),
                file_name=f"{deliv['title']}_summary.csv",
                mime="text/csv",
            )
        with c2:
            st.download_button(
                "Full workbook (Excel)",
                data=export_full_xlsx_one(deliv),
                file_name=f"{deliv['title']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with c3:
            if st.button("Edit", key=f"edit_{deliv['id']}"):
                st.session_state["edit_id"] = deliv["id"]
        with c4:
            if st.button("Delete", key=f"del_{deliv['id']}"):
                st.session_state["ask_delete_one"] = deliv["id"]

        if confirm_modal(
            f"Delete deliverable '{deliv['title']}'? This cannot be undone.",
            "ask_delete_one",
            match_id=deliv["id"],
        ):
            db_delete_deliverable(deliv["id"])
            st.session_state["deliverables"] = [x for x in st.session_state["deliverables"] if x["id"] != deliv["id"]]
            st.success("Deliverable deleted.")
            st.rerun()

# ───────────────────────────── UI: Create form (collapsible) ─────────
with st.expander("Create deliverable", expanded=False):
    create_deliverable_form()

# ───────────────────────────── Filters + Pagination + Global Export ──
st.subheader("Deliverables")

items_all = st.session_state["deliverables"]
terms = sorted({(d.get("term") or "").strip() for d in items_all if d.get("term")})
owners = sorted({(d.get("owner") or "").strip() for d in items_all if d.get("owner")})

fc1, fc2, fc3, fc4 = st.columns([1, 1, 2, 1])
with fc1:
    f_term = st.selectbox("Term", [""] + terms, index=0)
with fc2:
    f_owner = st.selectbox("Owner", [""] + owners, index=0)
with fc3:
    f_query = st.text_input("Search", help="title / unit / notes")
with fc4:
    per_page = st.selectbox("Per page", [5, 10, 20, 50], index=1)

filtered = filter_deliverables(items_all, f_term, f_owner, f_query)

dl1, dl2, _ = st.columns([1, 1, 6])
with dl1:
    st.download_button(
        "Download filtered — CSV",
        data=export_filtered_csv(filtered),
        file_name="deliverables_filtered_summary.csv",
        mime="text/csv",
    )
with dl2:
    st.download_button(
        "Download filtered — Excel",
        data=export_filtered_excel(filtered),
        file_name="deliverables_filtered.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

if "page" not in st.session_state:
    st.session_state["page"] = 1
pages = max(1, (len(filtered) - 1) // per_page + 1)
st.session_state["page"] = min(st.session_state["page"], pages)

pc1, pc2, pc3 = st.columns([1, 1, 6])
with pc1:
    if st.button("Prev", disabled=st.session_state["page"] <= 1):
        st.session_state["page"] -= 1
with pc2:
    if st.button("Next", disabled=st.session_state["page"] >= pages):
        st.session_state["page"] += 1
with pc3:
    st.caption(f"Page {st.session_state['page']} / {pages} • {len(filtered)} match(es)")

page_items, _ = paginate(filtered, st.session_state["page"], per_page)

# Optional edit modal open
if st.session_state.get("edit_id"):
    ed = next((d for d in items_all if d["id"] == st.session_state["edit_id"]), None)
    if ed:
        edit_deliverable_modal(ed)

if not page_items:
    st.info("No deliverables match the current filters.")
else:
    for d in page_items:
        show_deliverable_card(d)
