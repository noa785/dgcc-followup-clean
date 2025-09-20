# app.py — DGCC Follow-up Manager (original + infinite tasks)
# -----------------------------------------------------------
# Streamlit single-file app: create + manage Deliverables and Tasks.
# - Create form lives in an expander (short page)
# - Filters: Term / Owner / Search + pagination
# - Per-deliverable downloads (CSV) + global filtered downloads (CSV/Excel)
# - Edit & Delete (with modal fallback for older Streamlit)
# - Reliable calendar (date) + time picker per task (stored as datetime)
# - No external DB; everything is kept in session_state
# - NEW: Infinite tasks (Add/Remove) in Create and Edit

from __future__ import annotations

import io
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, time, datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# ---------------------------- Page & CSS ----------------------------

st.set_page_config(page_title="DGCC Follow-up Manager", page_icon="🗂", layout="wide")

st.markdown(
    """
<style>
/* Tighter, cleaner page */
.block-container { max-width: 1100px; }
.stExpander { border: 1px solid #e5e7eb; border-radius: 12px; }
[data-testid="stForm"] .stTextInput,
[data-testid="stForm"] .stTextArea,
[data-testid="stForm"] .stSelectbox,
[data-testid="stForm"] .stNumberInput,
[data-testid="stForm"] .stDateInput,
[data-testid="stForm"] .stTimeInput { margin-bottom: .4rem; }
.small-note { color:#6b7280; font-size:.85rem; }
hr { border: none; border-top: 1px solid #eee; margin: .75rem 0; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("DGCC Follow-up Manager")


# ---------------------- Compatibility & helpers ---------------------

def _rerun():
    """Streamlit rerun compatibility."""
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()  # older versions


@contextmanager
def ui_modal(title: str):
    """
    Modal compatibility wrapper:
    - Newer Streamlit: uses st.modal
    - Older Streamlit : falls back to a right sidebar container
    """
    if hasattr(st, "modal"):
        with st.modal(title):
            yield
    else:
        st.sidebar.markdown(f"### {title}")
        with st.sidebar.container():
            yield


def generate_id() -> str:
    return datetime.utcnow().strftime("%y%m%d%H%M%S%f")[-10:]


STATUS_OPTS = ["Not started", "In progress", "Blocked", "Done"]
PRIORITY_OPTS = ["Low", "Medium", "High"]


def split_dt(dt_val) -> Tuple[Optional[date], Optional[time]]:
    """Return (date, time) from a datetime/str/None."""
    if not dt_val:
        return None, None
    if isinstance(dt_val, str):
        try:
            dt_val = datetime.fromisoformat(dt_val)
        except Exception:
            return None, None
    return dt_val.date(), dt_val.time()


def pretty_due(dt_val) -> str:
    if not dt_val:
        return "None"
    if isinstance(dt_val, str):
        try:
            dt_val = datetime.fromisoformat(dt_val)
        except Exception:
            return dt_val
    return dt_val.strftime("%Y-%m-%d %H:%M")


def task_due_controls(idx: int, initial_dt=None, keyp: str = "c") -> Tuple[bool, Optional[datetime]]:
    """
    Renders calendar+time controls controlled by a checkbox.
      [ ] Has due date? idx
          Due date idx (calendar)
          Due time idx (time)
    Returns: (has_due, datetime|None)
    """
    init_d, init_t = split_dt(initial_dt)
    has_due_default = initial_dt is not None

    has_due = st.checkbox(
        f"Has due date? {idx}",
        value=has_due_default,
        key=f"{keyp}_t{idx}_has_due",
    )
    if has_due:
        d = st.date_input(
            f"Due date {idx}",
            value=init_d or date.today(),
            key=f"{keyp}_t{idx}_due_date",
        )
        t = st.time_input(
            f"Due time {idx}",
            value=init_t or time(9, 0),
            key=f"{keyp}_t{idx}_due_time",
        )
        return True, datetime.combine(d, t)
    else:
        return False, None


# -------------------------- Data structures -------------------------

@dataclass
class Task:
    row: int
    title: str
    status: str
    priority: str
    hours: Optional[float]
    due_at: Optional[datetime]
    notes: str


@dataclass
class Deliverable:
    id: str
    title: str
    owner: str
    unit: str
    term: str
    notes: str
    created_at: str
    tasks: List[Task]


# ----------------------------- State --------------------------------

def ensure_state():
    if "deliverables" not in st.session_state:
        st.session_state["deliverables"] = []
    # NEW: counters for how many task rows to draw
    st.session_state.setdefault("create_task_count", 3)  # default rows in Create

ensure_state()


# ------------------------ Infinite-task helpers ---------------------

def render_task_controls(count_key: str, base_key: str, min_rows: int = 1, max_rows: int = 50):
    """
    Add/Remove buttons that change how many task rows are rendered.
    These live outside submit buttons to avoid Streamlit form errors.
    """
    n = st.session_state.get(count_key, min_rows)
    c1, c2, _ = st.columns([1, 1, 6])
    with c1:
        if st.button("Add Task", key=f"{base_key}_add"):
            st.session_state[count_key] = min(n + 1, max_rows)
            _rerun()
    with c2:
        if st.button("Remove Last Task", key=f"{base_key}_rem", disabled=n <= min_rows):
            st.session_state[count_key] = max(n - 1, min_rows)
            _rerun()


def render_task_rows(n: int, base_key: str, existing: Optional[List[Dict]] = None) -> List[Dict]:
    """
    Renders n task rows (using the original controls, including the 'Has due date?' checkbox).
    Returns a list of task dicts (skips rows where title is blank).
    """
    existing = existing or []
    tasks: List[Dict] = []
    for i in range(1, n + 1):
        initial = next((t for t in existing if t.get("row") == i), None)

        st.markdown(f"#### Task {i} — title")
        title = st.text_input(
            f"Task {i} — title",
            value=(initial or {}).get("title", ""),
            key=f"{base_key}_t{i}_title",
            label_visibility="collapsed",
            placeholder="Task title",
        )
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            status = st.selectbox(
                "Status",
                STATUS_OPTS,
                index=(STATUS_OPTS.index((initial or {}).get("status"))
                       if (initial or {}).get("status") in STATUS_OPTS else 0),
                key=f"{base_key}_t{i}_status",
            )
        with c2:
            priority = st.selectbox(
                "Priority",
                PRIORITY_OPTS,
                index=(PRIORITY_OPTS.index((initial or {}).get("priority"))
                       if (initial or {}).get("priority") in PRIORITY_OPTS else 1),
                key=f"{base_key}_t{i}_priority",
            )
        with c3:
            hours = st.number_input(
                "Hours",
                min_value=0.0,
                step=0.5,
                value=float((initial or {}).get("hours") or 0),
                key=f"{base_key}_t{i}_hours",
            )

        has_due, due_at = task_due_controls(i, initial_dt=(initial or {}).get("due_at"), keyp=base_key)

        notes = st.text_area(
            f"Notes {i}",
            value=(initial or {}).get("notes", ""),
            key=f"{base_key}_t{i}_notes",
        )

        if title.strip():
            tasks.append(
                {
                    "row": i,
                    "title": title.strip(),
                    "status": status,
                    "priority": priority,
                    "hours": float(hours) if hours not in ("", None) else None,
                    "due_at": due_at if has_due else None,
                    "notes": notes.strip(),
                }
            )
        st.markdown("<hr/>", unsafe_allow_html=True)
    return tasks


# ------------------------------ Exports -----------------------------

def build_global_tables(items: List[Dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (deliverables_df, tasks_df, flattened_df) for a list of deliverables."""
    d_rows = []
    t_rows = []
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
                    "due_at": t.get("due_at").isoformat() if t.get("due_at") else None,
                    "notes": t.get("notes"),
                }
            )

    df_deliv = pd.DataFrame(d_rows)
    df_tasks = pd.DataFrame(t_rows)

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
                "due_at",
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


