# app.py — DGCC Follow-up Manager (clean, inline edit, date+time)

from __future__ import annotations
import io
from typing import Dict, List, Optional, Tuple
from datetime import date, time, datetime
import random
import string

import pandas as pd
import streamlit as st


# ──────────────────────────────────────────────────────────────────────────────
# Page + compact styling
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="DGCC Follow-up Manager", page_icon=None, layout="wide")

st.markdown(
    """
    <style>
      .block-container { max-width: 1100px; }
      [data-testid="stForm"] .stTextInput,
      [data-testid="stForm"] .stTextArea,
      [data-testid="stForm"] .stSelectbox,
      [data-testid="stForm"] .stNumberInput,
      [data-testid="stForm"] .stDateInput,
      [data-testid="stForm"] .stTimeInput { margin-bottom: .35rem; }
      .stExpander { border: 1px solid #e5e7eb; border-radius: 12px; }
      .muted { color:#6b7280; font-size: 0.9rem; }
      .tight { margin-top: .25rem; margin-bottom: .25rem; }
      .small { font-size: 0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixed lists (you can edit these; no "Variables" panel)
# ──────────────────────────────────────────────────────────────────────────────
if "vars" not in st.session_state:
    st.session_state["vars"] = {
        "status":   ["Not started", "In progress", "Blocked", "Done"],
        "priority": ["Low", "Medium", "High"],
    }

if "deliverables" not in st.session_state:
    st.session_state["deliverables"] = []

# Expander control (for Create)
if "show_create" not in st.session_state:
    st.session_state["show_create"] = False

# Which deliverable is in inline edit mode
if "edit_id" not in st.session_state:
    st.session_state["edit_id"] = None

# Which deliverable is being asked for delete confirm
if "confirm_delete_id" not in st.session_state:
    st.session_state["confirm_delete_id"] = None


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def generate_id(n: int = 9) -> str:
    """Simple id (pseudo), good enough for a session store."""
    letters = string.ascii_lowercase + string.digits
    return "".join(random.choice(letters) for _ in range(n))


def filter_deliverables(items: List[Dict], term: str, owner: str, query: str) -> List[Dict]:
    term = (term or "").strip().lower()
    owner = (owner or "").strip().lower()
    query = (query or "").strip().lower()

    out = []
    for d in items:
        if term and term not in (d.get("term", "") or "").lower():
            continue
        if owner and owner not in (d.get("owner", "") or "").lower():
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
    due_dt: Optional[datetime],
    notes: str,
    priority: str,
) -> Optional[Dict]:
    """Create a task dict. Skip if no title."""
    title = (title or "").strip()
    if not title:
        return None
    return {
        "row": idx,
        "title": title,
        "status": status,
        "priority": priority,
        "hours": float(hours) if hours not in (None, "") else None,
        "due_date": due_dt if has_due else None,   # datetime or None
        "notes": (notes or "").strip(),
    }


def _task_row(i: int, *, prefix: str = "new", preset: Optional[Dict] = None) -> Dict:
    """
    Render one task row (used in create and edit forms).
    Includes date + time when 'Has due date?' is checked.
    Returns raw widget values.
    """
    pfx = f"{prefix}_t{i}"
    preset = preset or {}
    preset_due = preset.get("due_date")

    title = st.text_input(f"Task {i} — title", value=preset.get("title", ""), key=f"{pfx}_title")

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    with c1:
        status = st.selectbox(
            "Status",
            st.session_state["vars"]["status"],
            index=(
                st.session_state["vars"]["status"].index(preset.get("status", "Not started"))
                if preset.get("status") in st.session_state["vars"]["status"] else 0
            ),
            key=f"{pfx}_status",
        )
    with c2:
        priority = st.selectbox(
            "Priority",
            st.session_state["vars"]["priority"],
            index=(
                st.session_state["vars"]["priority"].index(preset.get("priority", "Medium"))
                if preset.get("priority") in st.session_state["vars"]["priority"] else 1
            ),
            key=f"{pfx}_priority",
        )
    with c3:
        has_due = st.checkbox(
            f"Has due date? {i}",
            value=preset_due is not None,
            key=f"{pfx}_has_due",
        )
        if has_due:
            due_date_val = st.date_input(
                f"Due date {i}",
                value=(preset_due.date() if isinstance(preset_due, datetime) else date.today()),
                key=f"{pfx}_due_date",
            )
            due_time_val = st.time_input(
                f"Due time {i}",
                value=(preset_due.time() if isinstance(preset_due, datetime) else time(9, 0)),
                key=f"{pfx}_due_time",
            )
            due_dt = datetime.combine(due_date_val, due_time_val)
        else:
            st.date_input(f"Due date {i}", value=date.today(), key=f"{pfx}_due_date_disabled", disabled=True)
            st.time_input(f"Due time {i}", value=time(9, 0), key=f"{pfx}_due_time_disabled", disabled=True)
            due_dt = None
    with c4:
        hours = st.number_input(
            "Hours",
            min_value=0.0,
            step=0.5,
            value=float(preset.get("hours") or 0.0),
            key=f"{pfx}_hours",
        )

    notes = st.text_area(f"Notes {i}", value=preset.get("notes", ""), height=60, key=f"{pfx}_notes")
    st.markdown("---")

    return {
        "idx": i,
        "title": title,
        "status": status,
        "priority": priority,
        "has_due": has_due,
        "due_dt": due_dt,  # datetime or None
        "hours": hours,
        "notes": notes,
    }


def build_global_tables(items: List[Dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (deliverables_df, tasks_df, flattened_df) for a list of deliverables."""
    # Deliverables
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

    # Tasks
    t_rows = []
    for d in items:
        for t in d.get("tasks", []) or []:
            # Convert datetime to iso or empty
            due = ""
            if isinstance(t.get("due_date"), datetime):
                due = t["due_date"].strftime("%Y-%m-%d %H:%M")
            t_rows.append({
                "deliverable_id": d["id"],
                "deliverable_title": d.get("title", ""),
                "row": t.get("row"),
                "title": t.get("title"),
                "status": t.get("status"),
                "priority": t.get("priority"),
                "hours": t.get("hours"),
                "due_date": due,
                "notes": t.get("notes"),
            })
    df_tasks = pd.DataFrame(t_rows)

    if len(df_tasks):
        df_flat = df_tasks.copy()
    else:
        df_flat = pd.DataFrame(columns=[
            "deliverable_id", "deliverable_title", "row", "title", "status",
            "priority", "hours", "due_date", "notes"
        ])

    return df_deliv, df_tasks, df_flat


def export_filtered_csv(items: List[Dict]) -> bytes:
    _, _, df_flat = build_global_tables(items)
    buf = io.StringIO()
    df_flat.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def export_filtered_excel(items: List[Dict]) -> bytes:
    df_deliv, df_tasks, df_flat = build_global_tables(items)
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="xlsxwriter") as w:
        df_deliv.to_excel(w, index=False, sheet_name="deliverables")
        df_tasks.to_excel(w, index=False, sheet_name="tasks")
        df_flat.to_excel(w, index=False, sheet_name="flattened")
    return buff.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Create deliverable form (expander)
