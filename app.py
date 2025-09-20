# app.py — DGCC Follow-up (clean, searchable, downloadable, no variables panel)

from __future__ import annotations

import io
import json
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# ──────────────────────────────────────────────────────────────────────────────
# Page + compact CSS
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="DGCC Follow-up Manager", layout="wide")

st.markdown(
    """
<style>
/* Tighter form spacing inside forms */
[data-testid="stForm"] .stTextInput,
[data-testid="stForm"] .stTextArea,
[data-testid="stForm"] .stSelectbox,
[data-testid="stForm"] .stNumberInput,
[data-testid="stForm"] .stDateInput { margin-bottom: .35rem; }

/* Visible border around expanders so it feels card-like */
.stExpander { border: 1px solid #e5e7eb; border-radius: 12px; }

/* Page width */
.block-container { max-width: 1100px; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("DGCC Follow-up — Clean")


# ──────────────────────────────────────────────────────────────────────────────
# Fixed choices (no Variables panel)
# ──────────────────────────────────────────────────────────────────────────────

if "vars" not in st.session_state:
    st.session_state["vars"] = {
        "status":   ["Not started", "In progress", "Blocked", "Done"],
        "priority": ["Low", "Medium", "High"],
        "owners":   [],  # put names here if you want a dropdown
    }

# Deliverables storage
if "deliverables" not in st.session_state:
    st.session_state["deliverables"] = []

# UI state
st.session_state.setdefault("page", 1)
st.session_state.setdefault("edit_id", None)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers (IDs, filtering, paging, confirm, exports)
# ──────────────────────────────────────────────────────────────────────────────

def generate_id() -> str:
    """Short unique ID."""
    return datetime.utcnow().strftime("%y%m%d%H%M%S%f")[-10:]


def confirm_modal(prompt: str, state_key: str, match_id: Optional[str] = None) -> bool:
    """
    Simple yes/no confirm using a modal.
    Set st.session_state[state_key] = True (or the id) to open it.
    If match_id is provided, the modal is shown only if state value == match_id.
    """
    token = st.session_state.get(state_key)
    if token is False or token is None:
        return False
    if match_id is not None and token != match_id:
        return False

    with st.modal("Please confirm"):
        st.warning(prompt)
        c1, c2 = st.columns([1, 1])
        yes = c1.button("Yes, continue")
        no = c2.button("Cancel")
        if yes:
            st.session_state[state_key] = False
            return True
        if no:
            st.session_state[state_key] = False
            st.rerun()
    return False


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


# ── per-deliverable exports ───────────────────────────────────────────────────

def export_summary_csv(deliv: Dict) -> bytes:
    """Single deliverable → flattened task CSV."""
    rows = []
    for t in deliv.get("tasks", []) or []:
        rows.append({
            "deliverable_id": deliv["id"],
            "deliverable_title": deliv.get("title", ""),
            "row": t.get("row"),
            "task": t.get("title"),
            "status": t.get("status"),
            "priority": t.get("priority"),
            "hours": t.get("hours"),
            "due_date": t.get("due_date"),
            "notes": t.get("notes"),
        })
    df = pd.DataFrame(rows)
    out = io.StringIO()
    df.to_csv(out, index=False)
    return out.getvalue().encode("utf-8")


def export_full_xlsx(deliv: Dict) -> bytes:
    """Single deliverable → Excel with 2 sheets: meta, tasks."""
    meta = pd.DataFrame([{
        "id": deliv["id"],
        "title": deliv.get("title", ""),
        "owner": deliv.get("owner", ""),
        "unit": deliv.get("unit", ""),
        "term": deliv.get("term", ""),
        "created_at": deliv.get("created_at", ""),
        "notes": deliv.get("notes", ""),
    }])
    tasks = pd.DataFrame(deliv.get("tasks", []) or [])
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="xlsxwriter") as w:
        meta.to_excel(w, index=False, sheet_name="deliverable")
        tasks.to_excel(w, index=False, sheet_name="tasks")
    return buff.getvalue()


# ── global (filtered) exports ─────────────────────────────────────────────────

def build_global_tables(items: List[Dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (deliverables_df, tasks_df, flattened_df) for a list of deliverables."""
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

    df_flat = df_tasks.copy() if len(df_tasks) else pd.DataFrame(
        columns=[
            "deliverable_id", "deliverable_title", "row", "title", "status",
            "priority", "hours", "due_date", "notes"
        ]
    )
    return df_deliv, df_tasks, df_flat


def export_filtered_csv(items: List[Dict]) -> bytes:
    """Summary CSV of all filtered tasks."""
    _, _, df_flat = build_global_tables(items)
    buff = io.StringIO()
    df_flat.to_csv(buff, index=False)
    return buff.getvalue().encode("utf-8")


def export_filtered_excel(items: List[Dict]) -> bytes:
    """Excel workbook with 3 sheets: deliverables, tasks, flattened."""
    df_deliv, df_tasks, df_flat = build_global_tables(items)
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="xlsxwriter") as w:
        df_deliv.to_excel(w, index=False, sheet_name="deliverables")
        df_tasks.to_excel(w, index=False, sheet_name="tasks")
        df_flat.to_excel(w, index=False, sheet_name="flattened")
    return buff.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Create / Edit / Delete logic
