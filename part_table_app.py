# multi_rack_fg_stock_gsheets.py
import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib
import math
from streamlit_gsheets import GSheetsConnection

# ----------------------------
# App config
# ----------------------------
st.set_page_config(page_title="Multi-Rack FG Stock Board", layout="wide")

# ----------------------------
# Authenticator
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
PACKAGING_WEIGHT = 25.0
CELL_CAPACITY = 25
RACK_SPACES = {"A": 9, "B": 15, "C": 12, "D": 6, "E": 24, "F": 57}
FIXED_ROWS = 3

# ----------------------------
# Google Sheets Connection
# ----------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

# Helpers for syncing
def load_part_master():
    df = conn.read(worksheet="part_master", ttl=5)
    if df is None or df.empty:
        return {}
    return {row["Part No"]: {
                "Weight": row["Weight"],
                "Customer": row["Customer"],
                "Tube Length": row["Tube Length (mm)"]}
            for _, row in df.iterrows()}

def save_part_master(part_master):
    df = pd.DataFrame.from_dict(part_master, orient="index").reset_index()
    df = df.rename(columns={"index":"Part No"})
    conn.update(worksheet="part_master", data=df)

def load_history():
    df = conn.read(worksheet="history", ttl=5)
    return [] if df is None or df.empty else df.to_dict("records")

def save_history(history):
    df = pd.DataFrame(history)
    conn.update(worksheet="history", data=df)

def load_racks():
    df = conn.read(worksheet="racks", ttl=5)
    racks = {}
    for r, spaces in RACK_SPACES.items():
        cols = math.ceil(spaces / FIXED_ROWS)
        grid = [[{"Part No": None, "Quantity": 0} for _ in range(cols)] for _ in range(FIXED_ROWS)]
        racks[r] = {"rows": FIXED_ROWS, "cols": cols, "array": grid, "spaces": spaces}

    if df is not None and not df.empty:
        for _, row in df.iterrows():
            r = row["Rack"]; i = int(row["Row"])-1; j = int(row["Col"])-1
            if r in racks:
                racks[r]["array"][i][j] = {"Part No": row["Part No"], "Quantity": int(row["Quantity"])}
    return racks

def save_racks(racks):
    rows = []
    for rn, rack in racks.items():
        for i in range(rack["rows"]):
            for j in range(rack["cols"]):
                c = rack["array"][i][j]
                rows.append({"Rack": rn, "Row": i+1, "Col": j+1,
                             "Part No": c["Part No"], "Quantity": c["Quantity"]})
    conn.update(worksheet="racks", data=pd.DataFrame(rows))

# ----------------------------
# State Initialization
# ----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = None

if "part_master" not in st.session_state:
    st.session_state.part_master = load_part_master()

if "racks" not in st.session_state:
    st.session_state.racks = load_racks()

if "history" not in st.session_state:
    st.session_state.history = load_history()

# ----------------------------
# Utils
# ----------------------------
def ts_now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def add_history(action, rack, row_ui, col_ui, part_no, qty, user):
    st.session_state.history.insert(0, {
        "Timestamp": ts_now(),
        "User": user,
        "Action": action,
        "Rack": rack,
        "Row": row_ui,
        "Col": col_ui,
        "Part No": part_no,
        "Quantity": qty
    })
    save_history(st.session_state.history)

# ----------------------------
# Auth UI
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
    st.info("Welcome! Please login to continue.")
    st.stop()

# ----------------------------
# Role flags
# ----------------------------
role = st.session_state.role
can_master = role == "master"
can_input = role in ("master", "input")
can_output = role in ("master", "input", "output")

# ----------------------------
# Main Layout
# ----------------------------
st.title("Multi-Rack FG Stock Board")

tabs = []
if can_master: tabs.append("Master")
if can_input: tabs.append("Input")
if can_output: tabs.append("Output")
tab_objs = st.tabs(tabs)

