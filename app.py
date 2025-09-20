# app.py — DGCC Follow-up (clean, official, error-free)

from __future__ import annotations
import io
import uuid
from datetime import date, datetime
from typing import List, Dict, Any

import pandas as pd
import streamlit as st


# ------------------------------------------------------------------------------
# Page config and small helpers
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="DGCC Follow-up (clean)",
    page_icon="📝",
    layout="wide",
)

def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def _new_id() -> str:
    return uuid.uuid4().hex[:12]

def _init_state():
    if "deliverables" not in st.session_state:
        st.session_state["deliverables"] = []  # list[dict]
    if "show_new_form" not in st.session_state:
        st.session_state["show_new_form"] = True
    if "filters" not in st.session_state:
        st.session_state["filters"] = {"q": "", "priority": "All", "owner": "All"}

_init_state()


# ------------------------------------------------------------------------------
# Reusable confirm modal (Streamlit has no st.confirm)
# ------------------------------------------------------------------------------
def confirm_modal(prompt: str, state_key: str) -> bool:
    """
    Open a confirmation modal if st.session_state[state_key] is True.
    Return True only when the user clicks 'Yes'.
    Usage:
        if st.button("Delete ..."):
            st.session_state['ask_delete'] = True
        if confirm_modal("Sure?", 'ask_delete'):
            ...
    """
    if st.session_state.get(state_key):
        with st.modal("Confirm action"):
            st.warning(prompt)
            c1, c2 = st.columns(2)
            yes = c1.button("✅ Yes, do it", key=f"{state_key}_yes")
            no = c2.button("❌ Cancel", key=f"{state_key}_no")
            if yes:
                st.session_state[state_key] = False
                return True
            if no:
                st.session_state[state_key] = False
                st.rerun()
    return False


# ------------------------------------------------------------------------------
# Data model helpers
# ------------------------------------------------------------------------------
Task = Dict[str, Any]
Deliverable = Dict[str, Any]

def build_deliverable(
    unit: str,
    title: str,
    owner: str,
    priority: str,
    notes: str,
    tasks: List[Task],
) -> Deliverable:
    return {
        "id": _new_id(),
        "created": _now_str(),
        "unit": unit.strip(),
        "title": title.strip(),
        "owner": owner.strip(),
        "priority": priority,
        "notes": notes.strip(),
        "tasks": tasks,
    }

def task_row_form(idx: int) -> Task:
    """
    Render a single task row (inline form pieces) and return its structure.
    Leaving title empty => row ignored by caller.
    """
    st.markdown(f"**Task {idx+1}**")
    cols = st.columns([3, 1.4, 1.2, 1.2])
    title = cols[0].text_input("Title", key=f"t_title_{idx}", placeholder="Task title")
    has_due = cols[1].checkbox("Has due date?", key=f"t_has_due_{idx}", value=False)
    if has_due:
        due = cols[1].date_input("Due date", key=f"t_due_{idx}", value=date.today())
    else:
        # Render disabled-looking placeholder date input
        cols[1].date_input("Due date", value=date.today(), key=f"t_due_{idx}_disabled", disabled=True)
        due = None

    status = cols[2].selectbox("Status", ["New", "In progress", "Done", "Blocked"], key=f"t_status_{idx}")
    hours = cols[3].number_input("Hours", min_value=0.0, step=0.5, key=f"t_hours_{idx}")

    notes = st.text_area("Notes", key=f"t_notes_{idx}", placeholder="Optional notes", height=80)
    st.markdown("---")

    if not title.strip():
        return {}  # ignored
    return {
        "title": title.strip(),
        "has_due": has_due,
        "due": str(due) if due else "",
        "status": status,
        "hours": float(hours or 0.0),
        "notes": notes.strip(),
    }


# ------------------------------------------------------------------------------
# Export helpers
# ------------------------------------------------------------------------------
def to_summary_df(deliverables: List[Deliverable]) -> pd.DataFrame:
    records = []
    for d in deliverables:
        records.append({
            "ID": d["id"],
            "Created": d["created"],
            "Unit": d["unit"],
            "Title": d["title"],
            "Owner": d["owner"],
            "Priority": d["priority"],
            "Notes": d["notes"],
            "Tasks_count": len(d["tasks"]),
            "Hours_total": sum(t.get("hours", 0.0) for t in d["tasks"]),
        })
    if not records:
        return pd.DataFrame(columns=["ID","Created","Unit","Title","Owner","Priority","Notes","Tasks_count","Hours_total"])
    return pd.DataFrame(records)

