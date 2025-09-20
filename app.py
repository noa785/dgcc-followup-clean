# app.py — DGCC Follow-up (clean, single-file, organized)

import io
import uuid
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
# Page setup
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="DGCC Follow-up — Clean", page_icon="📝", layout="wide")
st.title("📝 DGCC Follow-up — Clean")

# Session defaults
if "deliverables" not in st.session_state:
    st.session_state["deliverables"] = []  # list[dict]

if "show_new_form" not in st.session_state:
    st.session_state["show_new_form"] = True


# ─────────────────────────────────────────────────────────────────────────────
# Helpers: id, modal confirm, exports, persistence
# ─────────────────────────────────────────────────────────────────────────────
def generate_id() -> str:
    """Small, URL-safe id snippet."""
    return uuid.uuid4().hex[:10]


def _show_form():
    st.session_state["show_new_form"] = True


def _hide_form():
    st.session_state["show_new_form"] = False


def confirm_modal(prompt: str, state_key: str, match_id: str | None = None) -> bool:
    """
    Open a confirmation modal when st.session_state[state_key] is truthy.
    If match_id is given, we only confirm when the stored value equals match_id.
    Returns True when user clicks Yes.
    """
    current = st.session_state.get(state_key)
    if current is None or current is False:
        return False

    if match_id is not None and current != match_id:
        return False

    with st.modal("Confirm action"):
        st.warning(prompt)
        c1, c2 = st.columns(2)
        yes = c1.button("✅ Yes, do it")
        no = c2.button("❌ Cancel")

        if yes:
            st.session_state[state_key] = None
            return True
        if no:
            st.session_state[state_key] = None
            st.rerun()

    return False


def save_deliverable(deliv: Dict) -> None:
    """Append or replace by id."""
    items = st.session_state["deliverables"]
    idx = next((i for i, d in enumerate(items) if d["id"] == deliv["id"]), None)
    if idx is None:
        items.append(deliv)
    else:
        items[idx] = deliv


def delete_deliverable(deliv_id: str) -> None:
    st.session_state["deliverables"] = [
        d for d in st.session_state["deliverables"] if d["id"] != deliv_id
    ]


def delete_all() -> None:
    st.session_state["deliverables"] = []