def export_tasks_csv(deliv: Dict) -> bytes:
    rows = []
    for t in deliv.get("tasks", []) or []:
        rows.append(
            {
                "#": t.get("row"),
                "Task": t.get("title"),
                "status": t.get("status"),
                "priority": t.get("priority"),
                "hours": t.get("hours"),
                "due_at": pretty_due(t.get("due_at")),
                "notes": t.get("notes"),
            }
        )
    df = pd.DataFrame(rows)
    s = io.StringIO()
    df.to_csv(s, index=False)
    return s.getvalue().encode("utf-8")


# ------------------------------ Filters -----------------------------

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


# --------------------------- CRUD operations ------------------------

def save_deliverable(new_deliv: Dict):
    st.session_state["deliverables"].append(new_deliv)


def update_deliverable(updated: Dict):
    for i, d in enumerate(st.session_state["deliverables"]):
        if d["id"] == updated["id"]:
            st.session_state["deliverables"][i] = updated
            return


def delete_deliverable(deliv_id: str):
    st.session_state["deliverables"] = [d for d in st.session_state["deliverables"] if d["id"] != deliv_id]


def confirm_modal(prompt: str, state_key: str, match_id: Optional[str] = None) -> bool:
    asked = st.session_state.get(state_key)
    if match_id is not None and asked != match_id:
        return False
    if not asked:
        return False

    with ui_modal("Confirm action"):
        st.warning(prompt)
        c1, c2 = st.columns(2)
        yes = c1.button("Yes, delete")
        no = c2.button("Cancel")
        if yes:
            st.session_state[state_key] = None
            return True
        if no:
            st.session_state[state_key] = None
            _rerun()
    return False


# ----------------------------- UI building --------------------------

