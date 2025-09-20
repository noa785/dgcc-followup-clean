# app.py — DGCC Follow-up (clean, professional)
# -------------------------------------------------
# Single file. No external database; uses session state.
# You can wire DB persistence later inside save/update/delete helpers.

from __future__ import annotations

from typing import List, Dict, Optional, Tuple
from datetime import datetime, date
import io
import uuid

import pandas as pd
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# Page setup and compact CSS
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="DGCC Follow-up Manager", layout="wide")

st.markdown(
    """
<style>
/* Narrower content and tighter spacing */
.block-container { max-width: 1100px; }
[data-testid="stForm"] .stTextInput,
[data-testid="stForm"] .stTextArea,
[data-testid="stForm"] .stSelectbox,
[data-testid="stForm"] .stNumberInput,
[data-testid="stForm"] .stDateInput { margin-bottom: .35rem; }
.stExpander { border: 1px solid #e5e7eb; border-radius: 12px; }
.small-note { color:#6b7280; font-size:.9rem; margin-top:.35rem; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("DGCC Follow-up — Clean")

# ──────────────────────────────────────────────────────────────────────────────
# Session state bootstrap
# ──────────────────────────────────────────────────────────────────────────────
if "deliverables" not in st.session_state:
    st.session_state["deliverables"] = []

if "vars" not in st.session_state:
    st.session_state["vars"] = {
        "status": ["Not started", "In progress", "Blocked", "Done"],
        "priority": ["Low", "Medium", "High"],
        "owners": [],
    }

if "create_open" not in st.session_state:
    st.session_state["create_open"] = False

if "open_ids" not in st.session_state:
    st.session_state["open_ids"] = set()

# ──────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ──────────────────────────────────────────────────────────────────────────────
def generate_id() -> str:
    return uuid.uuid4().hex[:10]

def save_deliverable(item: Dict) -> None:
    """Append to in-memory list (replace with DB insert if needed)."""
    st.session_state["deliverables"].append(item)

def update_deliverable(updated: Dict) -> None:
    items = st.session_state["deliverables"]
    for i, d in enumerate(items):
        if d["id"] == updated["id"]:
            items[i] = updated
            break

def delete_deliverable(deliv_id: str) -> None:
    items = st.session_state["deliverables"]
    st.session_state["deliverables"] = [d for d in items if d["id"] != deliv_id]
    # Also remove from "open" set
    st.session_state["open_ids"].discard(deliv_id)

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
    """Return a task dict if title is not empty; otherwise None (skip row)."""
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

def expand_all(ids: List[str]) -> None:
    st.session_state["open_ids"] = set(ids)

def collapse_all() -> None:
    st.session_state["open_ids"] = set()

def confirm_modal(prompt: str, state_key: str, match_id: Optional[str] = None) -> bool:
    """
    Simple modal confirmation.
    - set st.session_state[state_key] = True or = <id> before calling.
    - If match_id is given, only opens when state equals that id.
    """
    test_val = st.session_state.get(state_key)
    if match_id is not None and test_val != match_id:
        return False
    if test_val:
        with st.modal("Confirm action"):
            st.warning(prompt)
            c1, c2 = st.columns(2)
            yes = c1.button("Yes, proceed")
            no = c2.button("Cancel")
            if yes:
                st.session_state[state_key] = None
                return True
            if no:
                st.session_state[state_key] = None
                st.rerun()
    return False

# ──────────────────────────────────────────────────────────────────────────────
# Export helpers
# ──────────────────────────────────────────────────────────────────────────────
def export_summary_csv(deliv: Dict) -> bytes:
    rows = []
    if deliv.get("tasks"):
        for t in deliv["tasks"]:
            rows.append(
                {
                    "deliverable_id": deliv["id"],
                    "deliverable_title": deliv["title"],
                    "task_row": t.get("row"),
                    "task_title": t.get("title"),
                    "status": t.get("status"),
                    "priority": t.get("priority"),
                    "hours": t.get("hours"),
                    "due_date": t.get("due_date"),
                    "notes": t.get("notes"),
                }
            )
    df = pd.DataFrame(rows)
    buff = io.StringIO()
    df.to_csv(buff, index=False)
    return buff.getvalue().encode("utf-8")

def export_full_xlsx(deliv: Dict) -> bytes:
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="xlsxwriter") as writer:
        # Deliverable info
        info = pd.DataFrame(
            [
                {
                    "id": deliv["id"],
                    "title": deliv["title"],
                    "owner": deliv.get("owner", ""),
                    "unit": deliv.get("unit", ""),
                    "term": deliv.get("term", ""),
                    "created_at": deliv.get("created_at", ""),
                    "notes": deliv.get("notes", ""),
                }
            ]
        )
        info.to_excel(writer, index=False, sheet_name="deliverable")

        # Tasks
        tasks = pd.DataFrame(deliv.get("tasks", []))
        tasks.to_excel(writer, index=False, sheet_name="tasks")
    return buff.getvalue()

# ──────────────────────────────────────────────────────────────────────────────
# Variables panel (status/priority/owners)
# ──────────────────────────────────────────────────────────────────────────────
def variables_panel():
    with st.expander("Variables", expanded=False):
        st.caption("Edit the lists used in forms. Use comma-separated values.")
        with st.form("vars_form", clear_on_submit=False):
            v = st.session_state["vars"]
            status_csv = st.text_input("Status options", ", ".join(v["status"]))
            priority_csv = st.text_input("Priority options", ", ".join(v["priority"]))
            owners_csv = st.text_input("Owners (optional)", ", ".join(v.get("owners", [])))
            saved = st.form_submit_button("Save variables")
            if saved:
                st.session_state["vars"] = {
                    "status": [s.strip() for s in status_csv.split(",") if s.strip()],
                    "priority": [s.strip() for s in priority_csv.split(",") if s.strip()],
                    "owners": [s.strip() for s in owners_csv.split(",") if s.strip()],
                }
                st.success("Variables saved.")

variables_panel()

# ──────────────────────────────────────────────────────────────────────────────
# Create deliverable (collapsible)
# ──────────────────────────────────────────────────────────────────────────────
st.button("Add deliverable", on_click=lambda: st.session_state.__setitem__("create_open", True))

def create_deliverable_form():
    status_options = st.session_state["vars"]["status"]
    priority_options = st.session_state["vars"]["priority"]
    owner_options = [""] + st.session_state["vars"].get("owners", [])

    with st.form("new_deliverable", clear_on_submit=True):
        st.subheader("Create deliverable")

        # Deliverable level fields
        title = st.text_input("Deliverable title *")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        with c1:
            owner = st.selectbox("Owner", owner_options)
        with c2:
            unit = st.text_input("Unit")
        with c3:
            term = st.text_input("Term", help="e.g., 2025–1 or Fall 2025")
        with c4:
            notes = st.text_area("Deliverable notes", height=80)

        st.markdown("### Tasks (up to 5)")
        st.caption("Leave a task title empty to skip that row.")

        # We generate 5 task rows using keys t{idx}_*
        for idx in range(1, 6):
            st.markdown(f"**Task {idx}**")
            t_title = st.text_input("Title", key=f"t{idx}_title")
            cols = st.columns([1, 1, 1, 1])
            with cols[0]:
                st.selectbox("Status", status_options, key=f"t{idx}_status")
            with cols[1]:
                st.selectbox("Priority", priority_options, key=f"t{idx}_priority")
            with cols[2]:
                st.checkbox("Has due date?", key=f"t{idx}_has_due")
                st.date_input("Due date", disabled=not st.session_state.get(f"t{idx}_has_due"), key=f"t{idx}_due")
            with cols[3]:
                st.number_input("Hours", min_value=0.0, step=0.5, key=f"t{idx}_hours")
            st.text_area("Notes", height=60, key=f"t{idx}_notes")
            st.divider()

        col_a, col_b = st.columns([1, 1])
        save_close = col_a.form_submit_button("Save and close")
        save_again = col_b.form_submit_button("Save and add another")

        if save_close or save_again:
            if not title.strip():
                st.error("Please enter a deliverable title.")
                st.stop()

            tasks: List[Dict] = []
            for idx in range(1, 6):
                task = build_task(
                    idx,
                    st.session_state.get(f"t{idx}_title"),
                    st.session_state.get(f"t{idx}_status"),
                    st.session_state.get(f"t{idx}_hours"),
                    st.session_state.get(f"t{idx}_has_due"),
                    st.session_state.get(f"t{idx}_due"),
                    st.session_state.get(f"t{idx}_notes"),
                    st.session_state.get(f"t{idx}_priority"),
                )
                if task:
                    tasks.append(task)

            new_deliv = {
                "id": generate_id(),
                "title": title.strip(),
                "owner": (owner or "").strip(),
                "unit": unit.strip(),
                "term": term.strip(),
                "notes": notes.strip(),
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                "tasks": tasks,
            }
            save_deliverable(new_deliv)
            st.success("Deliverable saved.")

            if save_close:
                st.session_state["create_open"] = False
                st.rerun()
            else:
                st.session_state["create_open"] = True
                st.rerun()

with st.expander("Create deliverable", expanded=st.session_state["create_open"]):
    create_deliverable_form()

# ──────────────────────────────────────────────────────────────────────────────
# Edit modal
# ──────────────────────────────────────────────────────────────────────────────
def edit_deliverable_modal(deliv: Dict):
    status_options = st.session_state["vars"]["status"]
    priority_options = st.session_state["vars"]["priority"]
    owner_options = [""] + st.session_state["vars"].get("owners", [])

    with st.modal(f"Edit — {deliv['title']}"):
        with st.form(f"edit_form_{deliv['id']}", clear_on_submit=False):
            title = st.text_input("Deliverable title *", value=deliv.get("title", ""))
            c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
            with c1:
                owner = st.selectbox("Owner", owner_options, index=(owner_options.index(deliv.get("owner","")) if deliv.get("owner","") in owner_options else 0))
            with c2:
                unit = st.text_input("Unit", value=deliv.get("unit", ""))
            with c3:
                term = st.text_input("Term", value=deliv.get("term", ""))
            with c4:
                notes = st.text_area("Deliverable notes", value=deliv.get("notes", ""), height=80)

            st.markdown("### Tasks (up to 5)")
            tasks = deliv.get("tasks", []) or []

            # Render 5 rows; prefill with existing by row number if present
            existing_by_row = {t["row"]: t for t in tasks if "row" in t}
            for idx in range(1, 6):
                t = existing_by_row.get(idx, {})
                st.markdown(f"**Task {idx}**")
                st.text_input("Title", value=t.get("title", ""), key=f"e_{deliv['id']}_t{idx}_title")
                cols = st.columns([1, 1, 1, 1])
                with cols[0]:
                    st.selectbox("Status", status_options, index=(status_options.index(t.get("status","Not started")) if t.get("status") in status_options else 0), key=f"e_{deliv['id']}_t{idx}_status")
                with cols[1]:
                    st.selectbox("Priority", priority_options, index=(priority_options.index(t.get("priority","Low")) if t.get("priority") in priority_options else 0), key=f"e_{deliv['id']}_t{idx}_priority")
                with cols[2]:
                    has_due = t.get("due_date") is not None
                    st.checkbox("Has due date?", value=has_due, key=f"e_{deliv['id']}_t{idx}_has_due")
                    st.date_input(
                        "Due date",
                        value=t.get("due_date"),
                        disabled=not st.session_state.get(f"e_{deliv['id']}_t{idx}_has_due"),
                        key=f"e_{deliv['id']}_t{idx}_due",
                    )
                with cols[3]:
                    st.number_input("Hours", min_value=0.0, step=0.5, value=(float(t.get("hours")) if t.get("hours") not in (None, "") else 0.0), key=f"e_{deliv['id']}_t{idx}_hours")
                st.text_area("Notes", value=t.get("notes", ""), height=60, key=f"e_{deliv['id']}_t{idx}_notes")
                st.divider()

            col1, col2 = st.columns([1, 1])
            save_btn = col1.form_submit_button("Save changes")
            cancel_btn = col2.form_submit_button("Cancel")

            if save_btn:
                if not title.strip():
                    st.error("Please enter a deliverable title.")
                    st.stop()

                new_tasks: List[Dict] = []
                for idx in range(1, 6):
                    task = build_task(
                        idx,
                        st.session_state.get(f"e_{deliv['id']}_t{idx}_title"),
                        st.session_state.get(f"e_{deliv['id']}_t{idx}_status"),
                        st.session_state.get(f"e_{deliv['id']}_t{idx}_hours"),
                        st.session_state.get(f"e_{deliv['id']}_t{idx}_has_due"),
                        st.session_state.get(f"e_{deliv['id']}_t{idx}_due"),
                        st.session_state.get(f"e_{deliv['id']}_t{idx}_notes"),
                        st.session_state.get(f"e_{deliv['id']}_t{idx}_priority"),
                    )
                    if task:
                        new_tasks.append(task)

                updated = {
                    "id": deliv["id"],
                    "title": title.strip(),
                    "owner": (owner or "").strip(),
                    "unit": unit.strip(),
                    "term": term.strip(),
                    "notes": notes.strip(),
                    "created_at": deliv.get("created_at") or datetime.utcnow().isoformat(timespec="seconds"),
                    "tasks": new_tasks,
                }
                update_deliverable(updated)
                st.success("Changes saved.")
                st.rerun()

            if cancel_btn:
                st.rerun()

# ──────────────────────────────────────────────────────────────────────────────
# Deliverables list — filters, pagination, expand/collapse all
# ──────────────────────────────────────────────────────────────────────────────
st.subheader("Deliverables")

terms = sorted({(d.get("term") or "").strip() for d in st.session_state["deliverables"] if d.get("term")})
owners = sorted({(d.get("owner") or "").strip() for d in st.session_state["deliverables"] if d.get("owner")})

fc1, fc2, fc3, fc4 = st.columns([1, 1, 2, 1])
with fc1:
    f_term = st.selectbox("Term", [""] + terms, index=0)
with fc2:
    f_owner = st.selectbox("Owner", [""] + owners, index=0)
with fc3:
    f_query = st.text_input("Search", help="title / unit / notes")
with fc4:
    per_page = st.selectbox("Per page", [5, 10, 20, 50], index=1)

all_items = st.session_state["deliverables"]
filtered = filter_deliverables(all_items, f_term, f_owner, f_query)

if "page" not in st.session_state:
    st.session_state["page"] = 1

# reset page if filters change could be added; minimal approach
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

# Expand / Collapse all for the current page
page_ids = [d["id"] for d in page_items]
ec1, ec2, _ = st.columns([1, 1, 6])
with ec1:
    st.button("Expand all", on_click=lambda: expand_all(page_ids))
with ec2:
    st.button("Collapse all", on_click=collapse_all)

# ──────────────────────────────────────────────────────────────────────────────
# Card rendering
# ──────────────────────────────────────────────────────────────────────────────
def show_deliverable_card(deliv: Dict):
    is_open = deliv["id"] in st.session_state["open_ids"]

    with st.expander(f"{deliv['title']} — {deliv.get('owner','')}", expanded=is_open):
        # Keep it in the open set while it's visible
        st.session_state["open_ids"].add(deliv["id"])

        st.caption(f"ID: `{deliv['id']}` • Created {deliv.get('created_at','')}")
        meta = []
        if deliv.get("unit"): meta.append(f"Unit: {deliv['unit']}")
        if deliv.get("term"): meta.append(f"Term: {deliv['term']}")
        if meta:
            st.write(" • ".join(meta))
        if deliv.get("notes"):
            st.markdown(f"**Notes:** {deliv['notes']}")

        # Tasks table
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

        # Actions: download / edit / delete
        c1, c2, c3 = st.columns([1, 1, 1])
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
            colx, coly = st.columns(2)
            if colx.button("Edit", key=f"edit_{deliv['id']}"):
                st.session_state["edit_id"] = deliv["id"]
            if coly.button("Delete", key=f"del_{deliv['id']}"):
                st.session_state["ask_delete_one"] = deliv["id"]

        # Confirm delete modal
        if confirm_modal(
            f"Delete deliverable '{deliv['title']}'? This cannot be undone.",
            "ask_delete_one",
            match_id=deliv["id"],
        ):
            delete_deliverable(deliv["id"])
            st.success("Deliverable deleted.")
            st.rerun()

# Show edit modal if requested
if st.session_state.get("edit_id"):
    to_edit = next((d for d in all_items if d["id"] == st.session_state["edit_id"]), None)
    if to_edit:
        edit_deliverable_modal(to_edit)
    st.session_state["edit_id"] = None

# Render list
if not page_items:
    st.info("No deliverables match the current filters.")
else:
    for d in page_items:
        show_deliverable_card(d)
