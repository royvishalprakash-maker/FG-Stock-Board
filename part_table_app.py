import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ========================
# Google Sheets Connection
# ========================
SHEET_NAME = "YOUR_SHEET_NAME"   # <-- change this
WORKSHEET_NAME = "part_master"   # <-- change this

# Define the scopes
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# Authenticate using Streamlit secrets
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=scope
)
client = gspread.authorize(creds)

# Open sheet and worksheet
sheet = client.open(SHEET_NAME)
worksheet = sheet.worksheet(WORKSHEET_NAME)


# ========================
# Helper Functions
# ========================
def load_data():
    """Load all data from Google Sheet into a DataFrame"""
    records = worksheet.get_all_records()
    return pd.DataFrame(records)


def save_data(df):
    """Save DataFrame back to Google Sheet"""
    worksheet.clear()
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())


# ========================
# Streamlit UI
# ========================
st.set_page_config(page_title="FG Stock Board", layout="wide")
st.title("📦 FG Stock Board")

# Load sheet data
df = load_data()

st.subheader("Part Master Table")
st.dataframe(df, use_container_width=True)

# Form to add a new part
st.subheader("➕ Add New Part")
with st.form("add_part_form"):
    part_number = st.text_input("Part Number")
    description = st.text_input("Description")
    quantity = st.number_input("Quantity", min_value=0, step=1)

    submitted = st.form_submit_button("Add Part")
    if submitted:
        new_row = {"Part Number": part_number, "Description": description, "Quantity": quantity}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df)
        st.success(f"✅ Part {part_number} added successfully!")
        st.rerun()

# Option to delete a part
st.subheader("🗑️ Delete Part")
part_to_delete = st.selectbox("Select Part to Delete", df["Part Number"] if not df.empty else [])
if st.button("Delete Selected Part") and part_to_delete:
    df = df[df["Part Number"] != part_to_delete]
    save_data(df)
    st.success(f"🗑️ Part {part_to_delete} deleted successfully!")
    st.rerun()
