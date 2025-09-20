# app.py — DGCC Follow-up (clean, scalable)

import io
import math
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional

import pandas as pd
import streamlit as st


# ---------------------------
# Page/State helpers
# ---------------------------
st.set_page_config(page_title="DGCC Follow-up", page_icon="📝", layout="wide")


def _ensure_state():
    """Initialize session state containers."""
    if "deliverables" not in st.session_state:
        st.session_state["deliverables"] = []  # list[dict]
    if "ui" not in st.session_state:
        st.session_state["ui"] = {}
    st.session_state["ui"].setdefault("expanded_cards", False)
    st.session_state["ui"].setdefault("form_rows", 5)  # default tasks per deliverable


# ---------------------------
# Utility: Excel bytes
# ---------------------------
def _df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Return an Excel (xlsx) file bytes from a DataFrame."""
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    bio.seek(0)
    return bio.read()


# ---------------------------
# Deliverable schema helpers
# ---------------------------
PRIORITY_CHOICES = ["High", "Medium", "Low"]
STATUS_CHOICES = ["Todo", "In progress", "Blocked", "Done"]

TASK_COLUMNS = [
    "title", "status", "hours", "category", "subcategory",
    "has_start_date", "start_date", "has_due_date", "due_date", "notes"
]


def make_empty_task() -> Dict[str, Any]:
    return {
        "title": "",
        "status": "Todo",
        "hours": 0.0,
        "category": "",
        "subcategory": "",
        "has_start_date": False,
        "start_date": None,
        "has_due_date": False,
        "due_date": None,
        "notes": "",
    }


def normalize_task(t: Dict[str, Any]) -> Dict[str, Any]:
    """Clean a task dict (coerce types & drop empty)."""
    out = dict(t)
    out["title"] = (out.get("title") or "").strip()
    out["status"] = out.get("status") or "Todo"
    out["hours"] = float(out.get("hours") or 0)
    out["category"] = (out.get("category") or "").strip()
    out["subcategory"] = (out.get("subcategory") or "").strip()
    out["notes"] = (out.get("notes") or "").strip()

    # Dates
    if not out.get("has_start_date"):
        out["start_date"] = None
    if not out.get("has_due_date"):
        out["due_date"] = None

    # Keep row only if it has a title (your "skip empty row" rule)
    return out


def deliverable_summary_row(idx: int, d: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten deliverable -> one summary row."""
    due = d.get("due_date")
    due_str = due.strftime("%Y-%m-%d") if isinstance(due, (date, datetime)) else ""
    open_tasks = sum(
        1 for t in d.get("tasks", [])
        if str(t.get("status", "")).lower() not in {"done", "closed", "complete"}
    )
    total_hours = sum(float(t.get("hours", 0) or 0) for t in d.get("tasks", []))
    return {
        "ID": idx,
        "Title": d.get("title", "").strip(),
        "Owner": d.get("owner", ""),
        "Unit": d.get("unit", ""),
        "Priority": d.get("priority", ""),
        "Has due date": bool(d.get("has_due_date", False)),
        "Due": due_str,
        "Open tasks": open_tasks,
        "Total hours": total_hours,
        "Notes": (d.get("notes", "") or "").strip(),
    }


