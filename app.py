# app.py — DGCC Follow-up (clean, single-file)
# -------------------------------------------------
# Features:
# • Clean form: Deliverable + up to 5 tasks, with optional due-date picker per task
# • Divider between Notes and Tasks; visual separation per task row
# • "➕ Add another deliverable" button shown in two places
# • Deliverables displayed as collapsible cards (expanders)
# • Per-deliverable downloads:
#      - Summary (CSV)
#      - Full Excel workbook (Deliverable meta + Tasks + Summary)
# • Global downloads (top of page):
#      - ALL tasks across deliverables (CSV)
#      - GLOBAL summary (CSV)
#      - Full Excel workbook of everything
# • Uses st.session_state to persist across reruns (no experimental_rerun)

from __future__ import annotations

import io
from uuid import uuid4
from typing import List, Dict, Any, Optional
from datetime import date

import pandas as pd
import streamlit as st


# ---------- Session bootstrap ----------
def _init_state() -> None:
    if "deliverables" not in st.session_state:
        # List[Dict] – each deliverable dict has: id, unit, title, time, notes, tasks (list)
        st.session_state.deliverables: List[Dict[str, Any]] = []
    if "form_seed" not in st.session_state:
        # bump this to clear form fields after a successful add
        st.session_state.form_seed = str(uuid4())


_init_state()


# ---------- Helpers ----------
TASK_STATUSES = ["Not started", "In progress", "Blocked", "Done"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]


def _task_row(idx: int) -> Dict[str, Any]:
    """Render a single task row (idx 1..5) and return values."""
    st.markdown(f"**Task {idx}**")
    title = st.text_input(f"Title {idx}", key=f"title_{idx}_{st.session_state.form_seed}")

    cols = st.columns([1, 1, 1, 1])
    with cols[0]:
        has_due = st.checkbox("Has due date?", key=f"has_due_{idx}_{st.session_state.form_seed}")
        due = st.date_input(
            "Due date",
            value=date.today(),
            key=f"due_{idx}_{st.session_state.form_seed}",
            disabled=not has_due,
        )
        due_value: Optional[date] = due if has_due else None

    with cols[1]:
        priority = st.selectbox(
            "Priority",
            PRIORITIES,
            index=1,
            key=f"prio_{idx}_{st.session_state.form_seed}",
        )

    with cols[2]:
        status = st.selectbox(
            "Status",
            TASK_STATUSES,
            index=0,
            key=f"status_{idx}_{st.session_state.form_seed}",
        )

    with cols[3]:
        hours = st.number_input(
            "Hours (+)", min_value=0.0, step=0.5, value=0.0, key=f"hours_{idx}_{st.session_state.form_seed}"
        )

    notes = st.text_area(f"Notes {idx}", key=f"notes_{idx}_{st.session_state.form_seed}")
    st.divider()
    return {
        "title": title.strip(),
        "has_due": has_due,
        "due_date": due_value.isoformat() if due_value else None,
        "priority": priority,
        "status": status,
        "hours": float(hours),
        "notes": notes.strip(),
    }


