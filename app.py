import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- 1. CONFIGURATION & SUPABASE SETUP ---
st.set_page_config(page_title="Franklinville Field Log", page_icon="☁️", layout="centered")

@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# --- 2. AUTHENTICATION (Sidebar) ---
if "user" not in st.session_state:
    with st.sidebar:
        st.header("Welcome")
        auth_mode = st.radio("Access", ["Login", "Sign Up"], horizontal=True)
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        if auth_mode == "Login":
            if st.button("Sign In"):
                try:
                    auth_res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state["user"] = auth_res.user
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")
        
        else: # Sign Up Mode
            if st.button("Create Account"):
                try:
                    # This creates the account in your Supabase Auth table
                    supabase.auth.sign_up({"email": email, "password": password})
                    st.success("Account created! Please check your email if verification is enabled.")
                except Exception as e:
                    st.error(f"Sign up failed: {e}")

else: # Already logged in
    with st.sidebar:
        st.success(f"Logged in: {st.session_state['user'].email}")
        if st.button("Log Out"):
            supabase.auth.sign_out()
            del st.session_state["user"]
            st.rerun()
# --- 3. DATA FUNCTIONS ---
@st.cache_data(ttl=60)
def load_library():
    # Fetch seeds (Public access)
    response = supabase.table("seeds").select("*").execute()
    df = pd.DataFrame(response.data)
    
    expected_cols = ['genus', 'species', 'botanical_subspecies', 'common_name', 'variety']
    for col in expected_cols:
        if col not in df.columns:
            df[col] = "" 
            
    df = df.sort_values(by=expected_cols, ascending=True, na_position='first')
    df['display_name'] = df['common_name'] + " - " + df['variety'] + " (" + df['genus'] + " " + df['species'] + ")"
    return df

def save_log(seed_id, action, notes):
    # Get the user ID from the active session
    user = st.session_state.get("user")
    user_id = user.id if user else None
    
    data = {
        "seed_id": seed_id,
        "action": action,
        "notes": notes,
        "user_id": user_id
    }
    # Supabase uses RLS to enforce that only this user_id can insert
    supabase.table("field_logs").insert(data).execute()

df = load_library()

# --- 4. APP UI ---
st.title("☁️ Cloud Field App")
tab1, tab2 = st.tabs(["🗂️ Library", "📝 Field Log"])

with tab1:
    st.write(f"Active Collection: **{len(df)}** varieties")
    search_term = st.text_input("🔍 Quick Search...")

    if search_term:
        mask = df['common_name'].str.contains(search_term, case=False, na=False) | \
               df['variety'].str.contains(search_term, case=False, na=False)
        filtered_df = df[mask]
    else:
        filtered_df = df

    for index, row in filtered_df.iterrows():
        with st.expander(f"🌿 {row['common_name']} - {row['variety']}"):
            st.caption(f"Botanical: *{row['genus']} {row['species']}*")
            st.info(row.get('sowing_instructions', 'No instructions logged.'))

with tab2:
    if "user" not in st.session_state:
        st.warning("Please log in via the sidebar to record logs.")
    else:
        st.write("### 📝 Record an Action")
        plant_dict = dict(zip(df['display_name'], df['seed_id']))
        
        with st.form("log_form", clear_on_submit=True):
            selected_plant = st.selectbox("1. Which plant?", ["-- Choose --"] + list(plant_dict.keys()))
            action = st.selectbox("2. Action?", ["Started Indoors", "Direct Sowed", "Harvested", "General Observation"])
            notes = st.text_area("3. Notes")
            submitted = st.form_submit_button("☁️ Save to Cloud")
            
            if submitted:
                if selected_plant == "-- Choose --":
                    st.error("Select a plant!")
                else:
                    save_log(plant_dict[selected_plant], action, notes)
                    st.success("Logged successfully!")
