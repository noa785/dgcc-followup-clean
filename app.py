# app.py — DGCC Follow-up Manager (clean, single file)

from __future__ import annotations

import io
from dataclasses import dataclass, asdict
from datetime import date, time, datetime
from typing import List, Dict, Optional, Tuple

import pandas as pd
import streamlit as st


# ------------------------------------------------------------
# Page config / compact style
# ------------------------------------------------------------
st.set_page_config(page_title="DGCC Follow-up Manager", layout="wide")
st.markdown(
    """
    <style>
      .block-container {max-width: 1180px;}
      [data-testid="stForm"] input, 
      [data-testid="stForm"] textarea,
      [data-testid="stForm"] select { margin-bottom:.45rem; }
      .card {border:1px solid #e5e7eb;border-radius:12px;padding:16px 18px;margin-bottom:14px;}
      .soft {color:#6b7280;}
      .tight {margin-top:.25rem;margin-bottom:.25rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# Session boot
# ------------------------------------------------------------
if "deliverables" not in st.session_state:
    st.session_state["deliverables"]: List[Dict] = []

# fixed choices (you can edit these lists)
if "vars" not in st.session_state:
    st.session_state["vars"] = {
        "status": ["Not started", "In progress", "Blocked", "Done"],
        "priority": ["Low", "Medium", "High"],
        "owners": [],
    }

if "edit_open" not in st.session_state:
    # which deliverable ID is being edited inline (one at a time)
    st.session_state["edit_open"] = None

# ------------------------------------------------------------
# Models / helpers
# ------------------------------------------------------------
def generate_id() -> str:
    # simple short id
    return pd.util.hash_pandas_object(pd.Series([datetime.utcnow().isoformat()])).astype(str).iat[0][-10:]


@dataclass
class Task:
    row: int
    title: str
    status: str
    priority: str
    hours: Optional[float]
    due: Optional[str]  # ISO datetime string or None
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


def build_task(
    idx: int,
    title: str,
    status: str,
    priority: str,
    hours: Optional[float],
    due_iso: Optional[str],
    notes: str,
) -> Optional[Task]:
    """Return a Task if title is non-empty, else None."""
    t = (title or "").strip()
    if not t:
        return None
    return Task(
        row=idx,
        title=t,
        status=status,
        priority=priority,
        hours=float(hours) if hours not in (None, "") else None,
        due=due_iso,
        notes=(notes or "").strip(),
    )


def task_due_controls(idx: int, initial_dt=None, keyp: str = "c") -> tuple[bool, Optional[datetime]]:
    """
    Calendar + time gated by a checkbox.
    When checked: real st.date_input + st.time_input.
    Returns (has_due, datetime|None).
    """
    init_date = init_time = None
    if isinstance(initial_dt, str):
        try:
            initial_dt = datetime.fromisoformat(initial_dt)
        except Exception:
            initial_dt = None
    if isinstance(initial_dt, datetime):
        init_date, init_time = initial_dt.date(), initial_dt.time()

    has_due_default = initial_dt is not None
    has_due = st.checkbox(f"Has due date? {idx}", value=has_due_default, key=f"{keyp}_t{idx}_has_due")

    if has_due:
        d = st.date_input(
            f"Due date {idx}",
            value=init_date or date.today(),
            key=f"{keyp}_t{idx}_due_date",
            format="YYYY-MM-DD",
        )
        t = st.time_input(
            f"Due time {idx}",
            value=init_time or time(9, 0),
            step=900,
            key=f"{keyp}_t{idx}_due_time",
        )
        return True, datetime.combine(d, t)

    st.caption(f"Due date {idx}: not set")
    return False, None


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


# ------------------------------------------------------------
# Export helpers (filtered → CSV / Excel) & per-deliverable
# ------------------------------------------------------------
def build_global_tables(items: List[Dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    d_rows, t_rows = [], []
    for d in items:
        d_rows.append(
            dict(
                id=d["id"],
                title=d.get("title", ""),
                owner=d.get("owner", ""),
                unit=d.get("unit", ""),
                term=d.get("term", ""),
                created_at=d.get("created_at", ""),
                notes=d.get("notes", ""),
            )
        )
        for t in d.get("tasks", []) or []:
            t_rows.append(
                dict(
                    deliverable_id=d["id"],
                    deliverable_title=d.get("title", ""),
                    row=t.get("row"),
                    title=t.get("title"),
                    status=t.get("status"),
                    priority=t.get("priority"),
                    hours=t.get("hours"),
                    due=t.get("due"),
                    notes=t.get("notes"),
                )
            )
    df_deliv = pd.DataFrame(d_rows)
    df_tasks = pd.DataFrame(t_rows)
    df_flat = df_tasks.copy() if len(df_tasks) else pd.DataFrame(
        columns=["deliverable_id", "deliverable_title", "row", "title", "status", "priority", "hours", "due", "notes"]
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


def export_deliverable_csv(deliv: Dict) -> bytes:
    rows = []
    for t in deliv.get("tasks", []) or []:
        rows.append(dict(
            deliverable_title=deliv["title"],
            row=t.get("row"),
            title=t.get("title"),
            status=t.get("status"),
            priority=t.get("priority"),
            hours=t.get("hours"),
            due=t.get("due"),
            notes=t.get("notes"),
        ))
    df = pd.DataFrame(rows)
    buff = io.StringIO()
    df.to_csv(buff, index=False)
    return buff.getvalue().encode("utf-8")


# ------------------------------------------------------------
# UI: Create form (expander)
# ------------------------------------------------------------
def create_deliverable_form():
    with st.form("create_form", clear_on_submit=False):
        st.subheader("Create deliverable")
        t_title = st.text_input("Deliverable title *", key="c_title")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        with c1:
            t_owner = st.text_input("Owner", key="c_owner")
        with c2:
            t_unit = st.text_input("Unit", key="c_unit")
        with c3:
            t_term = st.text_input("Term", key="c_term")
        with c4:
            t_notes = st.text_area("Deliverable notes", key="c_notes", height=80)

        st.markdown("### Tasks (up to 5)")

        tasks: List[Task] = []
        for i in range(1, 6):
            st.markdown(f"**Task {i}**")
            c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
            title = c1.text_input(f"Task {i} — title", key=f"c_t{i}_title")
            status = c2.selectbox(f"Status {i}", st.session_state["vars"]["status"], key=f"c_t{i}_status")
            priority = c3.selectbox(f"Priority {i}", st.session_state["vars"]["priority"], key=f"c_t{i}_priority")
            hours = c4.number_input(f"Hours {i}", min_value=0.0, step=0.5, key=f"c_t{i}_hours")

            has_due, due_dt = task_due_controls(i, initial_dt=None, keyp="c")

            notes = st.text_area(f"Notes {i}", key=f"c_t{i}_notes", height=90)

            t = build_task(
                i,
                title,
                status,
                priority,
                hours,
                due_dt.isoformat() if due_dt else None,
                notes,
            )
            if t:
                tasks.append(t)

            st.divider()

        submitted = st.form_submit_button("Save deliverable")
        if submitted:
            if not (t_title or "").strip():
                st.error("Deliverable title is required.")
                st.stop()
            d = Deliverable(
                id=generate_id(),
                title=t_title.strip(),
                owner=t_owner.strip(),
                unit=t_unit.strip(),
                term=t_term.strip(),
                notes=t_notes.strip(),
                created_at=datetime.utcnow().isoformat(timespec="seconds"),
                tasks=tasks,
            )
            st.session_state["deliverables"].append(
                dict(
                    id=d.id,
                    title=d.title,
                    owner=d.owner,
                    unit=d.unit,
                    term=d.term,
                    notes=d.notes,
                    created_at=d.created_at,
                    tasks=[asdict(x) for x in d.tasks],
                )
            )
            st.success("Deliverable added.")
            # clear inputs but keep expander collapsed
            for k in [k for k in st.session_state.keys() if k.startswith("c_")]:
                del st.session_state[k]
            st.experimental_rerun()


# ------------------------------------------------------------
# UI: Inline editor inside each card (no sidebar, no modal)
# ------------------------------------------------------------
def edit_deliverable_inline(deliv: Dict):
    """Render an inline editor inside the card, pre-filled with stored values."""
    dkey = f"e_{deliv['id']}"
    with st.form(f"edit_form_{deliv['id']}"):
        st.markdown("**Edit deliverable**")
        t_title = st.text_input("Deliverable title *", value=deliv.get("title",""), key=f"{dkey}_title")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        with c1:
            t_owner = st.text_input("Owner", value=deliv.get("owner",""), key=f"{dkey}_owner")
        with c2:
            t_unit = st.text_input("Unit", value=deliv.get("unit",""), key=f"{dkey}_unit")
        with c3:
            t_term = st.text_input("Term", value=deliv.get("term",""), key=f"{dkey}_term")
        with c4:
            t_notes = st.text_area("Deliverable notes", value=deliv.get("notes",""), key=f"{dkey}_notes", height=80)

        st.markdown("### Tasks")
        new_tasks: List[Task] = []

        # Existing tasks first (keep original order)
        current = deliv.get("tasks", []) or []
        count = max(5, len(current))
        for i in range(1, count + 1):
            # prefer existing slot; else blank
            t_old = current[i-1] if i-1 < len(current) else {}
            st.markdown(f"**Task {i}**")

            c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
            title = c1.text_input(f"Task {i} — title", value=t_old.get("title",""), key=f"{dkey}_t{i}_title")
            # safe index for status/priority
            s_opts = st.session_state["vars"]["status"]
            p_opts = st.session_state["vars"]["priority"]

            def _safe_index(lst, val, default=0):
                try:
                    return max(0, lst.index(val))
                except Exception:
                    return default

            status = c2.selectbox(
                f"Status {i}", s_opts, index=_safe_index(s_opts, t_old.get("status")), key=f"{dkey}_t{i}_status"
            )
            priority = c3.selectbox(
                f"Priority {i}", p_opts, index=_safe_index(p_opts, t_old.get("priority"), 1), key=f"{dkey}_t{i}_priority"
            )
            hours = c4.number_input(
                f"Hours {i}", min_value=0.0, step=0.5, value=float(t_old.get("hours") or 0.0), key=f"{dkey}_t{i}_hours"
            )

            has_due, due_dt = task_due_controls(i, initial_dt=t_old.get("due"), keyp=dkey)
            notes = st.text_area(f"Notes {i}", value=t_old.get("notes",""), key=f"{dkey}_t{i}_notes", height=90)

            t_new = build_task(
                i,
                title,
                status,
                priority,
                hours,
                due_dt.isoformat() if due_dt else None,
                notes,
            )
            if t_new:
                new_tasks.append(t_new)

            st.divider()

        c_save, c_cancel = st.columns([1,1])
        do_save = c_save.form_submit_button("Save changes")
        do_cancel = c_cancel.form_submit_button("Cancel")

        if do_cancel:
            st.session_state["edit_open"] = None
            st.experimental_rerun()

        if do_save:
            if not (t_title or "").strip():
                st.error("Deliverable title is required.")
                st.stop()
            updated = dict(
                id=deliv["id"],
                title=t_title.strip(),
                owner=t_owner.strip(),
                unit=t_unit.strip(),
                term=t_term.strip(),
                notes=t_notes.strip(),
                created_at=deliv.get("created_at") or datetime.utcnow().isoformat(timespec="seconds"),
                tasks=[asdict(x) for x in new_tasks],
            )
            # replace
            items = st.session_state["deliverables"]
            for i, d in enumerate(items):
                if d["id"] == deliv["id"]:
                    items[i] = updated
                    break
            st.success("Changes saved.")
            st.session_state["edit_open"] = None
            st.experimental_rerun()


# ------------------------------------------------------------
# UI: One deliverable card
# ------------------------------------------------------------
def show_deliverable_card(deliv: Dict):
    with st.container():
        st.markdown('<div class="card">', unsafe_allow_html=True)

        # header
        st.markdown(f"**{deliv['title']}** — {deliv.get('unit','')}")
        st.caption(f"ID: `{deliv['id']}` • created {deliv.get('created_at','')}")
        if deliv.get("notes"):
            st.markdown(f"**Notes:** {deliv['notes']}")

        # tasks table
        df = pd.DataFrame(deliv.get("tasks", []) or [])
        if len(df):
            df_view = df[["row", "title", "status", "priority", "hours", "due", "notes"]].copy()
            df_view.rename(columns={"row": "#", "due": "Due"}, inplace=True)
            st.dataframe(df_view, use_container_width=True, hide_index=True)
        else:
            st.info("No tasks added.")

        # actions
        c1, c2, c3 = st.columns([1,1,1])
        if c1.button("Edit", key=f"edit_{deliv['id']}"):
            st.session_state["edit_open"] = deliv["id"]
            st.experimental_rerun()

        # delete (two-step inline)
        confirm_flag = f"ask_del_{deliv['id']}"
        ask_delete = c2.button("Delete", key=f"del_btn_{deliv['id']}")
        if ask_delete:
            st.session_state[confirm_flag] = True
            st.experimental_rerun()

        if st.session_state.get(confirm_flag):
            st.warning("Delete this deliverable? This cannot be undone.")
            c_ok, c_no = st.columns([1,1])
            if c_ok.button("Yes, delete", key=f"del_yes_{deliv['id']}"):
                st.session_state["deliverables"] = [d for d in st.session_state["deliverables"] if d["id"] != deliv["id"]]
                st.session_state[confirm_flag] = False
                st.success("Deleted.")
                st.experimental_rerun()
            if c_no.button("Cancel", key=f"del_no_{deliv['id']}"):
                st.session_state[confirm_flag] = False
                st.experimental_rerun()

        # per-deliverable download
        st.download_button(
            "Download tasks (CSV)",
            data=export_deliverable_csv(deliv),
            file_name=f"{deliv['title']}_tasks.csv",
            mime="text/csv",
        )

        # inline editor (in place)
        if st.session_state["edit_open"] == deliv["id"]:
            st.divider()
            edit_deliverable_inline(deliv)

        st.markdown("</div>", unsafe_allow_html=True)


# ------------------------------------------------------------
# App
# ------------------------------------------------------------
st.title("DGCC Follow-up Manager")

# Create form expander (compact)
with st.expander("Create deliverable", expanded=False):
    create_deliverable_form()

st.subheader("Deliverables")

# Filters & pagination
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

items_all = st.session_state["deliverables"]
filtered = filter_deliverables(items_all, f_term, f_owner, f_query)

# global downloads of the current filtered set
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
        st.experimental_rerun()
with pc2:
    if st.button("Next", disabled=st.session_state["page"] >= pages):
        st.session_state["page"] += 1
        st.experimental_rerun()
with pc3:
    st.caption(f"Page {st.session_state['page']} / {pages} • {len(filtered)} match(es)")

page_items, _ = paginate(filtered, st.session_state["page"], per_page)

# list
if not page_items:
    st.info("No deliverables match the current filters.")
else:
    for d in page_items:
        show_deliverable_card(d)