def summary_dataframe(deliverables: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = [deliverable_summary_row(i + 1, d) for i, d in enumerate(deliverables)]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    cols = ["ID", "Title", "Owner", "Unit", "Priority",
            "Has due date", "Due", "Open tasks", "Total hours", "Notes"]
    return df[cols]


# ---------------------------
# CREATE FORM
# ---------------------------
def create_deliverable_form():
    st.header("Create deliverable")
    _ensure_state()

    form_rows = st.session_state["ui"]["form_rows"]

    with st.form("create_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns([2, 1.2, 1, 1])

        title = c1.text_input("Deliverable title*", "")
        owner = c2.text_input("Owner", "")
        unit = c3.text_input("Unit", "")
        priority = c4.selectbox("Priority", PRIORITY_CHOICES, index=1)

        has_due = st.checkbox("Has due date?", value=False)
        due_date = None
        dd_col = st.container()
        if has_due:
            due_date = st.date_input("Due date", value=None)

        notes = st.text_area("Notes", placeholder="Optional notes for this deliverable")

        st.divider()
        st.subheader("Tasks")
        st.caption("Tip: Only fill the rows you need; empty task titles are ignored.")

        # Render task rows
        tasks = []
        for i in range(form_rows):
            with st.container(border=True):
                st.markdown(f"**Task {i+1}**")
                t1, t2, t3 = st.columns([2, 1, 1])
                title_i = t1.text_input("Title", key=f"task_title_{i}")
                status_i = t2.selectbox("Status", STATUS_CHOICES, key=f"task_status_{i}")
                hours_i = t3.number_input("Hours", min_value=0.0, step=0.5, key=f"task_hours_{i}")

                t4, t5 = st.columns([1, 1])
                cat_i = t4.text_input("Category", key=f"task_cat_{i}")
                subcat_i = t5.text_input("Subcategory", key=f"task_subcat_{i}")

                t6, t7 = st.columns([1, 1])
                has_start_i = t6.checkbox("Has start date?", key=f"task_has_start_{i}")
                start_i = t6.date_input("Start date", key=f"task_start_{i}") if has_start_i else None

                has_due_i = t7.checkbox("Has due date?", key=f"task_has_due_{i}")
                due_i = t7.date_input("Due date", key=f"task_due_{i}") if has_due_i else None

                notes_i = st.text_area("Notes", key=f"task_notes_{i}", placeholder="", height=60)

                tasks.append(normalize_task({
                    "title": title_i, "status": status_i, "hours": hours_i,
                    "category": cat_i, "subcategory": subcat_i,
                    "has_start_date": has_start_i, "start_date": start_i,
                    "has_due_date": has_due_i, "due_date": due_i,
                    "notes": notes_i
                }))

        # Keep only tasks with a title
        tasks = [t for t in tasks if t["title"]]

        left, mid, right = st.columns([1, 1, 2])
        with left:
            add_rows = st.number_input("Rows", min_value=1, max_value=20, value=form_rows, step=1)
        with mid:
            if st.form_submit_button("Apply rows"):
                st.session_state["ui"]["form_rows"] = int(add_rows)
                st.rerun()
        with right:
            saved = st.form_submit_button("➕ Add deliverable", type="primary")

    if saved:
        if not title.strip():
            st.error("Please enter a deliverable title.")
            return

        d = {
            "title": title.strip(),
            "owner": owner.strip(),
            "unit": unit.strip(),
            "priority": priority,
            "has_due_date": has_due,
            "due_date": due_date if has_due else None,
            "notes": notes.strip(),
            "tasks": tasks,
            "created_at": datetime.now()
        }
        st.session_state["deliverables"].append(d)
        st.success(f"Added deliverable: **{title.strip()}**")
        st.toast("Deliverable saved", icon="✅")


# ---------------------------
# FILTERS / SORT
# ---------------------------
def apply_filters(delivs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    st.sidebar.markdown("### Filters")

    q = st.sidebar.text_input("Search title/notes/owner", placeholder="Type to filter…").strip().lower()

    priorities = sorted({(d.get("priority") or "").strip() for d in delivs if d.get("priority")})
    prio_filter = st.sidebar.multiselect("Priority", priorities, default=[])

    only_open = st.sidebar.checkbox("Only with open tasks", value=False)

    due_choice = st.sidebar.selectbox(
        "Due window",
        ["All", "Overdue", "Due this week", "Due this month", "No due date"]
    )

    def in_due_window(d: Dict[str, Any]) -> bool:
        if due_choice == "All":
            return True
        due = d.get("due_date")
        has = bool(d.get("has_due_date") and isinstance(due, (date, datetime)))
        if due_choice == "No due date":
            return not has
        if not has:
            return False
        today = date.today()
        if due_choice == "Overdue":
            return due < today
        if due_choice == "Due this week":
            end = today + timedelta(days=7)
            return today <= due <= end
        if due_choice == "Due this month":
            end_month = (date(today.year + (today.month // 12), (today.month % 12) + 1, 1) - timedelta(days=1))
            return today <= due <= end_month
        return True

    out = []
    for d in delivs:
        text = " ".join([d.get("title", ""), d.get("notes", ""), d.get("owner", ""), d.get("unit", "")]).lower()
        if q and q not in text:
            continue
        if prio_filter and (d.get("priority") or "") not in prio_filter:
            continue
        if only_open:
            open_tasks = any(str(t.get("status", "")).lower() not in {"done", "closed", "complete"} for t in d.get("tasks", []))
            if not open_tasks:
                continue
        if not in_due_window(d):
            continue
        out.append(d)
    return out


def sort_deliverables(delivs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    st.sidebar.markdown("### Sort")
    sort_by = st.sidebar.selectbox("Sort by", ["Due date", "Priority", "Title", "Owner", "Created order"])
    reverse = st.sidebar.checkbox("Descending", value=False)

    if sort_by == "Created order":
        return list(reversed(delivs)) if reverse else delivs

    if sort_by == "Due date":
        def keyfn(d):
            due = d.get("due_date")
            return (0, due) if d.get("has_due_date") and isinstance(due, (date, datetime)) else (1, date.max)
    elif sort_by == "Priority":
        order = {"High": 0, "Medium": 1, "Low": 2}
        keyfn = lambda d: order.get(d.get("priority", ""), 99)
    elif sort_by == "Title":
        keyfn = lambda d: d.get("title", "").lower()
    else:
        keyfn = lambda d: d.get("owner", "").lower()

    return sorted(delivs, key=keyfn, reverse=reverse)


# ---------------------------
# DOWNLOADS
# ---------------------------
def download_summary_button(delivs: List[Dict[str, Any]], filename: str, key: str):
    df = summary_dataframe(delivs)
    st.download_button(
        "Save file",
        data=_df_to_excel_bytes(df),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key
    )


def download_flattened_button(delivs: List[Dict[str, Any]], filename: str, key: str):
    flat = []
    for i, d in enumerate(delivs, start=1):
        if d.get("tasks"):
            for t in d["tasks"]:
                row = {"Deliverable ID": i, "Deliverable": d.get("title", ""), **t}
                # Normalize dates
                if isinstance(row.get("start_date"), (date, datetime)):
                    row["start_date"] = row["start_date"].strftime("%Y-%m-%d")
                if isinstance(row.get("due_date"), (date, datetime)):
                    row["due_date"] = row["due_date"].strftime("%Y-%m-%d")
                flat.append(row)
        else:
            flat.append({"Deliverable ID": i, "Deliverable": d.get("title", "")})
    df = pd.DataFrame(flat)
    st.download_button(
        "Save file",
        data=_df_to_excel_bytes(df),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key
    )


def per_deliverable_downloads(idx: int, d: Dict[str, Any]):
    c1, c2, _ = st.columns([1, 1, 6])
    with c1:
        if st.button("📄 Summary", key=f"sum-{idx}"):
            # Build & stream
            download_summary_button([d], f"deliverable_{idx}_summary.xlsx", key=f"sumbtn-{idx}")
    with c2:
        if st.button("📦 Full workbook", key=f"full-{idx}"):
            # Full workbook: summary + tasks sheets
            bio = io.BytesIO()
            with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
                summary_dataframe([d]).to_excel(writer, index=False, sheet_name="Summary")
                if d.get("tasks"):
                    pd.DataFrame(d["tasks"]).to_excel(writer, index=False, sheet_name="Tasks")
            bio.seek(0)
            st.download_button(
                "Save file",
                data=bio.read(),
                file_name=f"deliverable_{idx}_full.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"fullbtn-{idx}"
            )


# ---------------------------
# RENDER DELIVERABLES
# ---------------------------
def render_deliverables():
    _ensure_state()
    st.header("Deliverables")

    deliverables = st.session_state["deliverables"]
    compact = st.toggle("Compact table view", value=True,
                        help="Great for long lists; use cards for details & actions.")

    # Filter/sort
    filtered = apply_filters(deliverables)
    filtered = sort_deliverables(filtered)

    # Global downloads (on current filtered set)
    if filtered:
        colA, colB, colC, colD = st.columns([1, 1, 1, 6])
        with colA:
            if st.button("⬇️ All (Summary)"):
                download_summary_button(filtered, "all_deliverables_summary.xlsx", key="dl-sum-all")
        with colB:
            if st.button("⬇️ All (Flattened)"):
                download_flattened_button(filtered, "all_deliverables_flattened.xlsx", key="dl-flat-all")
        with colC:
            if st.button("🗑️ Delete ALL filtered"):
                # ask confirm
                if st.confirm("Delete all filtered deliverables? This cannot be undone."):
                    keep = [d for d in deliverables if d not in filtered]
                    st.session_state["deliverables"] = keep
                    st.rerun()

    # Compact table view
    if compact:
        df = summary_dataframe(filtered)
        st.dataframe(df, use_container_width=True, hide_index=True)
        return

    # Card view with pagination
    total = len(filtered)
    page_size = st.sidebar.selectbox("Items per page", [5, 10, 20, 50], index=1)
    pages = max(1, math.ceil(total / page_size))
    page = st.sidebar.number_input("Page", min_value=1, max_value=pages, step=1, value=1)
    start, end = (page - 1) * page_size, (page - 1) * page_size + page_size

    st.session_state["ui"]["expanded_cards"] = st.checkbox(
        "Expand cards", value=st.session_state["ui"]["expanded_cards"]
    )

    if total == 0:
        st.info("No deliverables match your filters.")
        return

    for idx, d in enumerate(filtered[start:end], start=start + 1):
        title = d.get("title", "(untitled)")
        due = d.get("due_date")
        due_str = due.strftime("%Y-%m-%d") if isinstance(due, (date, datetime)) else "—"
        header = f"{idx}. {title}"
        expanded = st.session_state["ui"]["expanded_cards"]

        with st.expander(header, expanded=expanded):
            top_left, top_mid, top_right = st.columns([2, 1.2, 1])
            with top_left:
                st.markdown(f"**Owner:** {d.get('owner','')}")
                st.markdown(f"**Unit:** {d.get('unit','')}")
                st.markdown(f"**Priority:** {d.get('priority','')}")
                if d.get("has_due_date") and due_str != "—":
                    st.markdown(f"**Due:** {due_str}")
                if (d.get("notes") or "").strip():
                    st.markdown(f"**Notes:** {d.get('notes').strip()}")

            with top_right:
                # Dangerous: delete
                if st.button("🗑️ Delete", key=f"del-{idx}"):
                    st.session_state["deliverables"].remove(d)
                    st.rerun()

            # Tasks table (compact)
            tasks = d.get("tasks", [])
            if tasks:
                df_t = pd.DataFrame(tasks)
                # nicer date formatting
                for col in ("start_date", "due_date"):
                    if col in df_t.columns:
                        df_t[col] = df_t[col].apply(lambda x: x.strftime("%Y-%m-%d") if isinstance(x, (date, datetime)) else x)
                st.dataframe(df_t, use_container_width=True, hide_index=True)

            per_deliverable_downloads(idx, d)


# ---------------------------
# MAIN
# ---------------------------
def main():
    _ensure_state()

    st.title("📝 DGCC Follow-up (clean)")
    # Create form
    create_deliverable_form()

    st.divider()
    # Deliverables section
    render_deliverables()

    # Footer
    st.caption("© DGCC — Streamlined follow-up tool")


if __name__ == "__main__":
    main()
