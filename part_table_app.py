# multi_rack_fg_gspread.py
import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib
import math
import io

# Attempt gspread imports; we handle if unavailable at runtime
try:
    import gspread
    from google.oauth2.service_account import Credentials
    from gspread_dataframe import set_with_dataframe, get_as_dataframe
    GSPREAD_AVAILABLE = True
except Exception:
    GSPREAD_AVAILABLE = False

# ----------------------------
# Page config
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

def login_ok(username: str, password: str):
    u = USERS.get(username)
    if not u:
        return False, None
    return (u["pw_hash"] == hash_pw(password)), u["role"]

# ----------------------------
# Constants & Racks config
# ----------------------------
PACKAGING_WEIGHT = 25.0
CELL_CAPACITY = 25
RACK_SPACES = {"A": 9, "B": 15, "C": 12, "D": 6, "E": 24, "F": 57}
FIXED_ROWS = 3

# ----------------------------
# Google Sheets helpers (gspread)
# ----------------------------
def gspread_client_from_secrets():
    """
    Expects:
      st.secrets["gcp_service_account"] -> dict (service account JSON)
      st.secrets["spreadsheet_url"] -> string
    Returns (gc, sh) or (None, None) on failure.
    """
    if not GSPREAD_AVAILABLE:
        st.warning("gspread libraries not installed. Install via requirements.txt (gspread, google-auth, gspread-dataframe).")
        return None, None

    if "gcp_service_account" not in st.secrets or "spreadsheet_url" not in st.secrets:
        return None, None

    try:
        sa_info = st.secrets["gcp_service_account"]
        # create credentials
        creds = Credentials.from_service_account_info(sa_info, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ])
        gc = gspread.authorize(creds)
        sh = gc.open_by_url(st.secrets["spreadsheet_url"])
        return gc, sh
    except Exception as e:
        st.error(f"Failed to create gspread client: {e}")
        return None, None

def read_sheet_to_df(sh, worksheet_name):
    try:
        ws = sh.worksheet(worksheet_name)
        df = get_as_dataframe(ws, evaluate_formulas=True, usecols=None).fillna("")
        # drop rows that are completely blank
        if df.shape[0] == 0:
            return pd.DataFrame()
        df = df.dropna(how="all")
        return df
    except Exception:
        return pd.DataFrame()

def write_df_to_sheet(sh, worksheet_name, df):
    """
    Create or clear worksheet and write df into it.
    """
    try:
        try:
            ws = sh.worksheet(worksheet_name)
            sh.del_worksheet(ws)
        except Exception:
            pass
        ws = sh.add_worksheet(title=worksheet_name, rows=max(100, len(df)+10), cols=max(10, len(df.columns)+2))
        set_with_dataframe(ws, df, include_index=False, include_column_header=True)
        return True
    except Exception as e:
        st.error(f"Failed to write worksheet '{worksheet_name}': {e}")
        return False

# ----------------------------
# Persistence abstraction (either Google Sheets or in-memory)
# ----------------------------
def init_default_data_structures():
    # default part master (dict)
    default_pm = {
        "10283026": {"Weight": 8.05, "Customer": "Mahindra Pune", "Tube Length": 1254},
        "10291078": {"Weight": 7.90, "Customer": "Mahindra Pune", "Tube Length": 1245},
        "10282069": {"Weight": 8.95, "Customer": "Mahindra Pune", "Tube Length": 1262},
    }
    # default racks layout
    racks = {}
    for r, spaces in RACK_SPACES.items():
        cols = math.ceil(spaces / FIXED_ROWS)
        grid = [[{"Part No": None, "Quantity": 0} for _ in range(cols)] for _ in range(FIXED_ROWS)]
        racks[r] = {"rows": FIXED_ROWS, "cols": cols, "array": grid, "spaces": spaces}
    return default_pm, racks, []

# load/save using gspread if possible
gc, sh = gspread_client_from_secrets()

