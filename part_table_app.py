# multi_rack_fg_stock.py
import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib
import io
import math

# ----------------------------
# App config
# ----------------------------
st.set_page_config(page_title="Multi-Rack FG Stock Board", layout="wide")

# ----------------------------
# Demo authenticator (IN-APP demo only)
# ----------------------------
USERS = {
    "Vishal": {"pw_hash": hashlib.sha256(b"master123").hexdigest(), "role": "master"},
    "Kittu": {"pw_hash": hashlib.sha256(b"input123").hexdigest(), "role": "input"},
    "1306764": {"pw_hash": hashlib.sha256(b"output123").hexdigest(), "role": "output"},
}

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def login(username: str, password: str):
    u = USERS.get(username)
    if not u:
        return False, None
    return (u["pw_hash"] == hash_pw(password)), u["role"]

# ----------------------------
# Constants
# ----------------------------
PACKAGING_WEIGHT = 25.0  # kg per non-empty cell
CELL_CAPACITY = 25       # pieces per cell
RACK_SPACES = {"A": 9, "B": 15, "C": 12, "D": 6, "E": 24, "F": 57}
FIXED_ROWS = 3

# ----------------------------
# Init session state
# ----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = None

if "part_master" not in st.session_state:
    st.session_state.part_master = {
        "10283026": {"Weight": 8.05, "Customer": "Mahindra Pune", "Tube Length": 1254},
        "10291078": {"Weight": 7.90, "Customer": "Mahindra Pune", "Tube Length": 1245},
        "10282069": {"Weight": 8.95, "Customer": "Mahindra Pune", "Tube Length": 1262},
    }

if "racks" not in st.session_state:
    racks = {}
    for r, spaces in RACK_SPACES.items():
        cols = math.ceil(spaces / FIXED_ROWS)
        grid = [[{"Part No": None, "Quantity": 0} for _ in range(cols)] for _ in range(FIXED_ROWS)]
        racks[r] = {"rows": FIXED_ROWS, "cols": cols, "array": grid, "spaces": spaces}
    st.session_state.racks = racks

if "history" not in st.session_state:
    st.session_state.history = []

# ----------------------------
# Utilities
# ----------------------------
def ts_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def cell_total_weight(cell):
    pn, qty = cell["Part No"], cell["Quantity"]
    if qty > 0 and pn:
        pm = st.session_state.part_master.get(pn, {})
        return qty * pm.get("Weight", 0.0) + PACKAGING_WEIGHT
    return 0.0

def total_weight_all():
    return sum(
        cell_total_weight(c)
        for rack in st.session_state.racks.values()
        for row in rack["array"]
        for c in row
    )

def add_history(action, rack, row_ui, col_ui, part_no, qty, user, note=""):
    st.session_state.history.insert(
        0,
        {
            "Timestamp": ts_now(),
            "User": user,
            "Action": action,
            "Rack": rack,
            "Row": row_ui,
            "Col": col_ui,
            "Part No": part_no,
            "Quantity": qty,
            "Note": note,
        },
    )

def prepare_rack_grid_csv():
    rows = []
    for rn, rack in st.session_state.racks.items():
        for i in range(rack["rows"]):
            for j in range(rack["cols"]):
                c = rack["array"][i][j]
                pm = st.session_state.part_master.get(c["Part No"], {}) if c["Part No"] else {}
                rows.append(
                    {
                        "Rack": rn,
                        "Row": i + 1,
                        "Col": j + 1,
                        "Part No": c["Part No"],
                        "Customer": pm.get("Customer", ""),
                        "Tube Length (mm)": pm.get("Tube Length", ""),
                        "Quantity": c["Quantity"],
                        "Total Weight (kg)": round(cell_total_weight(c), 2),
                    }
                )
    return pd.DataFrame(rows)

def prepare_part_master_csv_bytes():
    df = pd.DataFrame.from_dict(st.session_state.part_master, orient="index").reset_index()
    df = df.rename(columns={"index": "Part No"})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

def prepare_history_csv_bytes():
    if not st.session_state.history:
        return "".encode("utf-8")
    df = pd.DataFrame(st.session_state.history)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

# ----------------------------
# Authentication UI
# ----------------------------
with st.sidebar:
    st.title("Access")
    if not st.session_state.logged_in:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                ok, role = login(username.strip(), password)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.user = username.strip()
                    st.session_state.role = role
                    st.rerun()
                else:
                    st.error("Invalid credentials")
    else:
        st.markdown(f"**User:** {st.session_state.user}")
        st.markdown(f"**Role:** {st.session_state.role}")
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.session_state.role = None
            st.rerun()

if not st.session_state.logged_in:
    st.title("Multi-Rack FG Stock Board")
    st.info("Welcome to the FG Stock Dashboard")
    st.stop()

# ----------------------------
# Role flags
# ----------------------------
role = st.session_state.role
can_master = role == "master"
can_input = role in ("master", "input")
can_output = role in ("master", "input", "output")

# ----------------------------
# Header
# ----------------------------
col1, col2 = st.columns([3, 1])
with col1:
    st.title("Multi-Rack FG Stock Board")
    st.caption(f"Signed in as {st.session_state.user} ({role})")
