import streamlit as st
import pandas as pd
import datetime

# ----------------------------
# Demo Authenticator (not secure)
# ----------------------------
USERS = {
    "master": {"password": "master123", "role": "master"},
    "input": {"password": "input123", "role": "input"},
    "output": {"password": "output123", "role": "output"},
}

# ----------------------------
# Initialize Session State
# ----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None

if "part_master" not in st.session_state:
    st.session_state.part_master = pd.DataFrame(columns=["Part No", "Description"])

if "racks" not in st.session_state:
    rack_spaces = {"A": 9, "B": 15, "C": 12, "D": 6, "E": 24, "F": 57}
    racks = {}
    for rack, spaces in rack_spaces.items():
        rows = 3
        cols = spaces // rows
        racks[rack] = {
            "rows": rows,
            "cols": cols,
            "array": [[{'Part No': None, 'Quantity': 0} for _ in range(cols)] for _ in range(rows)]
        }
    st.session_state.racks = racks

if "history" not in st.session_state:
    st.session_state.history = []

# ----------------------------
# Authentication Logic
# ----------------------------
def login():
    st.title("Multi-Rack FG Stock Board")
    st.info("🔐 Welcome! Please log in with your username and password to continue.")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login", key="login_button"):
        if username in USERS and USERS[username]["password"] == password:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = USERS[username]["role"]
            st.success(f"Welcome, {username}!")
            st.rerun()
        else:
            st.error("Invalid username or password")

def logout():
    if st.sidebar.button("Logout", key="logout_button"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.role = None
        st.rerun()

# ----------------------------
# Part Master Management
# ----------------------------
def part_master_ui():
    st.subheader("📘 Part Master Management")

    uploaded = st.file_uploader("Upload Part Master CSV", type="csv", key="upload_pm")
    if uploaded:
        df = pd.read_csv(uploaded)
        if "Part No" in df.columns and "Description" in df.columns:
            st.session_state.part_master = df
            st.success("Part Master updated from CSV")
        else:
            st.error("CSV must have 'Part No' and 'Description' columns")

    with st.form("add_part_form"):
        part_no = st.text_input("Part No")
        desc = st.text_input("Description")
        if st.form_submit_button("Add / Update Part"):
            if part_no:
                df = st.session_state.part_master
                if part_no in df["Part No"].values:
                    st.session_state.part_master.loc[df["Part No"] == part_no, "Description"] = desc
                    st.info("Part updated")
                else:
                    st.session_state.part_master = pd.concat(
                        [df, pd.DataFrame([[part_no, desc]], columns=df.columns)],
                        ignore_index=True
                    )
                    st.success("Part added")

    st.dataframe(st.session_state.part_master, use_container_width=True)

    csv = st.session_state.part_master.to_csv(index=False).encode()
    st.download_button(
        "⬇️ Download Part Master CSV",
        data=csv,
        file_name="part_master.csv",
        mime="text/csv",
        key="dl_part_master"
    )

# ----------------------------
# Input Section
# ----------------------------
def input_ui():
    st.subheader("📥 Add Stock to Rack")

    if st.session_state.part_master.empty:
        st.warning("Upload or add parts to the Part Master first.")
        return

    rack = st.selectbox("Select Rack", options=list(st.session_state.racks.keys()), key="rack_select")
    rack_data = st.session_state.racks[rack]
    part_no = st.selectbox("Select Part", st.session_state.part_master["Part No"], key="part_select")
    qty = st.number_input("Quantity", min_value=1, step=1, key="qty_input")

    if st.button("Add Stock", key="add_stock_btn"):
        placed = False
        for r in range(rack_data["rows"] - 1, -1, -1):  # bottom to top
            for c in range(rack_data["cols"]):
                cell = rack_data["array"][r][c]
                if cell["Part No"] in (None, part_no) or cell["Quantity"] == 0:
                    if cell["Part No"] is None:
                        cell["Part No"] = part_no
                    cell["Quantity"] += qty
                    st.session_state.history.append(
                        f"{datetime.datetime.now()} | Rack {rack} | Row {r+1} | Col {c+1} | Part No: {part_no} | Qty: +{qty}"
                    )
                    st.success(f"Added {qty} of {part_no} to Rack {rack} Row {r+1}, Col {c+1}")
                    placed = True
                    break
            if placed:
                break
        if not placed:
            st.error("No space available in this rack!")

# ----------------------------
# Output Section
# ----------------------------
def output_ui():
    st.subheader("📤 Output / Search")

    search_part = st.text_input("Enter Part No to Search", key="search_part")
    if search_part:
        fifo_candidates = [log for log in st.session_state.history if f"Part No: {search_part}" in log]
        if fifo_candidates:
            oldest_log = fifo_candidates[0]  # first added = oldest
            st.success(f"FIFO Pick → {oldest_log}")
        else:
            st.warning("Part not found in history.")

    st.subheader("📜 History Log")
    st.write(st.session_state.history)

    history_csv = "\n".join(st.session_state.history).encode()
    st.download_button(
        "⬇️ Download History CSV",
        data=history_csv,
        file_name="history.csv",
        mime="text/csv",
        key="dl_history"
    )

# ----------------------------
# Main
# ----------------------------
if not st.session_state.logged_in:
    login()
else:
    st.sidebar.write(f"👤 User: {st.session_state.username} ({st.session_state.role})")
    logout()

    role = st.session_state.role
    if role == "master":
        part_master_ui()
        input_ui()
        output_ui()
    elif role == "input":
        input_ui()
        output_ui()
    elif role == "output":
        output_ui()