def to_flat_tasks_df(deliverables: List[Deliverable]) -> pd.DataFrame:
    rows = []
    for d in deliverables:
        for i, t in enumerate(d["tasks"], start=1):
            rows.append({
                "Deliverable_ID": d["id"],
                "Unit": d["unit"],
                "Deliverable": d["title"],
                "Owner": d["owner"],
                "Priority": d["priority"],
                "Task_no": i,
                "Task_title": t["title"],
                "Has_due": t["has_due"],
                "Due": t["due"],
                "Status": t["status"],
                "Hours": t["hours"],
                "Task_notes": t["notes"],
            })
    if not rows:
        return pd.DataFrame(columns=[
            "Deliverable_ID","Unit","Deliverable","Owner","Priority",
            "Task_no","Task_title","Has_due","Due","Status","Hours","Task_notes"
        ])
    return pd.DataFrame(rows)

def excel_for_deliverable(d: Deliverable) -> bytes:
    """
    Build an Excel workbook with:
      - Summary sheet (1 row for the deliverable)
      - Tasks sheet (all tasks with columns)
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        to_summary_df([d]).to_excel(xw, index=False, sheet_name="Summary")
        to_flat_tasks_df([d]).to_excel(xw, index=False, sheet_name="Tasks")
    return buf.getvalue()


# ------------------------------------------------------------------------------
# Filtering + deletion
# ------------------------------------------------------------------------------
def filter_deliverables(all_items: List[Deliverable]) -> List[Deliverable]:
    f = st.session_state["filters"]
    q = f["q"].lower().strip()
    pr = f["priority"]
    ow = f["owner"]

    def match(d: Deliverable) -> bool:
        if q and (q not in d["title"].lower() and q not in d["unit"].lower() and q not in d["owner"].lower()):
            return False
        if pr != "All" and d["priority"] != pr:
            return False
        if ow != "All" and d["owner"] != ow:
            return False
        return True

    return [d for d in all_items if match(d)]

def delete_by_ids(ids: List[str]):
    st.session_state["deliverables"] = [d for d in st.session_state["deliverables"] if d["id"] not in ids]


# ------------------------------------------------------------------------------
# Create form (wrapped in visibility flag)
# ------------------------------------------------------------------------------
def create_form():
    with st.form("new_deliverable", clear_on_submit=True):
        st.subheader("Create deliverable")
        c1, c2, c3, c4 = st.columns([2, 2, 1.3, 2])

        unit = c1.text_input("Unit", placeholder="e.g., DGCC")
        title = c2.text_input("Deliverable title", placeholder="Brief title")
        owner = c3.text_input("Owner", placeholder="Name/role")
        priority = c4.selectbox("Priority", ["Low", "Medium", "High", "Critical"])

        notes = st.text_area("Notes (deliverable)", placeholder="Optional notes / description", height=90)

        st.markdown("---")
        st.caption("Add up to 5 tasks. Leave a task title empty to skip that row.")
        tasks: List[Task] = []
        for i in range(5):
            tr = task_row_form(i)
            if tr:
                tasks.append(tr)

        submitted = st.form_submit_button("Save deliverable")
        if submitted:
            if not title.strip():
                st.error("Deliverable title is required.")
                return
            new_d = build_deliverable(unit, title, owner, priority, notes, tasks)
            st.session_state["deliverables"].append(new_d)
            st.success("Deliverable added.")
            st.session_state["show_new_form"] = False
            st.rerun()


# ------------------------------------------------------------------------------
# UI renderers
# ------------------------------------------------------------------------------
def render_header():
    st.markdown("## 📝 DGCC Follow-up (clean)")
    st.caption("Create organized deliverables with up to five tasks each, export summaries, and keep your semester page compact.")

    # Primary controls row
    c1, c2, c3, c4 = st.columns([2, 2, 1.5, 2])
    c1.button("➕ Add another deliverable", key="add_top", on_click=lambda: st.session_state.update(show_new_form=True))

    # Filters
    with c2:
        st.text_input("Search (unit/title/owner)", key=("filters", "q".split())[-1] if False else "filters_q",
                      value=st.session_state["filters"]["q"],
                      on_change=lambda: st.session_state["filters"].update(q=st.session_state["filters_q"]))
    with c3:
        st.selectbox("Priority", ["All", "Low", "Medium", "High", "Critical"], key="filters_prio",
                     index=["All","Low","Medium","High","Critical"].index(st.session_state["filters"]["priority"]),
                     on_change=lambda: st.session_state["filters"].update(priority=st.session_state["filters_prio"]))
    with c4:
        # Owners list from current data
        owners = sorted({d["owner"] for d in st.session_state["deliverables"] if d["owner"]}) or []
        opts = ["All"] + owners
        chosen = st.selectbox("Owner", opts,
                              index=opts.index(st.session_state["filters"]["owner"]) if st.session_state["filters"]["owner"] in opts else 0)
        st.session_state["filters"]["owner"] = chosen

    st.markdown("---")


def render_table_and_global_actions(filtered: List[Deliverable]):
    # Compact table toggle
    compact = st.toggle("Compact table view", value=True, help="Show a simple summary table below.")

    # Global downloads row
    colA, colB, colC = st.columns([1.2, 1.2, 2])
    summary_df = to_summary_df(filtered)
    flat_df = to_flat_tasks_df(filtered)

    csv_summary = summary_df.to_csv(index=False).encode("utf-8")
    csv_flat = flat_df.to_csv(index=False).encode("utf-8")

    colA.download_button("⬇️ All (Summary)", data=csv_summary, file_name="dgcc_followup_summary.csv", mime="text/csv")
    colB.download_button("⬇️ All (Flattened tasks)", data=csv_flat, file_name="dgcc_followup_tasks.csv", mime="text/csv")

    with colC:
        if st.button("🗑️ Delete ALL filtered"):
            if filtered:
                st.session_state["ask_delete_filtered"] = True
            else:
                st.info("Nothing matches the current filter.")

        if confirm_modal("Delete all filtered deliverables? This cannot be undone.", "ask_delete_filtered"):
            delete_by_ids([d["id"] for d in filtered])
            st.success("Filtered deliverables deleted.")
            st.rerun()

    if compact:
        st.dataframe(
            summary_df[["Created","Unit","Title","Owner","Priority","Tasks_count","Hours_total"]],
            use_container_width=True,
            hide_index=True,
        )


def render_deliverable_card(d: Deliverable):
    with st.expander(f"📦 {d['title']}  —  {d['unit']}  •  {d['owner']}  •  {d['priority']}"):
        st.caption(f"ID: `{d['id']}` · created {d['created']}")
        st.markdown(f"**Notes:** {d['notes'] or '*—*'}")

        # Tasks table (pretty)
        if d["tasks"]:
            df = pd.DataFrame(d["tasks"])
            df = df.rename(columns={
                "title": "Task",
                "has_due": "Has due?",
                "due": "Due",
                "status": "Status",
                "hours": "Hours",
                "notes": "Notes",
            })
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No tasks added.")

        # Per-deliverable downloads and delete
        c1, c2, c3 = st.columns([1.2, 1.2, 1.2])
        csv_summary = to_summary_df([d]).to_csv(index=False).encode("utf-8")
        xls = excel_for_deliverable(d)

        c1.download_button("⬇️ Summary (CSV)", data=csv_summary, file_name=f"{d['title'][:20]}_summary.csv", mime="text/csv")
        c2.download_button("⬇️ Full workbook (Excel)", data=xls, file_name=f"{d['title'][:20]}_workbook.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if c3.button("🗑️ Delete this deliverable", key=f"del_{d['id']}"):
            st.session_state[f"ask_del_{d['id']}"] = True

        if confirm_modal(f"Delete deliverable “{d['title']}”? This cannot be undone.", f"ask_del_{d['id']}"):
            delete_by_ids([d["id"]])
            st.success("Deliverable deleted.")
            st.rerun()


def main():
    # Header / filters and top "Add" button
    render_header()

    # Create form (visible when toggled)
    if st.session_state["show_new_form"]:
        create_form()
    else:
        st.caption("Click **➕ Add another deliverable** to create a new one.")

    st.markdown("### Deliverables")

    all_items = st.session_state["deliverables"]
    filtered = filter_deliverables(all_items)

    # Global actions & compact table
    render_table_and_global_actions(filtered)

    # Collapsible cards
    if not filtered:
        st.info("No deliverables match the current filter. Use the form above to add one.")
    else:
        for d in filtered:
            render_deliverable_card(d)

    # Bottom "Add" button
    st.divider()
    st.button("➕ Add another deliverable", key="add_bottom", on_click=lambda: st.session_state.update(show_new_form=True))


if __name__ == "__main__":
    main()