# ──────────────────────────────────────────────────────────────────────────────

def save_deliverable(obj: Dict) -> None:
    st.session_state["deliverables"].append(obj)


def replace_deliverable(updated: Dict) -> None:
    items = st.session_state["deliverables"]
    for i, d in enumerate(items):
        if d["id"] == updated["id"]:
            items[i] = updated
            break


def delete_deliverable(deliv_id: str) -> None:
    items = st.session_state["deliverables"]
    st.session_state["deliverables"] = [d for d in items if d["id"] != deliv_id]


def create_deliverable_form() -> None:
    """Form inside an expander. Adds one deliverable with up to 5 tasks."""
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
            d_term = st.text_input("Term", help="Example: 2025-1 or Fall 2025")
        with c4:
            d_notes = st.text_area("Deliverable notes", height=72)

        st.markdown("#### Tasks (up to 5)")

        def task_row(idx: int, prefix: str):
            t_title = st.text_input(f"Task {idx} — title", key=f"{prefix}_title")
            cc1, cc2, cc3, cc4 = st.columns([1, 1, 1, 1])
            with cc1:
                t_status = st.selectbox(
                    "Status",
                    st.session_state["vars"]["status"],
                    key=f"{prefix}_status",
                    index=0,
                )
            with cc2:
                t_priority = st.selectbox(
                    "Priority",
                    st.session_state["vars"]["priority"],
                    key=f"{prefix}_priority",
                    index=1,
                )
            with cc3:
                t_has_due = st.checkbox("Has due date?", key=f"{prefix}_has_due")
                t_due = st.date_input("Due date", key=f"{prefix}_due", disabled=not t_has_due)
            with cc4:
                t_hours = st.number_input("Hours", min_value=0.0, step=0.5, key=f"{prefix}_hours")
            t_notes = st.text_area("Notes", height=56, key=f"{prefix}_notes")
            return t_title, t_status, t_priority, t_has_due, t_due, t_hours, t_notes

        rows = []
        for i in range(1, 6):
            rows.append(task_row(i, f"t{i}"))

        submitted = st.form_submit_button("Save deliverable")
        if submitted:
            if not d_title.strip():
                st.error("Please enter a deliverable title.")
                st.stop()

            tasks: List[Dict] = []
            for i, row in enumerate(rows, start=1):
                t_title, t_status, t_priority, t_has_due, t_due, t_hours, t_notes = row
                t = build_task(i, t_title, t_status, t_hours, t_has_due, t_due, t_notes, t_priority)
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


def edit_deliverable_modal(deliv: Dict) -> None:
    """Inline modal editor for a deliverable and its tasks."""
    with st.modal(f"Edit deliverable — {deliv.get('title','')}"):
        with st.form(f"edit_{deliv['id']}"):

            d_title = st.text_input("Deliverable title *", value=deliv.get("title", ""))
            c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
            with c1:
                d_owner = st.text_input("Owner", value=deliv.get("owner", ""))
            with c2:
                d_unit = st.text_input("Unit", value=deliv.get("unit", ""))
            with c3:
                d_term = st.text_input("Term", value=deliv.get("term", ""))
            with c4:
                d_notes = st.text_area("Deliverable notes", value=deliv.get("notes", ""), height=72)

            st.markdown("#### Tasks")

            existing = deliv.get("tasks", []) or []
            # ensure we show up to 5 rows
            while len(existing) < 5:
                existing.append({})

            rows = []
            for idx in range(1, 6):
                t = existing[idx - 1] or {}
                t_title = st.text_input(f"Task {idx} — title", value=t.get("title", ""), key=f"e_{deliv['id']}_title_{idx}")
                cc1, cc2, cc3, cc4 = st.columns([1, 1, 1, 1])
                with cc1:
                    t_status = st.selectbox(
                        "Status", st.session_state["vars"]["status"],
                        index=(st.session_state["vars"]["status"].index(t.get("status"))
                               if t.get("status") in st.session_state["vars"]["status"] else 0),
                        key=f"e_{deliv['id']}_status_{idx}",
                    )
                with cc2:
                    t_priority = st.selectbox(
                        "Priority", st.session_state["vars"]["priority"],
                        index=(st.session_state["vars"]["priority"].index(t.get("priority"))
                               if t.get("priority") in st.session_state["vars"]["priority"] else 1),
                        key=f"e_{deliv['id']}_priority_{idx}",
                    )
                with cc3:
                    base_has_due = bool(t.get("due_date"))
                    t_has_due = st.checkbox("Has due date?", value=base_has_due, key=f"e_{deliv['id']}_has_due_{idx}")
                    t_due = st.date_input(
                        "Due date",
                        value=(t.get("due_date") or date.today()),
                        disabled=not t_has_due,
                        key=f"e_{deliv['id']}_due_{idx}",
                    )
                with cc4:
                    t_hours = st.number_input(
                        "Hours", min_value=0.0, step=0.5,
                        value=float(t.get("hours") or 0.0),
                        key=f"e_{deliv['id']}_hours_{idx}",
                    )
                t_notes = st.text_area("Notes", value=t.get("notes", ""), height=56, key=f"e_{deliv['id']}_notes_{idx}")

                rows.append((t_title, t_status, t_priority, t_has_due, t_due, t_hours, t_notes))

            saved = st.form_submit_button("Save changes")
            if saved:
                if not d_title.strip():
                    st.error("Please enter a deliverable title.")
                    st.stop()

                tasks: List[Dict] = []
                for i, row in enumerate(rows, start=1):
                    t_title, t_status, t_priority, t_has_due, t_due, t_hours, t_notes = row
                    t = build_task(i, t_title, t_status, t_hours, t_has_due, t_due, t_notes, t_priority)
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
                replace_deliverable(updated)
                st.success("Saved.")
                st.session_state["edit_id"] = None
                st.rerun()