with col2:
    
    total_qty = sum(c["Quantity"] for r in st.session_state.racks.values() for row in r["array"] for c in row)
    st.metric("Total Qty", f"{total_qty}")

# ----------------------------
# Tabs
# ----------------------------
tabs = []
if can_master: tabs.append("Master")
if can_input: tabs.append("Input")
if can_output: tabs.append("Output")
tab_objs = st.tabs(tabs)

# MASTER Tab
if can_master:
    with tab_objs[tabs.index("Master")]:
        st.subheader("Part Master")
        with st.form("part_master_form"):
            pn = st.text_input("Part No").strip()
            wt = st.number_input("Weight (kg)", min_value=0.0, step=0.01, format="%.2f")
            cust = st.text_input("Customer")
            tube = st.number_input("Tube Length (mm)", min_value=0, step=1)
            if st.form_submit_button("Add / Update Part"):
                if pn:
                    st.session_state.part_master[pn] = {"Weight": wt, "Customer": cust, "Tube Length": int(tube)}
                    add_history("Master Update", "-", "-", "-", pn, 0, st.session_state.user)
                    st.success(f"Updated master for {pn}")
        st.dataframe(pd.DataFrame.from_dict(st.session_state.part_master, orient="index").reset_index().rename(columns={"index":"Part No"}))
        st.download_button("⬇️ Download Part Master CSV", data=prepare_part_master_csv_bytes(), file_name="part_master.csv", mime="text/csv")

# INPUT Tab
if can_input:
    with tab_objs[tabs.index("Input")]:
        st.subheader("Stock Input")
        rack_ui = st.selectbox("Rack", options=list(st.session_state.racks.keys()))
        rack_data = st.session_state.racks[rack_ui]
        ROWS, COLS = rack_data["rows"], rack_data["cols"]

        with st.form("stock_form", clear_on_submit=True):
            row_ui = st.number_input("Row (bottom=1)", min_value=1, max_value=ROWS, value=1, step=1)
            col_ui = st.number_input("Column", min_value=1, max_value=COLS, value=1, step=1)
            part_no = st.selectbox("Part No", options=sorted(st.session_state.part_master.keys()))
            qty = st.number_input("Quantity", min_value=1, step=1)
            action = st.radio("Action", ["Add", "Subtract"], horizontal=True)
            if st.form_submit_button("Apply"):
                cell = rack_data["array"][row_ui - 1][col_ui - 1]
                if action == "Add":
                    if cell["Part No"] in (None, part_no):
                        if cell["Quantity"] + qty <= CELL_CAPACITY:
                            cell["Part No"] = part_no
                            cell["Quantity"] += qty
                            add_history("Add", rack_ui, row_ui, col_ui, part_no, qty, st.session_state.user)
                            st.success(f"Added {qty} of {part_no} at {rack_ui} R{row_ui} C{col_ui}")
                        else:
                            st.error("Exceeds cell capacity")
                    else:
                        st.error("Cell already has a different part")
                else:  # Subtract
                    if cell["Part No"] == part_no and cell["Quantity"] >= qty:
                        cell["Quantity"] -= qty
                        if cell["Quantity"] == 0: cell["Part No"] = None
                        add_history("Subtract", rack_ui, row_ui, col_ui, part_no, qty, st.session_state.user)
                        st.success(f"Subtracted {qty} from {rack_ui} R{row_ui} C{col_ui}")
                    else:
                        st.error("Mismatch or insufficient stock")

        st.download_button("⬇️ Download Grid CSV", data=prepare_rack_grid_csv().to_csv(index=False).encode("utf-8"), file_name="grid.csv", mime="text/csv")

# OUTPUT Tab
if can_output:
    with tab_objs[tabs.index("Output")]:
        st.subheader("Rack Overview")
        out_rack = st.selectbox("Select Rack to View", options=list(st.session_state.racks.keys()))
        st.dataframe(prepare_rack_grid_csv().query("Rack == @out_rack"))

        st.subheader("FIFO Part Finder")
        search_part = st.text_input("Part No")
        if st.button("Find FIFO Cell"):
            fifo = None
            for ev in reversed(st.session_state.history):
                if ev["Action"]=="Add" and ev["Part No"]==search_part:
                    rk,row_ui,col_ui = ev["Rack"], ev["Row"], ev["Col"]
                    cell = st.session_state.racks[rk]["array"][row_ui-1][col_ui-1]
                    if cell["Part No"]==search_part and cell["Quantity"]>0:
                        fifo = ev
                        break
            if fifo:
                st.success(f"FIFO pick: Rack {fifo['Rack']} R{fifo['Row']} C{fifo['Col']} (Qty: {cell['Quantity']})")
            else:
                st.warning("No FIFO candidate found")

        st.subheader("History Log")
        if st.session_state.history:
            st.dataframe(pd.DataFrame(st.session_state.history))
            st.download_button("⬇️ Download History CSV", data=prepare_history_csv_bytes(), file_name="history.csv", mime="text/csv")
        else:
            st.info("No history yet")