# Master Tab
if can_master:
    with tab_objs[tabs.index("Master")]:
        st.subheader("Part Master")
        with st.form("part_form"):
            pn = st.text_input("Part No")
            wt = st.number_input("Weight (kg)", 0.0, step=0.01)
            cust = st.text_input("Customer")
            tube = st.number_input("Tube Length (mm)", 0, step=1)
            if st.form_submit_button("Add/Update"):
                if pn:
                    st.session_state.part_master[pn] = {"Weight": wt, "Customer": cust, "Tube Length": tube}
                    save_part_master(st.session_state.part_master)
                    add_history("Master Update", "-", "-", "-", pn, 0, st.session_state.user)
                    st.success(f"Updated master for {pn}")
        st.dataframe(pd.DataFrame.from_dict(st.session_state.part_master, orient="index").reset_index().rename(columns={"index":"Part No"}))

# Input Tab
if can_input:
    with tab_objs[tabs.index("Input")]:
        st.subheader("Stock Input")
        rack_ui = st.selectbox("Rack", options=list(st.session_state.racks.keys()))
        rack_data = st.session_state.racks[rack_ui]

        with st.form("stock_form", clear_on_submit=True):
            row_ui = st.number_input("Row (bottom=1)", 1, rack_data["rows"])
            col_ui = st.number_input("Column", 1, rack_data["cols"])
            part_no = st.selectbox("Part No", options=sorted(st.session_state.part_master.keys()))
            qty = st.number_input("Quantity", 1, step=1)
            action = st.radio("Action", ["Add", "Subtract"], horizontal=True)
            if st.form_submit_button("Apply"):
                cell = rack_data["array"][row_ui-1][col_ui-1]
                if action == "Add":
                    if cell["Part No"] in (None, part_no):
                        if cell["Quantity"] + qty <= CELL_CAPACITY:
                            cell["Part No"] = part_no
                            cell["Quantity"] += qty
                            add_history("Add", rack_ui, row_ui, col_ui, part_no, qty, st.session_state.user)
                            save_racks(st.session_state.racks)
                            st.success(f"Added {qty} {part_no} in {rack_ui} R{row_ui}C{col_ui}")
                        else:
                            st.error("Exceeds capacity")
                    else:
                        st.error("Cell holds different part")
                else:
                    if cell["Part No"] == part_no and cell["Quantity"] >= qty:
                        cell["Quantity"] -= qty
                        if cell["Quantity"] == 0: cell["Part No"] = None
                        add_history("Subtract", rack_ui, row_ui, col_ui, part_no, qty, st.session_state.user)
                        save_racks(st.session_state.racks)
                        st.success(f"Subtracted {qty} from {rack_ui} R{row_ui}C{col_ui}")
                    else:
                        st.error("Mismatch or insufficient stock")

# Output Tab
if can_output:
    with tab_objs[tabs.index("Output")]:
        st.subheader("Rack Overview")
        rack_sel = st.selectbox("Select Rack", options=list(st.session_state.racks.keys()))
        rows = []
        for i in range(st.session_state.racks[rack_sel]["rows"]):
            for j in range(st.session_state.racks[rack_sel]["cols"]):
                c = st.session_state.racks[rack_sel]["array"][i][j]
                rows.append({"Rack": rack_sel, "Row": i+1, "Col": j+1,
                             "Part No": c["Part No"], "Quantity": c["Quantity"]})
        st.dataframe(pd.DataFrame(rows))

        st.subheader("FIFO Finder")
        search_part = st.text_input("Part No to Pick (FIFO)")
        if st.button("Find FIFO"):
            fifo = None
            for ev in reversed(st.session_state.history):
                if ev["Action"]=="Add" and ev["Part No"]==search_part:
                    r,row_ui,col_ui = ev["Rack"], ev["Row"], ev["Col"]
                    cell = st.session_state.racks[r]["array"][row_ui-1][col_ui-1]
                    if cell["Part No"]==search_part and cell["Quantity"]>0:
                        fifo = ev; break
            if fifo:
                st.success(f"Pick from Rack {fifo['Rack']} R{fifo['Row']} C{fifo['Col']} (Qty {cell['Quantity']})")
            else:
                st.warning("No available FIFO stock")

        st.subheader("History")
        st.dataframe(pd.DataFrame(st.session_state.history))
