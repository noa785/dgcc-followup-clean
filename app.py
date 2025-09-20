# 📝 DGCC Follow-up — Clean (compact + filterable + editable)
# Single-file Streamlit app

from __future__ import annotations

from datetime import datetime, date
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------------
# Page config + compact CSS
# -----------------------------------------------------------------------------
st.set_page_config(page_title="DGCC Follow-up Manager", layout="wide")

st.markdown("""
<style>
/* Narrower content & subtle tightening */
.block-container {max-width: 1100px;}
[data-testid="stForm"] .stTextInput, 
[data-testid="stForm"] .stTextArea, 
[data-testid="stForm"] .stSelectbox,
[data-testid="stForm"] .stNumberInput,
[data-testid="stForm"] .stDateInput {
  margin-bottom: .35rem;
}
.stExpander {border: 1px solid #e5e7eb; border-radius: 12px;}
/* compact buttons in download bar */
.dl-row button { width: 100%; }
</style>
""", unsafe_allow_html=True)

st.title("DGCC Follow-up Manager")

# -----------------------------------------------------------------------------
# Session state (simple in-memory storage)
# -----------------------------------------------------------------------------
if "deliverables" not in st.session_state:
    st.session_state["deliverables"]: List[Dict] = []

if "page" not in st.session_state:
    st.session_state["page"] = 1


# -----------------------------------------------------------------------------
# Helpers: id, task builder, exports, filter, paginate, confirm modal
# -----------------------------------------------------------------------------
def generate_id() -> str:
    return datetime.utcnow().strftime("%y%m%d%H%M%S%f")[-10:]


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
    """
    Returns a task dict if title is not empty, otherwise None (skip row).
    """
    title = (title or "").strip()
    if not title:
        return None
    return {
        "row": idx,
        "title": title,
        "status": status,
        "priority": priority,
        "hours": float(hours) if hours not in (None, "") else None,
        "due_date": due if has_due else None,
        "notes": (notes or "").strip(),
    }


def export_summary_csv(deliv: Dict) -> bytes:
    """
    CSV of tasks for a single deliverable (summary).
    """
    tasks = deliv.get("tasks", []) or []
    if not tasks:
        df = pd.DataFrame(columns=["#", "Task", "Status", "Priority", "Hours", "Due", "Notes"])
    else:
        df = pd.DataFrame(tasks)
        rename = {"row": "#", "title": "Task", "due_date": "Due"}
        cols = ["row", "title", "status", "priority", "hours", "due_date", "notes"]
        df = df[[c for c in cols if c in df.columns]].rename(columns=rename)
    return df.to_csv(index=False).encode("utf-8")


def export_full_xlsx(deliv: Dict) -> bytes:
    """
    Excel workbook:
      - 'Deliverable' sheet (one row)
      - 'Tasks' sheet
      - 'Summary' sheet (same as CSV)
    """
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as xw:
        # Deliverable info
        d_row = {
            "ID": deliv.get("id",""),
            "Title": deliv.get("title",""),
            "Owner": deliv.get("owner",""),
            "Unit": deliv.get("unit",""),
            "Term": deliv.get("term",""),
            "Notes": deliv.get("notes",""),
            "Created": deliv.get("created_at",""),
        }
        pd.DataFrame([d_row]).to_excel(xw, index=False, sheet_name="Deliverable")

        # Tasks
        tasks = deliv.get("tasks", []) or []
        if not tasks:
            tdf = pd.DataFrame(columns=["#", "Task", "Status", "Priority", "Hours", "Due", "Notes"])
        else:
            tdf = pd.DataFrame(tasks)
            rename = {"row": "#", "title": "Task", "due_date": "Due"}
            cols = ["row", "title", "status", "priority", "hours", "due_date", "notes"]
            tdf = tdf[[c for c in cols if c in tdf.columns]].rename(columns=rename)
        tdf.to_excel(xw, index=False, sheet_name="Tasks")

        # Summary (same as tasks)
        tdf.to_excel(xw, index=False, sheet_name="Summary")

    bio.seek(0)
    return bio.getvalue()


def export_all_summary_csv(deliverables: List[Dict]) -> bytes:
    """
    CSV of ALL deliverables' tasks (flattened by deliverable).
    """
    rows = []
    for d in deliverables:
        base = {
            "Deliverable ID": d.get("id",""),
            "Title": d.get("title",""),
            "Owner": d.get("owner",""),
            "Unit": d.get("unit",""),
            "Term": d.get("term",""),
        }
        for t in d.get("tasks", []) or []:
            row = base | {
                "#": t.get("row"),
                "Task": t.get("title"),
                "Status": t.get("status"),
                "Priority": t.get("priority"),
                "Hours": t.get("hours"),
                "Due": t.get("due_date"),
                "Notes": t.get("notes"),
            }
            rows.append(row)
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode("utf-8")