def _deliverable_to_frames(d: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
    """Build DataFrames for a deliverable."""
    # Deliverable metadata (single-row)
    meta_df = pd.DataFrame(
        [
            {
                "deliverable_id": d["id"],
                "deliverable_title": d["title"],
                "unit": d["unit"],
                "time": d["time"],
                "notes": d["notes"],
                "num_tasks": len(d["tasks"]),
                "total_hours": sum(t.get("hours", 0.0) or 0.0 for t in d["tasks"]),
            }
        ]
    )

    # Tasks for this deliverable
    tasks_rows = []
    for i, t in enumerate(d["tasks"], 1):
        tasks_rows.append(
            {
                "deliverable_id": d["id"],
                "deliverable_title": d["title"],
                "task_idx": i,
                "task_title": t.get("title", ""),
                "has_due": t.get("has_due", False),
                "due_date": t.get("due_date"),
                "priority": t.get("priority", ""),
                "status": t.get("status", ""),
                "hours": t.get("hours", 0.0),
                "notes": t.get("notes", ""),
            }
        )
    tasks_df = pd.DataFrame(tasks_rows)

    # Summary for convenience
    summary_df = meta_df[
        ["deliverable_id", "deliverable_title", "unit", "time", "num_tasks", "total_hours"]
    ].copy()
    return {"meta": meta_df, "tasks": tasks_df, "summary": summary_df}


def _all_tasks_and_summary() -> Dict[str, pd.DataFrame]:
    """Flatten all deliverables into global tasks and summary frames."""
    all_tasks: List[pd.DataFrame] = []
    all_summary: List[pd.DataFrame] = []
    for d in st.session_state.deliverables:
        frames = _deliverable_to_frames(d)
        if not frames["tasks"].empty:
            all_tasks.append(frames["tasks"])
        all_summary.append(frames["summary"])

    tasks_df = pd.concat(all_tasks, ignore_index=True) if all_tasks else pd.DataFrame(
        columns=[
            "deliverable_id",
            "deliverable_title",
            "task_idx",
            "task_title",
            "has_due",
            "due_date",
            "priority",
            "status",
            "hours",
            "notes",
        ]
    )
    summary_df = pd.concat(all_summary, ignore_index=True) if all_summary else pd.DataFrame(
        columns=["deliverable_id", "deliverable_title", "unit", "time", "num_tasks", "total_hours"]
    )
    return {"tasks": tasks_df, "summary": summary_df}


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def _deliverable_xlsx_bytes(d: Dict[str, Any]) -> bytes:
    """Excel workbook (Deliverable) with 3 sheets: Meta, Tasks, Summary."""
    frames = _deliverable_to_frames(d)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        frames["meta"].to_excel(xw, sheet_name="Deliverable", index=False)
        frames["tasks"].to_excel(xw, sheet_name="Tasks", index=False)
        frames["summary"].to_excel(xw, sheet_name="Summary", index=False)
    buf.seek(0)
    return buf.read()


def _global_xlsx_bytes() -> bytes:
    """Excel workbook of EVERYTHING."""
    frames = _all_tasks_and_summary()
    meta_rows = []
    for d in st.session_state.deliverables:
        meta_rows.append(_deliverable_to_frames(d)["meta"].iloc[0].to_dict())
    meta_df = pd.DataFrame(meta_rows)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        meta_df.to_excel(xw, sheet_name="Deliverables", index=False)
        frames["tasks"].to_excel(xw, sheet_name="AllTasks", index=False)
        frames["summary"].to_excel(xw, sheet_name="GlobalSummary", index=False)
    buf.seek(0)
    return buf.read()


# ---------- UI: Header & Global downloads ----------
st.set_page_config(page_title="DGCC Follow-up Manager", page_icon="✅", layout="wide")
st.title("✅ DGCC Follow-up Manager")

c1, c2, c3, c4 = st.columns([1.6, 1.2, 1.2, 1.2])
with c1:
    st.caption("Quick global exports")
with c2:
    all_frames = _all_tasks_and_summary()
    st.download_button(
        "⬇️ All tasks (CSV)",
        data=_df_to_csv_bytes(all_frames["tasks"]),
        file_name="all_tasks.csv",
        mime="text/csv",
        use_container_width=True,
    )
with c3:
    st.download_button(
        "⬇️ Global summary (CSV)",
        data=_df_to_csv_bytes(all_frames["summary"]),
        file_name="global_summary.csv",
        mime="text/csv",
        use_container_width=True,
    )
with c4:
    st.download_button(
        "⬇️ Everything (Excel)",
        data=_global_xlsx_bytes(),
        file_name="followup_all.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

st.divider()

# ---------- Create form ----------
st.subheader("Create a deliverable")

with st.form(key=f"create_deliverable_{st.session_state.form_seed}", clear_on_submit=False):
    d_cols = st.columns([1, 1, 2, 1])
    with d_cols[0]:
        unit = st.text_input("Unit")
    with d_cols[1]:
        time_str = st.text_input("Time (optional)")
    with d_cols[2]:
        d_title = st.text_input("Deliverable title", placeholder="e.g. Student Reports Batch 3")
    with d_cols[3]:
        st.write("")  # spacer
        st.write("")  # spacer

    notes = st.text_area("Notes (optional)")

    st.markdown("###### Tasks (up to 5)")
    st.info("Leave a task title empty to skip that row.", icon="ℹ️")

    tasks: List[Dict[str, Any]] = []
    # render 5 task rows; empty titles are ignored later
    for i in range(1, 6):
        tasks.append(_task_row(i))

    submitted = st.form_submit_button("➕ Add deliverable")

if submitted:
    # Keep only tasks that have a title
    valid_tasks = [t for t in tasks if t["title"]]
    new_deliv = {
        "id": str(uuid4()),
        "unit": unit.strip(),
        "title": d_title.strip(),
        "time": time_str.strip(),
        "notes": notes.strip(),
        "tasks": valid_tasks,
    }
    if not new_deliv["title"]:
        st.error("Deliverable title is required.")
    else:
        st.session_state.deliverables.append(new_deliv)
        st.success(f"Deliverable added: **{new_deliv['title']}** with {len(valid_tasks)} task(s).")
        # reset inputs (fresh keys)
        st.session_state.form_seed = str(uuid4())
        st.experimental_rerun()

# Quick add button just under the form too
st.button("➕ Add another deliverable", key="add_again_top")

st.divider()

# ---------- Listing of Deliverables ----------
st.subheader("Deliverables")

if not st.session_state.deliverables:
    st.warning("No deliverables yet. Use the form above to add one.", icon="📝")
else:
    for d in st.session_state.deliverables:
        frames = _deliverable_to_frames(d)
        with st.expander(f"📦 {d['title']} — {d['unit'] or 'No unit'}  |  Tasks: {len(d['tasks'])}  |  Hours: {frames['summary'].total_hours.iloc[0]}"):
            meta_cols = st.columns([1, 1, 2])
            with meta_cols[0]:
                st.write(f"**Unit:** {d['unit'] or '—'}")
                st.write(f"**Time:** {d['time'] or '—'}")
            with meta_cols[1]:
                st.write(f"**Total tasks:** {len(d['tasks'])}")
                st.write(f"**Total hours:** {frames['summary'].total_hours.iloc[0]}")
            with meta_cols[2]:
                st.write(f"**Notes:** {d['notes'] or '—'}")

            st.markdown("**Tasks**")
            if frames["tasks"].empty:
                st.caption("_No tasks in this deliverable._")
            else:
                # nice display order
                show_cols = [
                    "task_idx",
                    "task_title",
                    "priority",
                    "status",
                    "has_due",
                    "due_date",
                    "hours",
                    "notes",
                ]
                st.dataframe(frames["tasks"][show_cols], use_container_width=True, hide_index=True)

            # Per-deliverable downloads
            cdl1, cdl2, cdl3 = st.columns([1, 1, 5])
            with cdl1:
                st.download_button(
                    "⬇️ Summary (CSV)",
                    data=_df_to_csv_bytes(frames["summary"]),
                    file_name=f"{d['title']}_summary.csv".replace(" ", "_"),
                    mime="text/csv",
                    use_container_width=True,
                )
            with cdl2:
                st.download_button(
                    "⬇️ Full workbook (Excel)",
                    data=_deliverable_xlsx_bytes(d),
                    file_name=f"{d['title']}_full.xlsx".replace(" ", "_"),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

st.divider()
st.button("➕ Add another deliverable", key="add_again_bottom")
