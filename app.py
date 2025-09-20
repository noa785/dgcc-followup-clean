# app.py — DGCC Follow-up Manager (clean, single file)

from __future__ import annotations

import io
import uuid
from contextlib import contextmanager
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
/* tighter content and widgets */
.block-container {max-width: 1100px;}
[data-testid="stForm"] .stTextInput,
[data-testid="stForm"] .stTextArea,
[data-testid="stForm"] .stSelectbox,
[data-testid="stForm"] .stNumberInput,
[data-testid="stForm"] .stDateInput { margin-bottom: .35rem; }

/* nicer expanders */
.stExpander {border: 1px solid #e5e7eb; border-radius: 12px;}
</style>
""",
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# Compatibility: “modal” wrapper (works on Streamlit versions without st.modal)
# ──────────────────────────────────────────────────────────────────────────────

@contextmanager
def ui_modal(title: str):
    """
    Usage:
        with ui_modal("Edit deliverable"):
            ...UI...
    On newer Streamlit: uses st.modal. On older builds: uses a right sidebar.
    """
    if hasattr(st, "modal"):           # Streamlit >= 1.31
        with st.modal(title):
            yield
    else:
        st.sidebar.markdown(f"### {title}")
        with st.sidebar.container():
            yield


# ──────────────────────────────────────────────────────────────────────────────
# Session state bootstrap
# ──────────────────────────────────────────────────────────────────────────────

def _init_state():
    if "deliverables" not in st.session_state:
        st.session_state["deliverables"] = []  # list[dict]
    if "open_create" not in st.session_state:
        st.session_state["open_create"] = False
    # Fixed choices (no Variables panel)
    if "vars" not in st.session_state:
        st.session_state["vars"] = {
            "status":   ["Not started", "In progress", "Blocked", "Done"],
            "priority": ["Low", "Medium", "High"],
            "owners":   [],  # put names if you want a dropdown later
        }

_init_state()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def generate_id() -> str:
    return uuid.uuid4().hex[:10]

def build_task(
    idx: int,
    title: str,
    status: str,
    hours: Optional[float],
    has_due: bool,
    due_val: Optional[date],
    notes: str,
    priority: str,
) -> Optional[Dict]:
    """Return a task dict if a title is entered; otherwise None."""
    title = (title or "").strip()
    if not title:
        return None
    return {
        "row": idx,
        "title": title,
        "status": status,
        "priority": priority,
        "hours": float(hours) if hours not in (None, "") else None,
        "due_date": due_val if has_due else None,
        "notes": (notes or "").strip(),
    }

def confirm_modal(prompt: str, state_key: str, match_id: Optional[str] = None) -> bool:
    """Open a confirm dialog if asked via session_state[state_key]."""
    requested = st.session_state.get(state_key)
    if match_id is not None and requested != match_id:
        return False
    if not requested:
        return False

    with ui_modal("Confirm action"):
        st.warning(prompt)
        c1, c2 = st.columns(2)
        yes = c1.button("Yes, continue")
        no  = c2.button("Cancel")
        if yes:
            st.session_state[state_key] = None
            return True
        if no:
            st.session_state[state_key] = None
            st.rerun()
    return False

def filter_deliverables(items: List[Dict], term: str, owner: str, query: str) -> List[Dict]:
    term  = (term or "").strip().lower()
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
# Export: filtered CSV/Excel
# ──────────────────────────────────────────────────────────────────────────────

def build_global_tables(items: List[Dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (deliverables_df, tasks_df, flattened_df) for a list of deliverables."""
    # deliverables
    d_rows = []
    for d in items:
        d_rows.append({
            "id": d["id"],
            "title": d.get("title", ""),
            "owner": d.get("owner", ""),
            "unit": d.get("unit", ""),
            "term": d.get("term", ""),
            "created_at": d.get("created_at", ""),
            "notes": d.get("notes", ""),
        })
    df_deliv = pd.DataFrame(d_rows)

    # tasks
    t_rows = []
    for d in items:
        for t in d.get("tasks", []) or []:
            t_rows.append({
                "deliverable_id": d["id"],
                "deliverable_title": d.get("title", ""),
                "row": t.get("row"),
                "title": t.get("title"),
                "status": t.get("status"),
                "priority": t.get("priority"),
                "hours": t.get("hours"),
                "due_date": t.get("due_date"),
                "notes": t.get("notes"),
            })
    df_tasks = pd.DataFrame(t_rows)

    # flattened = tasks table (already one per task)
    if len(df_tasks):
        df_flat = df_tasks.copy()
    else:
        df_flat = pd.DataFrame(
            columns=[
                "deliverable_id", "deliverable_title", "row", "title", "status",
                "priority", "hours", "due_date", "notes"
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
# Create / Edit forms
# ──────────────────────────────────────────────────────────────────────────────

def _task_row(i: int, *, prefix: str = "new", preset: Optional[Dict] = None) -> Dict:
    """
    Render one task row. Returns a dict with the raw widget values (not yet filtered by title).
    `prefix` ensures unique keys, e.g., "new_t1_title" or "ed_<id>_t1_title".
    """
    pfx = f"{prefix}_t{i}"
    preset = preset or {}

    title = st.text_input(f"Task {i} — title", value=preset.get("title", ""), key=f"{pfx}_title")

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    with c1:
        status = st.selectbox(
            "Status",
            st.session_state["vars"]["status"],
            index=(st.session_state["vars"]["status"].index(preset.get("status", "Not started"))
                   if preset.get("status") in st.session_state["vars"]["status"] else 0),
            key=f"{pfx}_status",
        )
    with c2:
        priority = st.selectbox(
            "Priority",
            st.session_state["vars"]["priority"],
            index=(st.session_state["vars"]["priority"].index(preset.get("priority", "Medium"))
                   if preset.get("priority") in st.session_state["vars"]["priority"] else 1),
            key=f"{pfx}_priority",
        )
    with c3:
        has_due = st.checkbox(f"Has due date? {i}", value=preset.get("due_date") is not None, key=f"{pfx}_has_due")
        if has_due:
            due = st.date_input(
                f"Due date {i}",
                value=preset.get("due_date") or date.today(),
                key=f"{pfx}_due",
            )
        else:
            # show disabled preview to keep layout consistent
            st.date_input(
                f"Due date {i}",
                value=preset.get("due_date") or date.today(),
                key=f"{pfx}_due_disabled",
                disabled=True,
            )
            due = None
    with c4:
        hours = st.number_input("Hours", min_value=0.0, step=0.5, value=float(preset.get("hours") or 0.0), key=f"{pfx}_hours")

    notes = st.text_area(f"Notes {i}", value=preset.get("notes", ""), height=60, key=f"{pfx}_notes")
    st.markdown("---")

    return {
        "idx": i,
        "title": title,
        "status": status,
        "priority": priority,
        "has_due": has_due,
        "due": due,
        "hours": hours,
        "notes": notes,
    }


def create_deliverable_form():
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
        raw_rows = []
        for i in range(1, 6):
            raw_rows.append(_task_row(i, prefix="new"))

        submitted = st.form_submit_button("Save deliverable")

        if submitted:
            if not d_title.strip():
                st.error("Please enter a deliverable title.")
                st.stop()

            tasks: List[Dict] = []
            for row in raw_rows:
                task = build_task(
                    row["idx"],
                    row["title"],
                    row["status"],
                    row["hours"],
                    row["has_due"],
                    row["due"],
                    row["notes"],
                    row["priority"],
                )
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
            st.success("Deliverable added.")
            st.session_state["open_create"] = False
            st.rerun()


def edit_deliverable_modal(deliv: Dict):
    """Edit an existing deliverable (uses ui_modal)."""
    with ui_modal("Edit deliverable"):
        with st.form(f"edit_deliv_{deliv['id']}"):
            d_title = st.text_input("Deliverable title *", value=deliv.get("title", ""))
            c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
            with c1:
                d_owner = st.text_input("Owner", value=deliv.get("owner", ""))
            with c2:
                d_unit = st.text_input("Unit", value=deliv.get("unit", ""))
            with c3:
                d_term = st.text_input("Term", value=deliv.get("term", ""))
            with c4:
                d_notes = st.text_area("Deliverable notes", value=deliv.get("notes", ""), height=80)

            st.markdown("### Tasks (up to 5)")
            raw_rows = []
            existing = {t.get("row"): t for t in (deliv.get("tasks", []) or [])}
            for i in range(1, 6):
                raw_rows.append(
                    _task_row(
                        i,
                        prefix=f"ed_{deliv['id']}",
                        preset=existing.get(i, {}),
                    )
                )

            submitted = st.form_submit_button("Save changes")

            if submitted:
                if not d_title.strip():
                    st.error("Please enter a deliverable title.")
                    st.stop()

                tasks: List[Dict] = []
                for row in raw_rows:
                    task = build_task(
                        row["idx"],
                        row["title"],
                        row["status"],
                        row["hours"],
                        row["has_due"],
                        row["due"],
                        row["notes"],
                        row["priority"],
                    )
                    if task:
                        tasks.append(task)

                # Update
                deliv.update(
                    {
                        "title": d_title.strip(),
                        "owner": d_owner.strip(),
                        "unit": d_unit.strip(),
                        "term": d_term.strip(),
                        "notes": d_notes.strip(),
                        "tasks": tasks,
                    }
                )
                st.success("Changes saved.")
                st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Rendering: per-deliverable card
# ──────────────────────────────────────────────────────────────────────────────

def show_deliverable_card(deliv: Dict):
    title = deliv.get("title", "")
    owner = deliv.get("owner", "")
    head = f"{title} — {owner}" if owner else title

    with st.expander(head, expanded=False):
        st.caption(f"ID: `{deliv['id']}` · created {deliv.get('created_at', '')}")
        if deliv.get("notes"):
            st.markdown(f"**Notes:** {deliv['notes']}")

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

        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            if st.button("Edit", key=f"edit_{deliv['id']}"):
                st.session_state["edit_id"] = deliv["id"]
        with c2:
            if st.button("Delete", key=f"del_{deliv['id']}"):
                st.session_state["ask_delete_one"] = deliv["id"]
        with c3:
            # Per-deliverable CSV export of its tasks
            _, _, fdf = build_global_tables([deliv])
            buff = io.StringIO()
            fdf.to_csv(buff, index=False)
            st.download_button(
                "Download tasks (CSV)",
                data=buff.getvalue().encode("utf-8"),
                file_name=f"{deliv['title']}_tasks.csv",
                mime="text/csv",
                key=f"dl_{deliv['id']}",
            )

    # Delete confirmation
    if confirm_modal(
        f"Delete deliverable '{deliv['title']}'? This cannot be undone.",
        "ask_delete_one",
        match_id=deliv["id"],
    ):
        st.session_state["deliverables"] = [
            d for d in st.session_state["deliverables"] if d["id"] != deliv["id"]
        ]
        st.success("Deliverable deleted.")
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Main page
# ──────────────────────────────────────────────────────────────────────────────

def main():
    st.title("DGCC Follow-up Manager")

    # top header row with right-side Create button (opens full-width expander)
    hdr_l, hdr_r = st.columns([5, 1])
    with hdr_r:
        if st.button("Create deliverable", use_container_width=True):
            st.session_state["open_create"] = True
            st.rerun()

    # full width create form
    with st.expander("Create deliverable", expanded=st.session_state["open_create"]):
        create_deliverable_form()
        if st.button("Close form", key="close_create_form"):
            st.session_state["open_create"] = False
            st.rerun()

    st.subheader("Deliverables")

    # Build choices from current data
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

    # global download (filtered)
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

    # pagination
    if "page" not in st.session_state:
        st.session_state["page"] = 1
    pages = max(1, (len(filtered) - 1) // per_page + 1)
    st.session_state["page"] = min(st.session_state["page"], pages)

    pc1, pc2, pc3 = st.columns([1, 1, 6])
    with pc1:
        if st.button("Prev", disabled=st.session_state["page"] <= 1):
            st.session_state["page"] -= 1
            st.rerun()
    with pc2:
        if st.button("Next", disabled=st.session_state["page"] >= pages):
            st.session_state["page"] += 1
            st.rerun()
    with pc3:
        st.caption(f"Page {st.session_state['page']} / {pages} • {len(filtered)} match(es)")

    page_items, _ = paginate(filtered, st.session_state["page"], per_page)

    # edit modal if requested
    if st.session_state.get("edit_id"):
        ed = next((d for d in items if d["id"] == st.session_state["edit_id"]), None)
        if ed:
            edit_deliverable_modal(ed)
            st.session_state["edit_id"] = None  # close after display

    if not page_items:
        st.info("No deliverables match the current filters.")
    else:
        for d in page_items:
            show_deliverable_card(d)


if __name__ == "__main__":
    main()