def export_all_flat_xlsx(deliverables: List[Dict]) -> bytes:
    """
    Excel with:
      - 'All Deliverables' (one row per deliverable)
      - 'All Tasks'      (one row per task with deliverable context)
    """
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as xw:
        d_rows = []
        t_rows = []
        for d in deliverables:
            d_rows.append({
                "Deliverable ID": d.get("id",""),
                "Title": d.get("title",""),
                "Owner": d.get("owner",""),
                "Unit": d.get("unit",""),
                "Term": d.get("term",""),
                "Notes": d.get("notes",""),
                "Created": d.get("created_at",""),
            })
            for t in d.get("tasks", []) or []:
                t_rows.append({
                    "Deliverable ID": d.get("id",""),
                    "Deliverable": d.get("title",""),
                    "#": t.get("row"),
                    "Task": t.get("title"),
                    "Status": t.get("status"),
                    "Priority": t.get("priority"),
                    "Hours": t.get("hours"),
                    "Due": t.get("due_date"),
                    "Notes": t.get("notes"),
                })
        pd.DataFrame(d_rows).to_excel(xw, index=False, sheet_name="All Deliverables")
        pd.DataFrame(t_rows).to_excel(xw, index=False, sheet_name="All Tasks")
    bio.seek(0)
    return bio.getvalue()


def filter_deliverables(items: List[Dict], term: str, owner: str, query: str) -> List[Dict]:
    term = (term or "").strip().lower()
    owner = (owner or "").strip().lower()
    query = (query or "").strip().lower()

    out = []
    for d in items:
        if term and term not in (d.get("term","").lower()):
            continue
        if owner and owner not in (d.get("owner","").lower()):
            continue
        hay = " ".join([d.get("title",""), d.get("unit",""), d.get("notes","")]).lower()
        if query and query not in hay:
            continue
        out.append(d)
    return out


def paginate(items: List[Dict], page: int, per_page: int) -> Tuple[List[Dict], int]:
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], total


def confirm_modal(prompt: str, state_key: str, match_id: str|None=None) -> bool:
    """
    Open a confirmation modal driven by a state flag.
    If match_id is provided, only open when the stored id matches.
    Return True when user confirms.
    """
    if match_id is not None:
        if st.session_state.get(state_key) != match_id:
            return False
    else:
        if not st.session_state.get(state_key):
            return False

    with st.modal("Confirm action"):
        st.warning(prompt)
        c1, c2 = st.columns(2)
        yes = c1.button("✅ Yes, delete")
        no  = c2.button("❌ Cancel")
        if yes:
            st.session_state[state_key] = None if match_id is not None else False
            return True
        if no:
            st.session_state[state_key] = None if match_id is not None else False
            st.rerun()
    return False


# -----------------------------------------------------------------------------
# Save / update / delete (session store; swap with DB if needed)
# -----------------------------------------------------------------------------
def save_deliverable(new_deliv: Dict):
    st.session_state["deliverables"].append(new_deliv)


def update_deliverable(updated: Dict):
    for i, d in enumerate(st.session_state["deliverables"]):
        if d["id"] == updated["id"]:
            st.session_state["deliverables"][i] = updated
            break


def delete_deliverable(deliv_id: str):
    st.session_state["deliverables"] = [d for d in st.session_state["deliverables"] if d["id"] != deliv_id]


# -----------------------------------------------------------------------------
# UI: Create deliverable (collapsible)
# -----------------------------------------------------------------------------
def create_deliverable_form():
    with st.form("new_deliverable", clear_on_submit=True):
        st.subheader("Create deliverable")

        # Deliverable fields
        d_title = st.text_input("Deliverable title *")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        with c1:
            d_owner = st.text_input("Owner")
        with c2:
            d_unit = st.text_input("Unit")
        with c3:
            d_term = st.text_input("Term", help="e.g., 2025–1 or Fall 2025")
        with c4:
            d_notes = st.text_area("Deliverable notes", height=80)

        st.markdown("### Tasks (up to 5)")

        # Common choices
        statuses = ["Not started", "In progress", "Blocked", "Done"]
        priorities = ["Low", "Medium", "High"]

        # --- Tasks 1..5
        task_inputs = []
        for i in range(1, 6):
            st.markdown(f"**Task {i}**")
            t_title = st.text_input(f"Task {i} — title", key=f"t{i}_title")
            c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
            with c1:
                t_status = st.selectbox("Status", statuses, key=f"t{i}_status")
            with c2:
                t_priority = st.selectbox("Priority", priorities, key=f"t{i}_priority")
            with c3:
                t_has_due = st.checkbox("Has due date?", key=f"t{i}_has_due")
                t_due = st.date_input("Due date", disabled=not t_has_due, key=f"t{i}_due")
            with c4:
                t_hours = st.number_input("Hours", min_value=0.0, step=0.5, key=f"t{i}_hours")
            t_notes = st.text_area(f"Notes {i}", height=60, key=f"t{i}_notes")
            task_inputs.append((t_title, t_status, t_hours, t_has_due, t_due, t_notes, t_priority))

        submitted = st.form_submit_button("Save deliverable")
        if submitted:
            # Validate
            if not d_title.strip():
                st.error("Please enter a deliverable title.")
                st.stop()

            tasks: List[Dict] = []
            for idx, (tt, stt, hrs, hdue, due, nts, pr) in enumerate(task_inputs, start=1):
                t = build_task(idx, tt, stt, hrs, hdue, due, nts, pr)
                if t:
                    tasks.append(t)

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
            save_deliverable(new_deliv)
            st.success("Deliverable added.")
            st.divider()