def create_deliverable_form():
    # Controls to change number of task rows for CREATE (outside submit)
    st.markdown("### Tasks")
    render_task_controls("create_task_count", base_key="create_tasks")

    with st.form("create_deliv", clear_on_submit=True):
        st.subheader("Create deliverable")

        d_title = st.text_input("Deliverable title *", "")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        with c1:
            d_owner = st.text_input("Owner")
        with c2:
            d_unit = st.text_input("Unit")
        with c3:
            d_term = st.text_input("Term", help="e.g., 2025-1 or Fall 2025")
        with c4:
            d_notes = st.text_area("Deliverable notes", height=80)

        st.markdown("---")
        n_rows = st.session_state.get("create_task_count", 3)
        tasks: List[Dict] = render_task_rows(n_rows, base_key="c")

        submitted = st.form_submit_button("Save deliverable")
        if submitted:
            if not d_title.strip():
                st.error("Please enter a deliverable title.")
                return
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
            _rerun()


def edit_deliverable_modal(deliv: Dict):
    with ui_modal("Edit deliverable"):
        with st.form(f"edit_{deliv['id']}"):
            st.subheader("Edit deliverable")

            d_title = st.text_input("Deliverable title *", value=deliv.get("title", ""), key=f"e_{deliv['id']}_title")
            c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
            with c1:
                d_owner = st.text_input("Owner", value=deliv.get("owner", ""), key=f"e_{deliv['id']}_owner")
            with c2:
                d_unit = st.text_input("Unit", value=deliv.get("unit", ""), key=f"e_{deliv['id']}_unit")
            with c3:
                d_term = st.text_input("Term", value=deliv.get("term", ""), key=f"e_{deliv['id']}_term")
            with c4:
                d_notes = st.text_area("Deliverable notes", value=deliv.get("notes", ""), height=80, key=f"e_{deliv['id']}_notes")

            st.markdown("---")
            st.markdown("### Tasks")
            # Per-deliverable counter for EDIT
            cnt_key = f"edit_{deliv['id']}_task_count"
            if cnt_key not in st.session_state:
                st.session_state[cnt_key] = max(1, len(deliv.get("tasks", []) or []))

            render_task_controls(cnt_key, base_key=f"edit_{deliv['id']}_tasks")
            existing = deliv.get("tasks", []) or []
            tasks: List[Dict] = render_task_rows(st.session_state[cnt_key], base_key=f"e_{deliv['id']}", existing=existing)

            btns = st.columns(2)
            with btns[0]:
                saved = st.form_submit_button("Save changes")
            with btns[1]:
                cancel = st.form_submit_button("Cancel")

            if saved:
                if not d_title.strip():
                    st.error("Please enter a deliverable title.")
                    return
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
                update_deliverable(updated)
                st.success("Updated.")
                # clear the edit counter for this deliverable
                st.session_state.pop(cnt_key, None)
                _rerun()
            if cancel:
                st.session_state.pop(cnt_key, None)
                _rerun()


def show_deliverable_card(deliv: Dict):
    with st.expander(f"{deliv['title']} — {deliv.get('owner','')}", expanded=False):
        st.caption(
            f"ID: `{deliv['id']}` · created {deliv.get('created_at','')}"
        )
        if deliv.get("notes"):
            st.markdown(f"**Notes:** {deliv['notes']}")

        tasks = deliv.get("tasks", []) or []
        if not tasks:
            st.info("No tasks added.")
        else:
            rows = []
            for t in tasks:
                rows.append(
                    {
                        "#": t.get("row"),
                        "Task": t.get("title"),
                        "status": t.get("status"),
                        "priority": t.get("priority"),
                        "hours": t.get("hours"),
                        "Due": pretty_due(t.get("due_at")),
                        "notes": t.get("notes"),
                    }
                )
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

        c1, c2, c3, _ = st.columns([1, 1, 1, 6])
        with c1:
            if st.button("Edit", key=f"edit_{deliv['id']}"):
                st.session_state["edit_id"] = deliv["id"]
                _rerun()
        with c2:
            if st.button("Delete", key=f"del_{deliv['id']}"):
                st.session_state["ask_delete_one"] = deliv["id"]
        with c3:
            st.download_button(
                "Download tasks (CSV)",
                data=export_tasks_csv(deliv),
                file_name=f"{deliv['title']}_tasks.csv",
                mime="text/csv",
                key=f"dl_csv_{deliv['id']}",
            )


# ------------------------------- Layout -----------------------------

# Short create form in an expander
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
        _rerun()
with pc2:
    if st.button("Next", disabled=st.session_state["page"] >= pages):
        st.session_state["page"] += 1
        _rerun()
with pc3:
    st.caption(f"Page {st.session_state['page']} / {pages} • {len(filtered)} match(es)")

page_items, _ = paginate(filtered, st.session_state["page"], per_page)

# Inline Edit modal launcher
if st.session_state.get("edit_id"):
    ed = next((d for d in items if d["id"] == st.session_state["edit_id"]), None)
    if ed:
        edit_deliverable_modal(ed)
        st.session_state["edit_id"] = None

# Delete confirm
for d in page_items:
    if confirm_modal(
        f"Delete deliverable '{d['title']}'? This cannot be undone.",
        "ask_delete_one",
        match_id=d["id"],
    ):
        delete_deliverable(d["id"])
        st.success("Deleted.")
        _rerun()

if not page_items:
    st.info("No deliverables match the current filters.")
else:
    for d in page_items:
        show_deliverable_card(d)
