# app.py — DGCC Follow-up — Clean, modal-compatible & stable

from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, date
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# ──────────────────────────────────────────────────────────────────────────────
# Page & light styling
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="DGCC Follow-up Manager", layout="wide")

st.markdown(
    """
    <style>
      .block-container {max-width: 1100px;}
      [data-testid="stForm"] .stTextInput,
      [data-testid="stForm"] .stTextArea,
      [data-testid="stForm"] .stSelectbox,
      [data-testid="stForm"] .stNumberInput,
      [data-testid="stForm"] .stDateInput { margin-bottom: .4rem; }
      .stExpander { border: 1px solid #e5e7eb; border-radius: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("DGCC Follow-up Manager")


# ──────────────────────────────────────────────────────────────────────────────
# Modal compatibility (Streamlit < 1.31 has no st.modal)
# ──────────────────────────────────────────────────────────────────────────────
@contextmanager
def ui_modal(title: str):
    """
    Use like: with ui_modal("Edit deliverable"): ...
    If st.modal exists → use it; otherwise show in the sidebar.
    """
    if hasattr(st, "modal"):
        with st.modal(title):
            yield
    else:
        st.sidebar.markdown(f"### {title}")
        with st.sidebar.container():
            yield


# ──────────────────────────────────────────────────────────────────────────────
# In-memory persistence
# ──────────────────────────────────────────────────────────────────────────────
def _init_state():
    if "deliverables" not in st.session_state:
        st.session_state["deliverables"]: List[Dict] = []
    if "vars" not in st.session_state:
        # Hard-coded choices (you can remove the variables panel entirely)
        st.session_state["vars"] = {
            "status": ["Not started", "In progress", "Blocked", "Done"],
            "priority": ["Low", "Medium", "High"],
            "owners": [],  # optional list of names
        }


def generate_id() -> str:
    return uuid.uuid4().hex[:10]


def save_deliverable(rec: Dict):
    # If id exists, replace; else append
    items = st.session_state["deliverables"]
    for i, d in enumerate(items):
        if d["id"] == rec["id"]:
            items[i] = rec
            break
    else:
        items.append(rec)


def delete_deliverable(deliv_id: str):
    items = st.session_state["deliverables"]
    st.session_state["deliverables"] = [d for d in items if d["id"] != deliv_id]


# ──────────────────────────────────────────────────────────────────────────────
# Filters / pagination
# ──────────────────────────────────────────────────────────────────────────────
def filter_deliverables(
    items: List[Dict], term: str, owner: str, query: str
) -> List[Dict]:
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
# Build task rows & exports
# ──────────────────────────────────────────────────────────────────────────────
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


def build_global_tables(items: List[Dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # deliverables
    d_rows = [
        {
            "id": d["id"],
            "title": d.get("title", ""),
            "owner": d.get("owner", ""),
            "unit": d.get("unit", ""),
            "term": d.get("term", ""),
            "created_at": d.get("created_at", ""),
            "notes": d.get("notes", ""),
        }
        for d in items
    ]
    df_deliv = pd.DataFrame(d_rows)

    # tasks
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

    # flattened (one row per task)
    if len(df_tasks):
        df_flat = df_tasks.copy()
    else:
        df_flat = pd.DataFrame(
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


# Per-deliverable quick exports -------------------------------------------------
def export_summary_csv_for_deliv(d: Dict) -> bytes:
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
    df = pd.DataFrame(rows)
    csv_buf = io.StringIO()
    df.to_csv(csv_buf, index=False)
    return csv_buf.getvalue().encode("utf-8")


def export_full_xlsx_for_deliv(d: Dict) -> bytes:
    df_deliv, df_tasks, df_flat = build_global_tables([d])
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="xlsxwriter") as w:
        df_deliv.to_excel(w, index=False, sheet_name="deliverable")
        df_tasks.to_excel(w, index=False, sheet_name="tasks")
        df_flat.to_excel(w, index=False, sheet_name="flattened")
    return buff.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Confirm modal (using ui_modal wrapper)
# ──────────────────────────────────────────────────────────────────────────────
def confirm_modal(prompt: str, state_key: str, match_id: str | None = None) -> bool:
    asked = st.session_state.get(state_key)
    if match_id is not None and asked != match_id:
        return False
    if not asked:
        return False

    with ui_modal("Confirm action"):
        st.warning(prompt)
        c1, c2 = st.columns(2)
        yes = c1.button("Yes")
        no = c2.button("Cancel")
        if yes:
            st.session_state[state_key] = None
            return True
        if no:
            st.session_state[state_key] = None
            st.rerun()
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Create / Edit forms
# ──────────────────────────────────────────────────────────────────────────────
def task_row_ui(idx: int, prefix: str):
    """Return dict of UI values for a task row; we don't build the dict here."""
    st.markdown(f"**Task {idx}**")
    title = st.text_input(f"Title {idx}", key=f"{prefix}_title")
    cols = st.columns([1, 1, 1, 1])
    with cols[0]:
        status = st.selectbox(
            f"Status {idx}", st.session_state["vars"]["status"], key=f"{prefix}_status"
        )
    with cols[1]:
        priority = st.selectbox(
            f"Priority {idx}",
            st.session_state["vars"]["priority"],
            key=f"{prefix}_priority",
        )
    with cols[2]:
        has_due = st.checkbox(f"Has due date? {idx}", key=f"{prefix}_has_due")
        if has_due:
            due = st.date_input(
                f"Due date {idx}",
                value=st.session_state.get(f"{prefix}_due") or date.today(),
                key=f"{prefix}_due",
            )
        else:
            st.date_input(
                f"Due date {idx}",
                value=st.session_state.get(f"{prefix}_due") or date.today(),
                key=f"{prefix}_due_preview",
                disabled=True,
            )
            due = None
    with cols[3]:
        hours = st.number_input(f"Hours {idx}", min_value=0.0, step=0.5, key=f"{prefix}_hours")

    notes = st.text_area(f"Notes {idx}", height=60, key=f"{prefix}_notes")
    st.divider()
    return {
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
            d_term = st.text_input("Term", help="e.g., 2025-1")
        with c4:
            d_notes = st.text_area("Deliverable notes", height=80)

        st.markdown("### Tasks (up to 5)")
        vals = [task_row_ui(i, f"t{i}") for i in range(1, 6)]

        submitted = st.form_submit_button("Save deliverable")
        if submitted:
            if not d_title.strip():
                st.error("Please enter a deliverable title.")
                st.stop()

            tasks: List[Dict] = []
            for i, v in enumerate(vals, start=1):
                t = build_task(
                    i,
                    v["title"],
                    v["status"],
                    v["hours"],
                    v["has_due"],
                    v["due"],
                    v["notes"],
                    v["priority"],
                )
                if t:
                    tasks.append(t)

            rec = {
                "id": generate_id(),
                "title": d_title.strip(),
                "owner": d_owner.strip(),
                "unit": d_unit.strip(),
                "term": d_term.strip(),
                "notes": d_notes.strip(),
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                "tasks": tasks,
            }
            save_deliverable(rec)
            st.success("Deliverable added.")
            st.rerun()


def edit_deliverable_modal(deliv: Dict):
    with ui_modal("Edit deliverable"):
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
        # Preload up to 5 tasks
        existing = deliv.get("tasks", []) or []
        vals = []
        for i in range(1, 6):
            prefix = f"e{i}_{deliv['id']}"
            init = next((t for t in existing if t.get("row") == i), None)
            # Seed initial values into session for consistent disabled/preview behavior
            if init and init.get("due_date"):
                st.session_state[f"{prefix}_has_due"] = True
                st.session_state[f"{prefix}_due"] = init.get("due_date")
            vals.append(task_row_ui(i, prefix))

            # overwrite inputs with initial values where appropriate
            if init:
                # ensure UI shows existing values (Streamlit keeps previous keys)
                for k, v in {
                    "title": init.get("title", ""),
                    "status": init.get("status", st.session_state["vars"]["status"][0]),
                    "priority": init.get("priority", st.session_state["vars"]["priority"][0]),
                    "hours": init.get("hours", 0.0),
                    "notes": init.get("notes", ""),
                }.items():
                    st.session_state.setdefault(f"{prefix}_{k}", v)

        c1, c2 = st.columns([1, 1])
        with c1:
            save = st.button("Save changes", key=f"save_{deliv['id']}")
        with c2:
            cancel = st.button("Cancel", key=f"cancel_{deliv['id']}")

        if cancel:
            st.rerun()

        if save:
            if not d_title.strip():
                st.error("Please enter a deliverable title.")
                st.stop()

            tasks: List[Dict] = []
            for i, v in enumerate(vals, start=1):
                t = build_task(
                    i,
                    st.session_state.get(f"e{i}_{deliv['id']}_title", ""),
                    st.session_state.get(f"e{i}_{deliv['id']}_status", st.session_state["vars"]["status"][0]),
                    st.session_state.get(f"e{i}_{deliv['id']}_hours", 0.0),
                    st.session_state.get(f"e{i}_{deliv['id']}_has_due", False),
                    st.session_state.get(f"e{i}_{deliv['id']}_due", None),
                    st.session_state.get(f"e{i}_{deliv['id']}_notes", ""),
                    st.session_state.get(f"e{i}_{deliv['id']}_priority", st.session_state["vars"]["priority"][0]),
                )
                if t:
                    tasks.append(t)

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
            save_deliverable(updated)
            st.success("Saved.")
            st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Cards (display each deliverable)
# ──────────────────────────────────────────────────────────────────────────────
def show_deliverable_card(deliv: Dict):
    with st.expander(f"{deliv['title']} — {deliv.get('owner','')}", expanded=False):
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
            st.dataframe(
                df.rename(columns={"row": "#", "title": "Task", "due_date": "Due"}),
                use_container_width=True,
                hide_index=True,
            )

        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        with c1:
            st.download_button(
                "Summary (CSV)",
                data=export_summary_csv_for_deliv(deliv),
                file_name=f"{deliv['title']}_summary.csv",
                mime="text/csv",
                key=f"dl_sum_{deliv['id']}",
            )
        with c2:
            st.download_button(
                "Full workbook (Excel)",
                data=export_full_xlsx_for_deliv(deliv),
                file_name=f"{deliv['title']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_full_{deliv['id']}",
            )
        with c3:
            if st.button("Edit", key=f"edit_{deliv['id']}"):
                st.session_state["edit_id"] = deliv["id"]
                st.rerun()
        with c4:
            if st.button("Delete", key=f"del_{deliv['id']}"):
                st.session_state["ask_delete_one"] = deliv["id"]

        if confirm_modal(
            f"Delete deliverable '{deliv['title']}'? This cannot be undone.",
            "ask_delete_one",
            match_id=deliv["id"],
        ):
            delete_deliverable(deliv["id"])
            st.success("Deleted.")
            st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Main page
# ──────────────────────────────────────────────────────────────────────────────
def main():
    _init_state()

    # Top quick bar to create another item anytime
    top_l, top_r = st.columns([1, 6])
    with top_l:
        with st.expander("Create deliverable", expanded=False):
            create_deliverable_form()

    st.subheader("Deliverables")

    # Filters + pagination
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

    # inline “Create deliverable” on the right (as you requested)
    right_cta = st.columns([6, 1])[1]
    with right_cta:
        with st.expander("Create deliverable", expanded=False):
            create_deliverable_form()

    if not page_items:
        st.info("No deliverables match the current filters.")
    else:
        # Edit modal if requested
        if st.session_state.get("edit_id"):
            ed = next((d for d in items if d["id"] == st.session_state["edit_id"]), None)
            if ed:
                edit_deliverable_modal(ed)
                # after closing, clear the flag so we don't reopen
                st.session_state["edit_id"] = None

        for d in page_items:
            show_deliverable_card(d)


if __name__ == "__main__":
    main()