def edit_deliverable_modal(deliv: Dict):
    with st.modal(f"Edit: {deliv['title']}"):
        d_title = st.text_input("Deliverable title *", value=deliv.get("title", ""), key=f"e_title_{deliv['id']}")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        with c1:
            d_owner = st.text_input("Owner", value=deliv.get("owner",""), key=f"e_owner_{deliv['id']}")
        with c2:
            d_unit = st.text_input("Unit", value=deliv.get("unit",""), key=f"e_unit_{deliv['id']}")
        with c3:
            d_term = st.text_input("Term", value=deliv.get("term",""), key=f"e_term_{deliv['id']}")
        with c4:
            d_notes = st.text_area("Deliverable notes", value=deliv.get("notes",""), height=80, key=f"e_notes_{deliv['id']}")

        st.markdown("### Tasks (up to 5)")

        statuses = ["Not started", "In progress", "Blocked", "Done"]
        priorities = ["Low", "Medium", "High"]
        existing = {t["row"]: t for t in (deliv.get("tasks") or [])}

        task_inputs = []
        for i in range(1, 6):
            cur = existing.get(i, {})
            st.markdown(f"**Task {i}**")
            t_title = st.text_input(f"Task {i} — title", value=cur.get("title",""), key=f"et{i}_title_{deliv['id']}")
            c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
            with c1:
                t_status = st.selectbox("Status", statuses, index=(statuses.index(cur.get("status","Not started")) if cur.get("status") in statuses else 0), key=f"et{i}_status_{deliv['id']}")
            with c2:
                t_priority = st.selectbox("Priority", priorities, index=(priorities.index(cur.get("priority","Medium")) if cur.get("priority") in priorities else 1), key=f"et{i}_priority_{deliv['id']}")
            with c3:
                has_due_default = cur.get("due_date") is not None
                t_has_due = st.checkbox("Has due date?", value=has_due_default, key=f"et{i}_has_due_{deliv['id']}")
                t_due = st.date_input("Due date", value=cur.get("due_date"), disabled=not t_has_due, key=f"et{i}_due_{deliv['id']}")
            with c4:
                t_hours = st.number_input("Hours", value=float(cur.get("hours") or 0.0), min_value=0.0, step=0.5, key=f"et{i}_hours_{deliv['id']}")
            t_notes = st.text_area(f"Notes {i}", value=cur.get("notes",""), height=60, key=f"et{i}_notes_{deliv['id']}")
            task_inputs.append((t_title, t_status, t_hours, t_has_due, t_due, t_notes, t_priority))

        c1, c2 = st.columns(2)
        update = c1.button("💾 Save changes", key=f"save_{deliv['id']}")
        cancel = c2.button("Cancel", key=f"cancel_{deliv['id']}")
        if update:
            if not d_title.strip():
                st.error("Please enter a deliverable title.")
                st.stop()

            tasks: List[Dict] = []
            for idx, (tt, stt, hrs, hdue, due, nts, pr) in enumerate(task_inputs, start=1):
                t = build_task(idx, tt, stt, hrs, hdue, due, nts, pr)
                if t:
                    tasks.append(t)

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
            update_deliverable(updated)
            st.success("Updated.")
            st.rerun()
        if cancel:
            st.rerun()