def show_deliverable_card(deliv: Dict) -> None:
    with st.expander(f"{deliv.get('title','')} — {deliv.get('owner','')}", expanded=False):
        st.caption(f"ID: {deliv['id']}  •  created {deliv.get('created_at','')}")
        if deliv.get("notes"):
            st.markdown(f"**Notes:** {deliv['notes']}")

        tasks = deliv.get("tasks", []) or []
        if not tasks:
            st.info("No tasks added.")
        else:
            df = pd.DataFrame(tasks)
            cols = ["row", "title", "status", "priority", "hours", "due_date", "notes"]
            cols = [c for c in cols if c in df.columns]
            st.dataframe(
                df[cols].rename(columns={"row": "#", "title": "Task", "due_date": "Due"}),
                use_container_width=True,
                hide_index=True,
            )

        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        with c1:
            st.download_button(
                "Summary (CSV)",
                data=export_summary_csv(deliv),
                file_name=f"{deliv['title']}_summary.csv",
                mime="text/csv",
                key=f"dl_csv_{deliv['id']}",
            )
        with c2:
            st.download_button(
                "Full workbook (Excel)",
                data=export_full_xlsx(deliv),
                file_name=f"{deliv['title']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_xlsx_{deliv['id']}",
            )
        with c3:
            if st.button("Edit", key=f"edit_{deliv['id']}"):
                st.session_state["edit_id"] = deliv["id"]
                st.rerun()
        with c4:
            if st.button("Delete", key=f"del_{deliv['id']}"):
                st.session_state["ask_delete_one"] = deliv["id"]

        # Confirm delete
        if confirm_modal(
            f"Delete deliverable '{deliv['title']}'? This cannot be undone.",
            "ask_delete_one",
            match_id=deliv["id"],
        ):
            delete_deliverable(deliv["id"])
            st.success("Deliverable deleted.")
            st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Layout
# ──────────────────────────────────────────────────────────────────────────────

# Create form in collapsible expander
with st.expander("Create deliverable", expanded=False):
    create_deliverable_form()

st.subheader("Deliverables")

# Filters + pagination
terms = sorted({(d.get("term") or "").strip() for d in st.session_state["deliverables"] if d.get("term")})
owners = sorted({(d.get("owner") or "").strip() for d in st.session_state["deliverables"] if d.get("owner")})

fc1, fc2, fc3, fc4 = st.columns([1, 1, 2, 1])
with fc1:
    f_term = st.selectbox("Term", [""] + terms, index=0)
with fc2:
    f_owner = st.selectbox("Owner", [""] + owners, index=0)
with fc3:
    f_query = st.text_input("Search", help="title / unit / notes")   # Search bar
with fc4:
    per_page = st.selectbox("Per page", [5, 10, 20, 50], index=1)

items = st.session_state["deliverables"]
filtered = filter_deliverables(items, f_term, f_owner, f_query)

# Global download of filtered
dl1, dl2, _ = st.columns([1, 1, 6])
with dl1:
    st.download_button(
        "Download filtered — CSV",
        data=export_filtered_csv(filtered),
        file_name="deliverables_filtered_summary.csv",
        mime="text/csv",
        key="dl_filtered_csv",
    )
with dl2:
    st.download_button(
        "Download filtered — Excel",
        data=export_filtered_excel(filtered),
        file_name="deliverables_filtered.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_filtered_xlsx",
    )

# Pagination controls
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

# Open edit modal if needed
if st.session_state.get("edit_id"):
    ed = next((d for d in items if d["id"] == st.session_state["edit_id"]), None)
    if ed:
        edit_deliverable_modal(ed)

if not page_items:
    st.info("No deliverables match the current filters.")
else:
    for d in page_items:
        show_deliverable_card(d)