def load_all_from_sheets():
    if not sh:
        return init_default_data_structures()
    # part_master sheet expected columns: Part No, Weight, Customer, Tube Length (mm)
    pm_df = read_sheet_to_df(sh, "part_master")
    part_master = {}
    if not pm_df.empty:
        for _, row in pm_df.iterrows():
            pn = str(row.get("Part No", "")).strip()
            if pn:
                part_master[pn] = {
                    "Weight": float(row.get("Weight", 0.0)) if row.get("Weight", "")!="" else 0.0,
                    "Customer": row.get("Customer", ""),
                    "Tube Length": int(row.get("Tube Length (mm)", 0)) if row.get("Tube Length (mm)", "")!="" else 0
                }
    # racks sheet expected columns: Rack, Row, Col, Part No, Quantity
    racks = {}
    for r, spaces in RACK_SPACES.items():
        cols = math.ceil(spaces / FIXED_ROWS)
        grid = [[{"Part No": None, "Quantity": 0} for _ in range(cols)] for _ in range(FIXED_ROWS)]
        racks[r] = {"rows": FIXED_ROWS, "cols": cols, "array": grid, "spaces": spaces}
    racks_df = read_sheet_to_df(sh, "racks")
    if not racks_df.empty:
        for _, row in racks_df.iterrows():
            r = str(row.get("Rack", "")).strip()
            if not r or r not in racks: 
                continue
            try:
                i = int(row.get("Row", 0)) - 1
                j = int(row.get("Col", 0)) - 1
                pn = row.get("Part No", None)
                qty = int(row.get("Quantity", 0)) if row.get("Quantity", "")!="" else 0
                if 0 <= i < racks[r]["rows"] and 0 <= j < racks[r]["cols"]:
                    racks[r]["array"][i][j] = {"Part No": pn if pn not in ("", "None", None) else None, "Quantity": qty}
            except Exception:
                continue
    # history sheet expected columns: Timestamp, User, Action, Rack, Row, Col, Part No, Quantity, Note (optional)
    hist_df = read_sheet_to_df(sh, "history")
    history = []
    if not hist_df.empty:
        for _, row in hist_df.iterrows():
            entry = {
                "Timestamp": row.get("Timestamp", ""),
                "User": row.get("User", ""),
                "Action": row.get("Action", ""),
                "Rack": row.get("Rack", ""),
                "Row": int(row.get("Row", 0)) if row.get("Row", "")!="" else 0,
                "Col": int(row.get("Col", 0)) if row.get("Col", "")!="" else 0,
                "Part No": row.get("Part No", ""),
                "Quantity": int(row.get("Quantity", 0)) if row.get("Quantity", "")!="" else 0,
                "Note": row.get("Note", "")
            }
            history.append(entry)
    return part_master, racks, history

def save_all_to_sheets(part_master, racks, history):
    if not sh:
        return False
    # save part_master
    pm_rows = []
    for pn, meta in part_master.items():
        pm_rows.append({
            "Part No": pn,
            "Weight": meta.get("Weight", 0.0),
            "Customer": meta.get("Customer", ""),
            "Tube Length (mm)": meta.get("Tube Length", "")
        })
    pm_df = pd.DataFrame(pm_rows)
    write_pm_ok = write_any_df_to_sheet("part_master", pm_df)

    # save racks
    racks_rows = []
    for rn, rack in racks.items():
        for i in range(rack["rows"]):
            for j in range(rack["cols"]):
                c = rack["array"][i][j]
                racks_rows.append({"Rack": rn, "Row": i+1, "Col": j+1, "Part No": c["Part No"], "Quantity": c["Quantity"]})
    racks_df = pd.DataFrame(racks_rows)
    write_racks_ok = write_any_df_to_sheet("racks", racks_df)

    # save history
    hist_df = pd.DataFrame(history)
    write_hist_ok = write_any_df_to_sheet("history", hist_df)

    return write_pm_ok and write_racks_ok and write_hist_ok

def write_any_df_to_sheet(worksheet_name, df):
    try:
        return write_df_to_sheet(sh, worksheet_name, df)
    except Exception as e:
        st.warning(f"Could not write '{worksheet_name}' to sheet: {e}")
        return False

# ----------------------------
# Load persisted (or defaults)
# ----------------------------
if "initialized" not in st.session_state:
    if sh:
        pm, racks, hist = load_all_from_sheets()
    else:
        pm, racks, hist = init_default_data_structures()
    st.session_state.part_master = pm
    st.session_state.racks = racks
    st.session_state.history = hist
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.initialized = True

# ----------------------------
# Utility functions
# ----------------------------
def ts_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def cell_total_weight(cell):
    pn, qty = cell["Part No"], cell["Quantity"]
    if qty > 0 and pn:
        pm = st.session_state.part_master.get(pn, {})
        return qty * pm.get("Weight", 0.0) + PACKAGING_WEIGHT
    return 0.0

def total_qty_all():
    return sum(c["Quantity"] for r in st.session_state.racks.values() for row in r["array"] for c in row)

def add_history(action, rack, row_ui, col_ui, part_no, qty, user, note=""):
    entry = {
        "Timestamp": ts_now(),
        "User": user,
        "Action": action,
        "Rack": rack,
        "Row": row_ui,
        "Col": col_ui,
        "Part No": part_no,
        "Quantity": qty,
        "Note": note
    }
    st.session_state.history.insert(0, entry)
    # try persist
    if sh:
        _ = write_any_df_to_sheet("history", pd.DataFrame(st.session_state.history))

def save_racks_and_pm():
    # persist both part_master and racks and history
    if sh:
        save_all_to_sheets(st.session_state.part_master, st.session_state.racks, st.session_state.history)

# ----------------------------
# Authentication UI (sidebar)
# ----------------------------
with st.sidebar:
    st.title("Access")
    if not st.session_state.get("logged_in"):
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                ok, role = login_ok(username.strip(), password)
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

if not st.session_state.get("logged_in"):
    st.title("Multi-Rack FG Stock Board")
    st.info("Welcome! Please login to continue.")
    st.stop()

# ----------------------------
# Permissions
# ----------------------------
role = st.session_state.role
can_master = role == "master"
can_input = role in ("master", "input")
can_output = role in ("master", "input", "output")

# ----------------------------
# UI Layout
# ----------------------------
st.title("Multi-Rack FG Stock Board")
col1, col2 = st.columns([3,1])
with col1:
    st.m