def show_deliverable_card(deliv: Dict):
    title_line = f"📦 {deliv['title']}"
    sub = " · ".join([x for x in [deliv.get('owner',''), deliv.get('unit',''), deliv.get('term','')] if x])
    if sub:
        title_line += f" — {sub}"

    with st.expander(title_line, expanded=False):
        st.caption(f"ID: `{deliv['id']}` · created {deliv.get('created_at','')}")
        if deliv.get("notes"):
            st.markdown(f"**Notes:** {deliv['notes']}")

        tasks = deliv.get("tasks", []) or []
        if not tasks:
            st.info("No tasks added.")
        else:
            df = pd.DataFrame(tasks)
            cols = ["row", "title", "status", "priority", "hours", "due_date", "notes"]
            df = df[[c for c in cols if c in df.columns]]
            df = df.rename(columns={"row": "#", "title": "Task", "due_date": "Due"})
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Downloads and actions
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1], gap="small")
        with c1:
            st.download_button(
                "⬇️ Summary (CSV)",
                data=export_summary_csv(deliv),
                file_name=f"{deliv['title']}_summary.csv",
                mime="text/csv",
                help="Task table for this deliverable"
            )
        with c2:
            st.download_button(
                "⬇️ Full workbook (Excel)",
                data=export_full_xlsx(deliv),
                file_name=f"{deliv['title']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Deliverable + tasks + summary"
            )
        with c3:
            if st.button("✏️ Edit", key=f"edit_{deliv['id']}"):
                st.session_state["edit_id"] = deliv["id"]
        with c4:
            if st.button("🗑️ Delete", key=f"del_{deliv['id']}"):
                st.session_state["ask_delete_one"] = deliv["id"]

        # Confirm delete for this record
        if confirm_modal(f"Delete deliverable '{deliv['title']}'? This cannot be undone.", "ask_delete_one", match_id=deliv["id"]):
            delete_deliverable(deliv["id"])
            st.success("Deliverable deleted.")
            st.rerun()


# -----------------------------------------------------------------------------
# Top: global downloads
# -----------------------------------------------------------------------------
with st.container():
    st.subheader("Global downloads")
    items = st.session_state["deliverables"]
    c1, c2 = st.columns([1, 1], gap="small")
    with c1:
        st.download_button(
            "⬇️ All (Summary CSV)",
            data=export_all_summary_csv(items),
            file_name="dgcc_followup_all_summary.csv",
            mime="text/csv",
            help="All tasks across all deliverables"
        )
    with c2:
        st.download_button(
            "⬇️ All (Flattened Excel)",
            data=export_all_flat_xlsx(items),
            file_name="dgcc_followup_all.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="All deliverables + tasks in one workbook"
        )

st.divider()

# -----------------------------------------------------------------------------
# Create form (collapsed)
# -----------------------------------------------------------------------------
with st.expander("➕ Create deliverable", expanded=False):
    create_deliverable_form()

# -----------------------------------------------------------------------------
# Filters + Pagination + List
# -----------------------------------------------------------------------------
st.subheader("Deliverables")

# Build choices for filters
terms = sorted({(d.get("term") or "").strip() for d in st.session_state["deliverables"] if d.get("term")})
owners = sorted({(d.get("owner") or "").strip() for d in st.session_state["deliverables"] if d.get("owner")})

fc1, fc2, fc3, fc4 = st.columns([1, 1, 2, 1])
with fc1:
    f_term = st.selectbox("Term", [""] + terms, index=0, help="Filter by term")
with fc2:
    f_owner = st.selectbox("Owner", [""] + owners, index=0, help="Filter by owner")
with fc3:
    f_query = st.text_input("Search", help="title / unit / notes")
with fc4:
    per_page = st.selectbox("Per page", [5, 10, 20, 50], index=1)

all_items = st.session_state["deliverables"]
f_items = filter_deliverables(all_items, f_term, f_owner, f_query)

# Pagination
pages = max(1, (len(f_items) - 1) // per_page + 1)
st.session_state["page"] = min(st.session_state["page"], pages)
pc1, pc2, pc3 = st.columns([1, 1, 6])
with pc1:
    if st.button("◀ Prev", disabled=st.session_state["page"] <= 1):
        st.session_state["page"] -= 1
with pc2:
    if st.button("Next ▶", disabled=st.session_state["page"] >= pages):
        st.session_state["page"] += 1
with pc3:
    st.caption(f"Page {st.session_state['page']} / {pages}  •  {len(f_items)} match(es)")

page_items, _ = paginate(f_items, st.session_state["page"], per_page)

# Edit modal launcher (if any)
if st.session_state.get("edit_id"):
    ed = next((d for d in all_items if d["id"] == st.session_state["edit_id"]), None)
    if ed:
        edit_deliverable_modal(ed)

# Render page items
if not page_items:
    st.info("No deliverables match the current filters.")
else:
    for d in page_items:
        show_deliverable_card(d)

# -----------------------------------------------------------------------------
# End
# -----------------------------------------------------------------------------
