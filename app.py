# app.py — DGCC Follow-up Manager
# Infinite deliverables + infinite tasks + infinite variables
# -----------------------------------------------------------
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
.block-container { max-width: 1100px; }
.stExpander { border: 1px solid #e5e7eb; border-radius: 12px; }
[data-testid="stForm"] .stTextInput,
[data-testid="stForm"] .stTextArea,
[data-testid="stForm"] .stSelectbox,
[data-testid="stForm"] .stNumberInput,
[data-testid="stForm"] .stDateInput,
[data-testid="stForm"] .stTimeInput { margin-bottom: .4rem; }
hr { border: none; border-top: 1px solid #eee; margin: .75rem 0; }
.hint { background:#fff7ed; border:1px solid #fed7aa; padding:.5rem .75rem; border-radius:.5rem; }
</style>
""",
    unsafe_allow_html=True,
)
st.title("DGCC Follow-up Manager")

# ---------------------- Helpers & compatibility --------------------
def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

@contextmanager
def ui_modal(title: str):
    if hasattr(st, "modal"):
        with st.modal(title):
            yield
    else:
        st.sidebar.markdown(f"### {title}")
        with st.sidebar.container():
            yield

def generate_id() -> str:
    return datetime.utcnow().strftime("%y%m%d%H%M%S%f")[-10:]

STATUS_OPTS   = ["Not started", "In progress", "Blocked", "Done"]
PRIORITY_OPTS = ["Low", "Medium", "High"]

def split_dt(dt_val) -> Tuple[Optional[date], Optional[time]]:
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

# -------------------------- Data structures ------------------------
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
    vars: List[Dict[str, str]]

# ------------------------------ State ------------------------------
def ensure_state():
    st.session_state.setdefault("deliverables", [])

    # Batch-create controls
    st.session_state.setdefault("create_deliv_count", 1)  # number of deliverable blocks visible

    # For each deliverable block i (1..N) we track its own task/var counts.
    # We'll initialize lazily when rendering.
ensure_state()

def _ensure_block_counts(i: int):
    st.session_state.setdefault(f"c{i}_task_count", 3)
    st.session_state.setdefault(f"c{i}_var_count", 1)

# ------------------------------ Exports ----------------------------
def build_global_tables(items: List[Dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    d_rows, t_rows, v_rows = [], [], []
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
            due = t.get("due_at")
            t_rows.append(
                {
                    "deliverable_id": d["id"],
                    "deliverable_title": d.get("title", ""),
                    "row": t.get("row"),
                    "title": t.get("title"),
                    "status": t.get("status"),
                    "priority": t.get("priority"),
                    "hours": t.get("hours"),
                    "due_at": due.isoformat() if isinstance(due, datetime) else (due or None),
                    "notes": t.get("notes"),
                }
            )
        for j, kv in enumerate(d.get("vars", []) or [], start=1):
            v_rows.append(
                {
                    "deliverable_id": d["id"],
                    "deliverable_title": d.get("title", ""),
                    "row": j,
                    "name": kv.get("name", ""),
                    "value": kv.get("value", ""),
                }
            )
    df_deliv = pd.DataFrame(d_rows)
    df_tasks = pd.DataFrame(t_rows)
    df_vars  = pd.DataFrame(v_rows)
    df_flat  = df_tasks.copy() if len(df_tasks) else pd.DataFrame(
        columns=["deliverable_id","deliverable_title","row","title","status","priority","hours","due_at","notes"]
    )
    if not len(df_vars):
        df_vars = pd.DataFrame(columns=["deliverable_id","deliverable_title","row","name","value"])
    return df_deliv, df_tasks, df_flat, df_vars

def export_filtered_csv(items: List[Dict]) -> bytes:
    _, _, df_flat, _ = build_global_tables(items)
    s = io.StringIO(); df_flat.to_csv(s, index=False); return s.getvalue().encode("utf-8")

def export_filtered_excel(items: List[Dict]) -> bytes:
    df_deliv, df_tasks, df_flat, df_vars = build_global_tables(items)
    b = io.BytesIO()
    with pd.ExcelWriter(b, engine="xlsxwriter") as w:
        df_deliv.to_excel(w, index=False, sheet_name="deliverables")
        df_tasks.to_excel(w, index=False, sheet_name="tasks")
        df_flat.to_excel(w, index=False, sheet_name="flattened")
        df_vars.to_excel(w, index=False, sheet_name="variables")
    return b.getvalue()

def export_tasks_csv(deliv: Dict) -> bytes:
    rows = []
    for t in deliv.get("tasks", []) or []:
        rows.append(
            {"#": t.get("row"), "Task": t.get("title"), "status": t.get("status"),
             "priority": t.get("priority"), "hours": t.get("hours"),
             "due_at": pretty_due(t.get("due_at")), "notes": t.get("notes")}
        )
    df = pd.DataFrame(rows); s = io.StringIO(); df.to_csv(s, index=False); return s.getvalue().encode("utf-8")

# ------------------------------ Filters ----------------------------
def filter_deliverables(items: List[Dict], term: str, owner: str, query: str) -> List[Dict]:
    term = (term or "").strip().lower(); owner = (owner or "").strip().lower(); query = (query or "").strip().lower()
    out = []
    for d in items:
        if term and term not in (d.get("term","").lower()): continue
        if owner and owner not in (d.get("owner","").lower()): continue
        hay = " ".join([d.get("title",""), d.get("unit",""), d.get("notes","")]).lower()
        if query and query not in hay: continue
        out.append(d)
    return out

def paginate(items: List[Dict], page: int, per_page: int) -> Tuple[List[Dict], int]:
    total = len(items); start = (page-1)*per_page; end = start + per_page
    return items[start:end], total

# --------------------------- CRUD ops ------------------------------
def save_deliverable(new_deliv: Dict): st.session_state["deliverables"].append(new_deliv)

def update_deliverable(updated: Dict):
    for i, d in enumerate(st.session_state["deliverables"]):
        if d["id"] == updated["id"]:
            st.session_state["deliverables"][i] = updated; return

def delete_deliverable(deliv_id: str):
    st.session_state["deliverables"] = [d for d in st.session_state["deliverables"] if d["id"] != deliv_id]

def confirm_modal(prompt: str, state_key: str, match_id: Optional[str] = None) -> bool:
    asked = st.session_state.get(state_key)
    if match_id is not None and asked != match_id: return False
    if not asked: return False
    with ui_modal("Confirm action"):
        st.warning(prompt)
        c1, c2 = st.columns(2)
        yes = c1.button("Yes, delete"); no = c2.button("Cancel")
        if yes: st.session_state[state_key] = None; return True
        if no:  st.session_state[state_key] = None; _rerun()
    return False

# ----------------------------- UI pieces ---------------------------
def task_inputs(i: int, keyp: str, initial: Optional[Dict] = None) -> Optional[Dict]:
    initial = initial or {}
    st.markdown(f"#### Task {i} — title")
    title = st.text_input(f"Task {i} — title", value=initial.get("title",""),
                          key=f"{keyp}_t{i}_title", label_visibility="collapsed",
                          placeholder="Task title")
    c1, c2, c3 = st.columns([1,1,1])
    with c1:
        status = st.selectbox("Status", STATUS_OPTS,
                              index=(STATUS_OPTS.index(initial.get("status")) if initial.get("status") in STATUS_OPTS else 0),
                              key=f"{keyp}_t{i}_status")
    with c2:
        priority = st.selectbox("Priority", PRIORITY_OPTS,
                                index=(PRIORITY_OPTS.index(initial.get("priority")) if initial.get("priority") in PRIORITY_OPTS else 1),
                                key=f"{keyp}_t{i}_priority")
    with c3:
        hours = st.number_input("Hours", min_value=0.0, step=0.5,
                                value=float(initial.get("hours") or 0),
                                key=f"{keyp}_t{i}_hours")

    init_d, init_t = split_dt(initial.get("due_at"))
    dc1, dc2 = st.columns([1,1])
    with dc1:
        d = st.date_input(f"Due date {i}", value=init_d or date.today(), key=f"{keyp}_t{i}_due_date")
    with dc2:
        t = st.time_input(f"Due time {i}", value=init_t or time(9,0), key=f"{keyp}_t{i}_due_time")
    due_at = datetime.combine(d, t) if d and t else None

    notes = st.text_area(f"Notes {i}", value=initial.get("notes",""),
                         key=f"{keyp}_t{i}_notes", placeholder="Notes (optional)")

    if not title.strip(): return None
    return {"row": i, "title": title.strip(), "status": status, "priority": priority,
            "hours": float(hours) if hours not in ("", None) else None,
            "due_at": due_at, "notes": notes.strip()}

def var_inputs(i: int, keyp: str, initial: Optional[Dict] = None) -> Optional[Dict]:
    initial = initial or {}
    c1, c2 = st.columns([1,2])
    with c1:
        name = st.text_input(f"Variable {i} — name", value=initial.get("name",""),
                             key=f"{keyp}_v{i}_name", placeholder="e.g., Milestone")
    with c2:
        value = st.text_input(f"Variable {i} — value", value=initial.get("value",""),
                              key=f"{keyp}_v{i}_value", placeholder="e.g., Phase 1 / Link / Budget")
    if not (name or value):
        return None
    return {"name": name.strip(), "value": value.strip()}

def render_task_rows(n: int, base_key: str, existing: Optional[List[Dict]] = None) -> List[Dict]:
    existing = existing or []
    tasks: List[Dict] = []
    for i in range(1, n + 1):
        initial = next((t for t in existing if t.get("row") == i), None)
        with st.container():
            t = task_inputs(i, keyp=f"{base_key}_{i}", initial=initial)
            if t: tasks.append(t)
            st.markdown("<hr/>", unsafe_allow_html=True)
    return tasks

def render_var_rows(n: int, base_key: str, existing: Optional[List[Dict]] = None) -> List[Dict]:
    existing = existing or []
    out: List[Dict] = []
    for i in range(1, n + 1):
        initial = existing[i-1] if i-1 < len(existing) else None
        with st.container():
            kv = var_inputs(i, keyp=f"{base_key}_{i}", initial=initial)
            if kv: out.append(kv)
    return out

def render_controls(count_key: str, base_key: str, label: str, key_suffix: str, min_rows: int = 1, max_rows: int = 50):
    n = st.session_state.get(count_key, min_rows)
    c1, c_mid, c2 = st.columns([1,3,1])
    with c1:
        if st.button(f"➕ Add {label}", key=f"{base_key}_{key_suffix}_add"):
            st.session_state[count_key] = min(n + 1, max_rows); _rerun()
    with c_mid:
        st.caption(f"{label}s visible: **{n}**")
    with c2:
        if st.button(f"➖ Remove Last {label}", key=f"{base_key}_{key_suffix}_rem", disabled=n <= min_rows):
            st.session_state[count_key] = max(n - 1, min_rows); _rerun()

# ---------------------- Batch CREATE (infinite) --------------------
def create_deliverables_section():
    # 1) Top-level controls to add/remove deliverable blocks (outside the form)
    c1, c2, _ = st.columns([1,1,6])
    with c1:
        if st.button("➕ Add Deliverable", key="add_deliv"):
            st.session_state["create_deliv_count"] = min(st.session_state["create_deliv_count"] + 1, 30)
            _rerun()
    with c2:
        if st.button("➖ Remove Last Deliverable", key="rem_deliv", disabled=st.session_state["create_deliv_count"] <= 1):
            st.session_state["create_deliv_count"] = max(st.session_state["create_deliv_count"] - 1, 1)
            _rerun()
    st.caption(f"Deliverable blocks visible: **{st.session_state['create_deliv_count']}**")
    st.markdown("---")

    # 2) Per-block controls (outside form) for tasks/vars
    N = st.session_state["create_deliv_count"]
    for i in range(1, N + 1):
        _ensure_block_counts(i)
        st.markdown(f"### Deliverable {i} — controls")
        render_controls(f"c{i}_task_count", base_key=f"c{i}_tasks", label="Task", key_suffix="top")
        render_controls(f"c{i}_var_count",  base_key=f"c{i}_vars",  label="Variable", key_suffix="top")
        st.markdown("---")

    # 3) Single form containing ALL deliverable blocks
    with st.form("create_batch", clear_on_submit=True):
        st.subheader("Create deliverables (batch)")

        all_new: List[Dict] = []
        for i in range(1, N + 1):
            st.markdown(f"## Deliverable {i}")
            _ensure_block_counts(i)

            # Core deliverable fields
            d_title = st.text_input(f"[D{i}] Title *", key=f"D{i}_title")
            c1, c2, c3, c4 = st.columns([1,1,1,2])
            with c1: d_owner = st.text_input(f"[D{i}] Owner", key=f"D{i}_owner")
            with c2: d_unit  = st.text_input(f"[D{i}] Unit",  key=f"D{i}_unit")
            with c3: d_term  = st.text_input(f"[D{i}] Term",  key=f"D{i}_term", help="e.g., 2025-1 or Fall 2025")
            with c4: d_notes = st.text_area(f"[D{i}] Notes", key=f"D{i}_notes", height=80)

            # Tasks
            st.markdown("---")
            st.markdown(f"#### [D{i}] Tasks ({st.session_state[f'c{i}_task_count']})")
            tasks = render_task_rows(st.session_state[f"c{i}_task_count"], base_key=f"D{i}_t", existing=None)

            # Variables
            st.markdown(f"#### [D{i}] Variables ({st.session_state[f'c{i}_var_count']})")
            st.markdown('<div class="hint">Tip: Use variables for any extra fields (Milestone, Budget, Link...).</div>', unsafe_allow_html=True)
            vars_list = render_var_rows(st.session_state[f"c{i}_var_count"], base_key=f"D{i}_v", existing=None)

            all_new.append({
                "_title": d_title, "_owner": d_owner, "_unit": d_unit, "_term": d_term, "_notes": d_notes,
                "_tasks": tasks, "_vars": vars_list,
            })
            st.markdown("---")

        submitted = st.form_submit_button("Save all deliverables")
        if submitted:
            ok_any = False
            for block in all_new:
                if not (block["_title"] or block["_owner"] or block["_unit"] or block["_term"] or block["_notes"] or block["_tasks"] or block["_vars"]):
                    # Completely empty block → skip silently
                    continue
                if not (block["_title"] or "").strip():
                    st.error("Each non-empty deliverable needs a Title. Please fill or leave the whole block empty.")
                    return
                new_deliv = {
                    "id": generate_id(),
                    "title": block["_title"].strip(),
                    "owner": (block["_owner"] or "").strip(),
                    "unit": (block["_unit"] or "").strip(),
                    "term": (block["_term"] or "").strip(),
                    "notes": (block["_notes"] or "").strip(),
                    "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                    "tasks": block["_tasks"],
                    "vars": block["_vars"],
                }
                save_deliverable(new_deliv)
                ok_any = True
            if ok_any:
                st.success("Deliverables added.")
                # reset counts and clear form
                st.session_state["create_deliv_count"] = 1
                st.session_state["c1_task_count"] = 3
                st.session_state["c1_var_count"]  = 1
                _rerun()
            else:
                st.info("Nothing to save — all blocks were empty.")

# ------------------------------ EDIT -------------------------------
def edit_deliverable_modal(deliv: Dict):
    t_cnt = f"edit_{deliv['id']}_task_count"
    v_cnt = f"edit_{deliv['id']}_var_count"
    if t_cnt not in st.session_state:
        st.session_state[t_cnt] = max(1, len(deliv.get("tasks", []) or []))
    if v_cnt not in st.session_state:
        st.session_state[v_cnt] = max(1, len(deliv.get("vars", []) or []))

    with ui_modal("Edit deliverable"):
        # Controls outside the form
        st.markdown("### Tasks")
        render_controls(t_cnt, base_key=f"e_{deliv['id']}_tasks", label="Task", key_suffix="top")
        st.markdown("### Custom variables")
        render_controls(v_cnt, base_key=f"e_{deliv['id']}_vars", label="Variable", key_suffix="top")
        st.markdown("---")

        with st.form(f"edit_{deliv['id']}"):
            st.subheader("Edit deliverable")
            d_title = st.text_input("Deliverable title *", value=deliv.get("title",""), key=f"e_{deliv['id']}_title")
            c1, c2, c3, c4 = st.columns([1,1,1,2])
            with c1: d_owner = st.text_input("Owner", value=deliv.get("owner",""), key=f"e_{deliv['id']}_owner")
            with c2: d_unit  = st.text_input("Unit",  value=deliv.get("unit",""),  key=f"e_{deliv['id']}_unit")
            with c3: d_term  = st.text_input("Term",  value=deliv.get("term",""),  key=f"e_{deliv['id']}_term")
            with c4: d_notes = st.text_area("Deliverable notes", value=deliv.get("notes",""), height=80, key=f"e_{deliv['id']}_notes")

            existing_tasks = deliv.get("tasks", []) or []
            tasks = render_task_rows(st.session_state.get(t_cnt,1), base_key=f"e_{deliv['id']}_t", existing=existing_tasks)

            st.markdown(f"#### Variables ({st.session_state.get(v_cnt,1)})")
            existing_vars = deliv.get("vars", []) or []
            vars_list = render_var_rows(st.session_state.get(v_cnt,1), base_key=f"e_{deliv['id']}_v", existing=existing_vars)

            btns = st.columns(2)
            with btns[0]:
                saved = st.form_submit_button("Save changes")
            with btns[1]:
                cancel = st.form_submit_button("Cancel")

            if saved:
                if not d_title.strip():
                    st.error("Please enter a deliverable title."); return
                updated = {
                    "id": deliv["id"],
                    "title": d_title.strip(),
                    "owner": d_owner.strip(),
                    "unit": d_unit.strip(),
                    "term": d_term.strip(),
                    "notes": d_notes.strip(),
                    "created_at": deliv.get("created_at") or datetime.utcnow().isoformat(timespec="seconds"),
                    "tasks": tasks,
                    "vars": vars_list,
                }
                update_deliverable(updated)
                st.success("Updated.")
                st.session_state.pop(t_cnt, None); st.session_state.pop(v_cnt, None)
                _rerun()
            if cancel:
                st.session_state.pop(t_cnt, None); st.session_state.pop(v_cnt, None)
                _rerun()

# ------------------------------ Cards ------------------------------
def show_deliverable_card(deliv: Dict):
    with st.expander(f"{deliv['title']} — {deliv.get('owner','')}", expanded=False):
        st.caption(f"ID: `{deliv['id']}` · created {deliv.get('created_at','')}")
        if deliv.get("notes"):
            st.markdown(f"**Notes:** {deliv['notes']}")

        vars_list = deliv.get("vars", []) or []
        if vars_list:
            st.markdown("**Variables**")
            st.dataframe(pd.DataFrame(vars_list), use_container_width=True, hide_index=True)

        tasks = deliv.get("tasks", []) or []
        if not tasks:
            st.info("No tasks added.")
        else:
            rows = [{
                "#": t.get("row"), "Task": t.get("title"), "status": t.get("status"),
                "priority": t.get("priority"), "hours": t.get("hours"),
                "Due": pretty_due(t.get("due_at")), "notes": t.get("notes"),
            } for t in tasks]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        c1, c2, c3, _ = st.columns([1,1,1,6])
        with c1:
            if st.button("Edit", key=f"edit_{deliv['id']}"):
                st.session_state["edit_id"] = deliv["id"]; _rerun()
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

# ------------------------------- Layout ----------------------------
with st.expander("Create deliverables (infinite)", expanded=False):
    create_deliverables_section()

st.subheader("Deliverables")

items  = st.session_state["deliverables"]
terms  = sorted({(d.get("term") or "").strip()  for d in items if d.get("term")})
owners = sorted({(d.get("owner") or "").strip() for d in items if d.get("owner")})

fc1, fc2, fc3, fc4 = st.columns([1,1,2,1])
with fc1: f_term  = st.selectbox("Term",  [""] + terms,  index=0)
with fc2: f_owner = st.selectbox("Owner", [""] + owners, index=0)
with fc3: f_query = st.text_input("Search", help="title / unit / notes")
with fc4: per_page = st.selectbox("Per page", [5,10,20,50], index=1)

filtered = filter_deliverables(items, f_term, f_owner, f_query)

dl1, dl2, _ = st.columns([1,1,6])
with dl1:
    st.download_button("Download filtered — CSV",
                       data=export_filtered_csv(filtered),
                       file_name="deliverables_filtered_summary.csv",
                       mime="text/csv")
with dl2:
    st.download_button("Download filtered — Excel",
                       data=export_filtered_excel(filtered),
                       file_name="deliverables_filtered.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if "page" not in st.session_state: st.session_state["page"] = 1
pages = max(1, (len(filtered) - 1) // per_page + 1)
st.session_state["page"] = min(st.session_state["page"], pages)

pc1, pc2, pc3 = st.columns([1,1,6])
with pc1:
    if st.button("Prev", disabled=st.session_state["page"] <= 1):
        st.session_state["page"] -= 1; _rerun()
with pc2:
    if st.button("Next", disabled=st.session_state["page"] >= pages):
        st.session_state["page"] += 1; _rerun()
with pc3:
    st.caption(f"Page {st.session_state['page']} / {pages} • {len(filtered)} match(es)")

page_items, _ = paginate(filtered, st.session_state["page"], per_page)

# Launch edit modal when requested
if st.session_state.get("edit_id"):
    ed = next((d for d in items if d["id"] == st.session_state["edit_id"]), None)
    if ed:
        edit_deliverable_modal(ed)
        st.session_state["edit_id"] = None

# Delete confirm (per visible page)
for d in page_items:
    if confirm_modal(f"Delete deliverable '{d['title']}'? This cannot be undone.",
                     "ask_delete_one", match_id=d["id"]):
        delete_deliverable(d["id"]); st.success("Deleted."); _rerun()

if not page_items:
    st.info("No deliverables match the current filters.")
else:
    for d in page_items:
        show_deliverable_card(d)
