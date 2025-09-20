# app.py — DGCC Follow-up Manager (clean, single file)

from __future__ import annotations

import io
import uuid
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# ──────────────────────────────────────────────────────────────────────────────
# Page config + compact CSS
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="DGCC Follow-up Manager", layout="wide")

st.markdown(
    """
<style>
/* Compact, tidy dashboard look */
.block-container {max-width: 1100px;}
.stExpander {border: 1px solid #e5e7eb; border-radius: 12px;}
[data-testid="stForm"] .stTextInput,
[data-testid="stForm"] .stTextArea,
[data-testid="stForm"] .stSelectbox,
[data-testid="stForm"] .stNumberInput,
[data-testid="stForm"] .stDateInput { margin-bottom: .35rem; }
</style>
""",
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# App-wide state and fixed choices (no "Variables" panel)
# ──────────────────────────────────────────────────────────────────────────────
if "deliverables" not in st.session_state:
    st.session_state["deliverables"] = []  # list[dict]

# Control the create expander open/close from anywhere
if "open_create" not in st.session_state:
    st.session_state["open_create"] = False

def open_create() -> None:
    st.session_state["open_create"] = True

def close_create() -> None:
    st.session_state["open_create"] = False

# Track which deliverable is being edited
if "edit_id" not in st.session_state:
    st.session_state["edit_id"] = None

# Fixed options used in forms (you can change these values)
STATUS_OPTIONS = ["Not started", "In progress", "Blocked", "Done"]
PRIORITY_OPTIONS = ["Low", "Medium", "High"]


# ──────────────────────────────────────────────────────────────────────────────
# Small helpers
# ──────────────────────────────────────────────────────────────────────────────
def generate_id() -> str:
    return uuid.uuid4().hex[:10]

def confirm_modal(prompt: str, state_key: str, match_id: Optional[str] = None) -> bool:
    """
    Confirmation modal:
      - Toggle by setting st.session_state[state_key] = True or to a specific id
      - If match_id is provided, the modal only renders if state_key == match_id
    Returns True when user clicks "Yes".
    """
    current = st.session_state.get(state_key)
    if match_id is not None and current != match_id:
        return False
    if not current:
        return False

    with st.modal("Confirm action"):
        st.warning(prompt)
        c1, c2 = st.columns(2)
        yes = c1.button("Yes, continue")
        no = c2.button("Cancel")
        if yes:
            st.session_state[state_key] = False if match_id is None else None
            return True
        if no:
            st.session_state[state_key] = False if match_id is None else None
            st.rerun()
    return False


# Build a single task row from inputs; skip row if title is blank
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
        "due_date": due if has_due else None,
        "notes": (notes or "").strip(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Export helpers (per deliverable and global)
# ──────────────────────────────────────────────────────────────────────────────
def deliverable_summary_df(d: Dict) -> pd.DataFrame:
    rows = []
    for t in d.get("tasks", []) or []:
        rows.append(
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
    return pd.DataFrame(rows)


def export_summary_csv(d: Dict) -> bytes:
    df = deliverable_summary_df(d)
    buff = io.StringIO()
    df.to_csv(buff, index=False)
    return buff.getvalue().encode("utf-8")


def export_full_xlsx(d: Dict) -> bytes:
    """Three sheets in one workbook: deliverable meta, tasks, flattened (same as summary)"""
    meta = pd.DataFrame(
        [
            {
                "id": d["id"],
                "title": d.get("title", ""),
                "owner": d.get("owner", ""),
                "unit": d.get("unit", ""),
                "term": d.get("term", ""),
                "created_at": d.get("created_at", ""),
                "notes": d.get("notes", ""),
            }
        ]
    )
    tasks = pd.DataFrame(d.get("tasks", []) or [])
    flat = deliverable_summary_df(d)

    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="xlsxwriter") as w:
        meta.to_excel(w, index=False, sheet_name="deliverable")
        tasks.to_excel(w, index=False, sheet_name="tasks")
        flat.to_excel(w, index=False, sheet_name="summary")
    return buff.getvalue()


def build_global_tables(items: List[Dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    d_rows = []
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
    df_deliv = pd.DataFrame(d_rows)

    t_rows = []
    for d in items:
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
    df_tasks = pd.DataFrame(t_rows)
    df_flat = df_tasks.copy() if len(df_tasks) else pd.DataFrame(
        columns=[
            "deliverable_id",
            "deliverable_title",
            "row",
            "title",
            "status",
            "priority",
            "hours",
            "due_date",
            "notes",
        ]
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


# ──────────────────────────────────────────────────────────────────────────────
# Create & Edit forms
# ──────────────────────────────────────────────────────────────────────────────
def create_deliverable_form() -> None:
    with st.form("new_deliverable", clear_on_submit=True):
        st.subheader("Create deliverable")

        d_title = st.text_input("Deliverable title *")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        with c1:
            d_owner = st.text_input("Owner")
        with c2:
            d_unit = st.text_input("Unit")
        with c3:
            d_term = st.text_input("Term", help="e.g., 2025-1 or Fall 2025")
        with c4:
            d_notes = st.text_area("Deliverable notes", height=80)

        st.markdown("### Tasks (up to 5)")

        task_inputs = []
        for i in range(1, 6):
            st.markdown(f"**Task {i}**")
            t_title = st.text_input(f"Title {i}", key=f"t{i}_title")
            cc1, cc2, cc3, cc4 = st.columns([1, 1, 1, 1])
            with cc1:
                t_status = st.selectbox(
                    f"Status {i}", STATUS_OPTIONS, index=0, key=f"t{i}_status"
                )
            with cc2:
                t_pri = st.selectbox(
                    f"Priority {i}", PRIORITY_OPTIONS, index=1, key=f"t{i}_priority"
                )
            with cc3:
                t_has_due = st.checkbox(f"Has due date? {i}", key=f"t{i}_has_due")
                t_due = st.date_input(f"Due date {i}", disabled=not t_has_due, key=f"t{i}_due")
            with cc4:
                t_hours = st.number_input(
                    f"Hours {i}", min_value=0.0, step=0.5, key=f"t{i}_hours"
                )
            t_notes = st.text_area(f"Notes {i}", height=60, key=f"t{i}_notes")
            st.divider()

            task_inputs.append(
                (i, t_title, t_status, t_hours, t_has_due, t_due, t_notes, t_pri)
            )

        submitted = st.form_submit_button("Save deliverable")

        if submitted:
            if not d_title.strip():
                st.error("Please enter a deliverable title.")
                st.stop()

            tasks: List[Dict] = []
            for (i, title, status, hours, has_due, due, notes, pri) in task_inputs:
                task = build_task(i, title, status, hours, has_due, due, notes, pri)
                if task:
                    tasks.append(task)

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

            st.session_state["deliverables"].append(new_deliv)
            close_create()  # hide form after save
            st.success("Deliverable added.")
            st.rerun()


def edit_deliverable_modal(deliv: Dict) -> None:
    if st.session_state.get("edit_id") != deliv["id"]:
        return
    with st.modal("Edit deliverable"):
        with st.form(f"edit_form_{deliv['id']}", clear_on_submit=False):
            st.subheader("Edit deliverable")
            d_title = st.text_input("Deliverable title *", value=deliv.get("title", ""))
            c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
            with c1:
                d_owner = st.text_input("Owner", value=deliv.get("owner", ""))
            with c2:
                d_unit = st.text_input("Unit", value=deliv.get("unit", ""))
            with c3:
                d_term = st.text_input("Term", value=deliv.get("term", ""))
            with c4:
                d_notes = st.text_area(
                    "Deliverable notes", value=deliv.get("notes", ""), height=80
                )

            st.markdown("### Tasks (up to 5)")
            # Use up to 5; prefill existing tasks by row number
            existing_by_row = {t.get("row"): t for t in deliv.get("tasks", []) or []}
            task_inputs = []
            for i in range(1, 6):
                st.markdown(f"**Task {i}**")
                t0 = existing_by_row.get(i, {})
                t_title = st.text_input(f"Title {i}", value=t0.get("title", ""), key=f"e_{deliv['id']}_t{i}_title")
                cc1, cc2, cc3, cc4 = st.columns([1, 1, 1, 1])
                with cc1:
                    t_status = st.selectbox(
                        f"Status {i}",
                        STATUS_OPTIONS,
                        index=STATUS_OPTIONS.index(t0.get("status", STATUS_OPTIONS[0]))
                        if t0.get("status") in STATUS_OPTIONS
                        else 0,
                        key=f"e_{deliv['id']}_t{i}_status",
                    )
                with cc2:
                    pri_val = t0.get("priority", PRIORITY_OPTIONS[1])
                    t_pri = st.selectbox(
                        f"Priority {i}",
                        PRIORITY_OPTIONS,
                        index=PRIORITY_OPTIONS.index(pri_val)
                        if pri_val in PRIORITY_OPTIONS
                        else 1,
                        key=f"e_{deliv['id']}_t{i}_priority",
                    )
                with cc3:
                    has_due_default = t0.get("due_date") is not None
                    t_has_due = st.checkbox(
                        f"Has due date? {i}",
                        value=has_due_default,
                        key=f"e_{deliv['id']}_t{i}_has_due",
                    )
                    due_default = t0.get("due_date") or date.today()
                    t_due = st.date_input(
                        f"Due date {i}",
                        value=due_default,
                        disabled=not t_has_due,
                        key=f"e_{deliv['id']}_t{i}_due",
                    )
                with cc4:
                    t_hours = st.number_input(
                        f"Hours {i}",
                        min_value=0.0,
                        step=0.5,
                        value=float(t0.get("hours", 0.0) or 0.0),
                        key=f"e_{deliv['id']}_t{i}_hours",
                    )
                t_notes = st.text_area(
                    f"Notes {i}", value=t0.get("notes", ""), height=60, key=f"e_{deliv['id']}_t{i}_notes"
                )
                st.divider()
                task_inputs.append(
                    (i, t_title, t_status, t_hours, t_has_due, t_due, t_notes, t_pri)
                )

            c1, c2 = st.columns(2)
            save = c1.form_submit_button("Save changes")
            cancel = c2.form_submit_button("Cancel")

            if cancel:
                st.session_state["edit_id"] = None
                st.rerun()

            if save:
                if not d_title.strip():
                    st.error("Please enter a deliverable title.")
                    st.stop()

                tasks: List[Dict] = []
                for (i, title, status, hours, has_due, due, notes, pri) in task_inputs:
                    task = build_task(i, title, status, hours, has_due, due, notes, pri)
                    if task:
                        tasks.append(task)

                updated = {
                    "id": deliv["id"],
                    "title": d_title.strip(),
                    "owner": d_owner.strip(),
                    "unit": d_unit.strip(),
                    "term": d_term.strip(),
                    "notes": d_notes.strip(),
                    "created_at": deliv.get("created_at")
                    or datetime.utcnow().isoformat(timespec="seconds"),
                    "tasks": tasks,
                }

                # Replace in session
                items = st.session_state["deliverables"]
                for idx, d in enumerate(items):
                    if d["id"] == deliv["id"]:
                        items[idx] = updated
                        break

                st.session_state["edit_id"] = None
                st.success("Deliverable updated.")
                st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Filters + pagination
# ──────────────────────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────────────────────
# Rendering of deliverable card
# ──────────────────────────────────────────────────────────────────────────────
def show_deliverable_card(deliv: Dict) -> None:
    with st.expander(f"{deliv.get('title','')} — {deliv.get('owner','')}", expanded=False):
        st.caption(f"ID: `{deliv['id']}` · created {deliv.get('created_at','')}")
        if deliv.get("notes"):
            st.markdown(f"**Notes:** {deliv['notes']}")

        # Task table
        tasks = deliv.get("tasks", []) or []
        if not tasks:
            st.info("No tasks added.")
        else:
            df = pd.DataFrame(tasks)
            cols = ["row", "title", "status", "priority", "hours", "due_date", "notes"]
            df = df[[c for c in cols if c in df.columns]]
            st.dataframe(
                df.rename(columns={"row": "#", "title": "Task", "due_date": "Due"}),
                use_container_width=True,
                hide_index=True,
            )

        # Downloads + actions
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        with c1:
            st.download_button(
                "Summary (CSV)",
                data=export_summary_csv(deliv),
                file_name=f"{deliv['title']}_summary.csv",
                mime="text/csv",
            )
        with c2:
            st.download_button(
                "Full workbook (Excel)",
                data=export_full_xlsx(deliv),
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
            items = st.session_state["deliverables"]
            st.session_state["deliverables"] = [d for d in items if d["id"] != deliv["id"]]
            st.success("Deliverable deleted.")
            st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────────────
st.title("DGCC Follow-up Manager")

# Collapsible create form (can be opened from the header button)
with st.expander("Create deliverable", expanded=st.session_state.get("open_create", False)):
    create_deliverable_form()

# Deliverables header with "Create" button on the right
hdr_l, hdr_r = st.columns([6, 2])
with hdr_l:
    st.subheader("Deliverables")
with hdr_r:
    st.button("Create deliverable", on_click=open_create, use_container_width=True)

# Build choices for filters
items = st.session_state["deliverables"]
terms = sorted({(d.get("term") or "").strip() for d in items if d.get("term")})
owners = sorted({(d.get("owner") or "").strip() for d in items if d.get("owner")})

fc1, fc2, fc3, fc4 = st.columns([1, 1, 2, 1])
with fc1:
    f_term = st.selectbox("Term", [""] + terms, index=0)
with fc2:
    f_owner = st.selectbox("Owner", [""] + owners, index=0)
with fc3:
    f_query = st.text_input("Search", help="title / unit / notes")
with fc4:
    per_page = st.selectbox("Per page", [5, 10, 20, 50], index=1)

filtered = filter_deliverables(items, f_term, f_owner, f_query)

# Global downloads for the filtered set
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

# Pagination controls
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

# Render edit modal if needed (do this before drawing cards)
if st.session_state.get("edit_id"):
    ed = next((d for d in items if d["id"] == st.session_state["edit_id"]), None)
    if ed:
        edit_deliverable_modal(ed)

# Draw cards or empty state
if not page_items:
    st.info("No deliverables match the current filters.")
else:
    for d in page_items:
        show_deliverable_card(d)

st.divider()
st.button("Create deliverable", on_click=open_create)