def tasks_to_dataframe(tasks: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(tasks) if tasks else pd.DataFrame(
        columns=["row", "title", "status", "priority", "hours", "due_date", "notes"]
    )
    # order columns nicely if they exist
    cols = ["row", "title", "status", "priority", "hours", "due_date", "notes"]
    df = df[[c for c in cols if c in df.columns]]
    return df


def export_summary_csv(deliv: Dict) -> bytes:
    """CSV with a compact task list for one deliverable."""
    df = tasks_to_dataframe(deliv.get("tasks", []))
    # include deliverable id/title in the first row as metadata
    meta = pd.DataFrame(
        [{"deliverable_id": deliv["id"], "deliverable_title": deliv["title"]}]
    )
    out = io.StringIO()
    meta.to_csv(out, index=False)
    out.write("\n")
    df.to_csv(out, index=False)
    return out.getvalue().encode("utf-8")


def export_full_xlsx(deliv: Dict) -> bytes:
    """Workbook with Deliverable sheet + Tasks sheet."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as xw:
        # Deliverable
        pd.DataFrame([{
            "id": deliv["id"],
            "title": deliv["title"],
            "owner": deliv.get("owner", ""),
            "unit": deliv.get("unit", ""),
            "created_at": deliv.get("created_at", ""),
            "notes": deliv.get("notes", ""),
        }]).to_excel(xw, sheet_name="Deliverable", index=False)

        # Tasks
        df_tasks = tasks_to_dataframe(deliv.get("tasks", []))
        df_tasks.to_excel(xw, sheet_name="Tasks", index=False)

    output.seek(0)
    return output.read()


def export_all_summary_csv(deliverables: List[Dict]) -> bytes:
    """All deliverables in a two-part CSV: header rows + tasks for each."""
    out = io.StringIO()
    first = True
    for d in deliverables:
        meta = pd.DataFrame(
            [{"deliverable_id": d["id"], "deliverable_title": d["title"]}]
        )
        if not first:
            out.write("\n")
        meta.to_csv(out, index=False)
        out.write("\n")
        tasks_to_dataframe(d.get("tasks", [])).to_csv(out, index=False)
        first = False
    return out.getvalue().encode("utf-8")


def export_all_flattened_csv(deliverables: List[Dict]) -> bytes:
    """
    One big flat table: one row per task with deliverable columns repeated.
    """
    rows: List[Dict] = []
    for d in deliverables:
        common = {
            "deliverable_id": d["id"],
            "deliverable_title": d["title"],
            "owner": d.get("owner", ""),
            "unit": d.get("unit", ""),
            "created_at": d.get("created_at", ""),
        }
        tasks = d.get("tasks", [])
        if not tasks:
            # include a blank line to represent deliverable without tasks
            rows.append({**common})
        else:
            for t in tasks:
                r = {**common}
                for k in ["row", "title", "status", "priority", "hours", "due_date", "notes"]:
                    r[k] = t.get(k)
                rows.append(r)

    df = pd.DataFrame(rows)
    out = io.StringIO()
    df.to_csv(out, index=False)
    return out.getvalue().encode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Build tasks from form rows
# ─────────────────────────────────────────────────────────────────────────────
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
        "hours": float(hours) if hours not in (None, "") else None,
        "due_date": due if has_due else None,
        "priority": priority,
        "notes": (notes or "").strip(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# UI: Create deliverable form (5 task rows)
# ─────────────────────────────────────────────────────────────────────────────
def create_deliverable_form():
    with st.form("new_deliverable", clear_on_submit=True):
        st.subheader("Create deliverable")

        # Deliverable fields
        d_title = st.text_input("Deliverable title *")
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            d_owner = st.text_input("Owner")
        with c2:
            d_unit = st.text_input("Unit")
        with c3:
            d_notes = st.text_area("Deliverable notes", height=80)

        st.markdown("### Tasks (up to 5)")
        status_opts = ["Not started", "In progress", "Blocked", "Done"]
        prio_opts = ["Low", "Medium", "High"]

        # Gather 5 tasks in a loop to avoid repetition
        task_widgets: List[Tuple] = []
        for i in range(1, 6):
            st.markdown(f"#### Task {i}")
            t_title = st.text_input(f"Task {i} — title", key=f"t{i}_title")
            cc1, cc2, cc3, cc4 = st.columns([1, 1, 1, 1])
            with cc1:
                t_status = st.selectbox("Status", status_opts, key=f"t{i}_status")
            with cc2:
                t_prio = st.selectbox("Priority", prio_opts, key=f"t{i}_prio")
            with cc3:
                t_has_due = st.checkbox("Has due date?", key=f"t{i}_has_due")
                t_due = st.date_input("Due date", disabled=not t_has_due, key=f"t{i}_due")
            with cc4:
                t_hours = st.number_input("Hours", min_value=0.0, step=0.5, key=f"t{i}_hours")
            t_notes = st.text_area(f"Notes {i}", height=60, key=f"t{i}_notes")

            task_widgets.append(
                (i, t_title, t_status, t_hours, t_has_due, t_due, t_notes, t_prio)
            )

        submitted = st.form_submit_button("Save deliverable")

        if submitted:
            if not d_title.strip():
                st.error("Please enter a deliverable title.")
                st.stop()

            tasks: List[Dict] = []
            for (i, a, b, c, d, e, f, g) in task_widgets:
                row = build_task(i, a, b, c, d, e, f, g)
                if row:
                    tasks.append(row)

            new_deliv = {
                "id": generate_id(),
                "title": d_title.strip(),
                "owner": d_owner.strip(),
                "unit": d_unit.strip(),
                "notes": d_notes.strip(),
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                "tasks": tasks,
            }
            save_deliverable(new_deliv)
            st.success("Deliverable added.")
            _hide_form()


# ─────────────────────────────────────────────────────────────────────────────
# UI: Render deliverable card (expander)
# ─────────────────────────────────────────────────────────────────────────────
def show_deliverable_card(deliv: Dict):
    with st.expander(f"📦 {deliv['title']} — {deliv.get('owner','')}", expanded=False):
        st.caption(f"ID: `{deliv['id']}` · created {deliv.get('created_at','')}")
        if deliv.get("notes"):
            st.markdown(f"**Notes:** {deliv['notes']}")

        tasks = deliv.get("tasks", []) or []
        if not tasks:
            st.info("No tasks added.")
        else:
            df = tasks_to_dataframe(tasks).rename(columns={"row": "#", "title": "Task", "due_date": "Due"})
            st.dataframe(df, use_container_width=True, hide_index=True)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button(
                "⬇️ Summary (CSV)",
                data=export_summary_csv(deliv),
                file_name=f"{deliv['title']}_summary.csv",
                mime="text/csv",
            )
        with c2:
            st.download_button(
                "⬇️ Full workbook (Excel)",
                data=export_full_xlsx(deliv),
                file_name=f"{deliv['title']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with c3:
            if st.button("🗑️ Delete this deliverable", key=f"del_{deliv['id']}"):
                st.session_state["ask_delete_one"] = deliv["id"]

        if confirm_modal(
            f"Delete deliverable “{deliv['title']}”? This cannot be undone.",
            "ask_delete_one",
            match_id=deliv["id"],
        ):
            delete_deliverable(deliv["id"])
            st.success("Deliverable deleted.")
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Main layout
# ─────────────────────────────────────────────────────────────────────────────
# Top add button
st.button("➕ Add another deliverable", on_click=_show_form, key="add_top")

# Create form (toggleable)
if st.session_state["show_new_form"]:
    create_deliverable_form()
else:
    st.caption("Click **➕ Add another deliverable** to create a new one.")

st.divider()

# Deliverables section
st.subheader("Deliverables")

items = st.session_state["deliverables"]

# Global actions row
g1, g2, g3 = st.columns([1, 1, 1])
with g1:
    st.download_button(
        "⬇️ All (Summary)",
        data=export_all_summary_csv(items),
        file_name="dgcc_followup_all_summary.csv",
        mime="text/csv",
        disabled=not items,
    )
with g2:
    st.download_button(
        "⬇️ All (Flattened)",
        data=export_all_flattened_csv(items),
        file_name="dgcc_followup_all_flattened.csv",
        mime="text/csv",
        disabled=not items,
    )
with g3:
    if st.button("🗑️ Delete ALL", disabled=not items):
        st.session_state["ask_delete_all"] = True

if confirm_modal("Delete ALL deliverables? This cannot be undone.", "ask_delete_all"):
    delete_all()
    st.success("All deliverables deleted.")
    st.rerun()

st.markdown("")  # small gap

if not items:
    st.info("No deliverables yet. Use the form above to add one.")
else:
    for d in items:
        show_deliverable_card(d)

# Bottom add button for long pages
st.divider()
st.button("➕ Add another deliverable", on_click=_show_form, key="add_bottom")