# ──────────────────────────────────────────────────────────────────────────────
def create_deliverable_form():
    with st.expander("Create deliverable", expanded=st.session_state["show_create"]):
        with st.form("new_deliverable", clear_on_submit=False):
            st.subheader("Create deliverable")

            d_title = st.text_input("Deliverable title *")
            c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
            with c1:
                d_owner = st.text_input("Owner")
            with c2:
                d_unit = st.text_input("Unit")
            with c3:
                d_term = st.text_input("Term")
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
                        row["due_dt"],   # datetime or None
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
                st.session_state["show_create"] = False
                st.success("Deliverable added.")
                st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Inline card (view + inline edit + inline delete confirm)
# ──────────────────────────────────────────────────────────────────────────────
def show_deliverable_card(deliv: Dict):
    title = deliv.get("title", "")
    owner = deliv.get("owner", "")
    head = f"{title} — {owner}" if owner else title

    editing = (st.session_state.get("edit_id") == deliv["id"])
    confirm_this = (st.session_state.get("confirm_delete_id") == deliv["id"])

    with st.expander(head, expanded=editing or confirm_this):
        st.caption(f"ID: `{deliv['id']}` · created {deliv.get('created_at', '')}")

        if editing:
            # ── INLINE EDIT FORM ─────────────────────────────────────────────
            with st.form(f"edit_deliv_inline_{deliv['id']}"):
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
                    raw_rows.append(_task_row(i, prefix=f"ed_{deliv['id']}", preset=existing.get(i, {})))

                csave, ccancel = st.columns([1, 1])
                submitted = csave.form_submit_button("Save changes")
                canceled  = ccancel.form_submit_button("Cancel")

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
                            row["due_dt"],   # datetime or None
                            row["notes"],
                            row["priority"],
                        )
                        if task:
                            tasks.append(task)

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
                    st.session_state["edit_id"] = None
                    st.success("Changes saved.")
                    st.rerun()

                if canceled:
                    st.session_state["edit_id"] = None
                    st.rerun()

        else:
            # ── READ-ONLY VIEW ──────────────────────────────────────────────
            if deliv.get("notes"):
                st.markdown(f"**Notes:** {deliv['notes']}")

            tasks = deliv.get("tasks", []) or []
            if not tasks:
                st.info("No tasks added.")
            else:
                df = pd.DataFrame(tasks)
                if "due_date" in df.columns and len(df):
                    df["due_date"] = df["due_date"].apply(
                        lambda x: x.strftime("%Y-%m-%d %H:%M") if isinstance(x, datetime) else ""
                    )
                cols = ["row", "title", "status", "priority", "hours", "due_date", "notes"]
                df = df[[c for c in cols if c in df.columns]]
                st.dataframe(
                    df.rename(columns={"row": "#", "title": "Task", "due_date": "Due"}),
                    use_container_width=True,
                    hide_index=True,
                )

            # Action row
            c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
            with c1:
                if st.button("Edit", key=f"edit_{deliv['id']}"):
                    st.session_state["edit_id"] = deliv["id"]
                    st.session_state["confirm_delete_id"] = None
                    st.rerun()
            with c2:
                if not confirm_this and st.button("Delete", key=f"del_{deliv['id']}"):
                    st.session_state["confirm_delete_id"] = deliv["id"]
                    st.session_state["edit_id"] = None
                    st.rerun()
            with c3:
                # Per-deliverable CSV (tasks)
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

            # Inline delete confirm
            if confirm_this:
                st.warning("Delete this deliverable? This cannot be undone.")
                cc1, cc2 = st.columns([1, 1])
                if cc1.button("Yes, delete", key=f"yes_{deliv['id']}"):
                    st.session_state["deliverables"] = [
                        d for d in st.session_state["deliverables"] if d["id"] != deliv["id"]
                    ]
                    st.session_state["confirm_delete_id"] = None
                    st.success("Deliverable deleted.")
                    st.rerun()
                if cc2.button("Cancel", key=f"no_{deliv['id']}"):
                    st.session_state["confirm_delete_id"] = None
                    st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────
st.title("DGCC Follow-up Manager")

# Create form (expander)
create_deliverable_form()

st.subheader("Deliverables")

# Quick "Create deliverable" button near filters
def _open_create():
    st.session_state["show_create"] = True

st.button("Create deliverable", on_click=_open_create, help="Open the create form above")

# Build filter choices from current data
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

# Filter
all_items = st.session_state["deliverables"]
filtered = filter_deliverables(all_items, f_term, f_owner, f_query)

# Global filtered downloads
dl1, dl2, _ = st.columns([1, 1, 6])
with dl1:
    st.download_button(
        "Download filtered — CSV",
        data=export_filtered_csv(filtered),
        file_name="deliverables_filtered_summary.csv",
        mime="text/csv",
        help="All filtered tasks, flattened",
    )
with dl2:
    st.download_button(
        "Download filtered — Excel",
        data=export_filtered_excel(filtered),
        file_name="deliverables_filtered.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="Workbook with 3 sheets: deliverables, tasks, flattened",
    )

# Pagination
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

# Render
if not page_items:
    st.info("No deliverables match the current filters.")
else:
    for d in page_items:
        show_deliverable_card(d)
