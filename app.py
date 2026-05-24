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
        else:
            if st.button("Create Account"):
                try:
                    supabase.auth.sign_up({"email": email, "password": password})
                    st.success("Account created! Please check your email.")
                except Exception as e:
                    st.error(f"Sign up failed: {e}")
else:
    with st.sidebar:
        st.success(f"Logged in: {st.session_state['user'].email}")
        if st.button("Log Out"):
            supabase.auth.sign_out()
            del st.session_state["user"]
            st.rerun()

# --- 3. DATA FUNCTIONS ---
@st.cache_data(ttl=60)
def load_library():
    response = supabase.table("seeds").select("*").execute()
    df = pd.DataFrame(response.data)
    expected_cols = ['genus', 'species', 'botanical_subspecies', 'common_name', 'variety']
    for col in expected_cols:
        if col not in df.columns: df[col] = "" 
    df = df.sort_values(by=expected_cols, ascending=True, na_position='first')
    df['display_name'] = df['common_name'] + " - " + df['variety'] + " (" + df['genus'] + " " + df['species'] + ")"
    return df

def save_log(seed_id, action, notes):
    user = st.session_state.get("user")
    data = {"seed_id": seed_id, "action": action, "notes": notes, "user_id": user.id if user else None}
    supabase.table("field_logs").insert(data).execute()

df = load_library()

# --- 4. APP UI ---
st.title("☁️ Cloud Field App")
tab1, tab2 = st.tabs(["🗂️ Library", "📝 Field Log"])

with tab1:
    st.write(f"Active Collection: **{len(df)}** varieties")
    search_term = st.text_input("🔍 Quick Search Library...")
    filtered_df = df[df['common_name'].str.contains(search_term, case=False, na=False) | df['variety'].str.contains(search_term, case=False, na=False)] if search_term else df
    for index, row in filtered_df.iterrows():
        with st.expander(f"🌿 {row['common_name']} - {row['variety']}"):
            st.caption(f"Botanical: *{row['genus']} {row['species']}*")
            st.info(row.get('sowing_instructions', 'No instructions logged.'))

with tab2:
    if "user" not in st.session_state:
        st.warning("Please log in to record or view your logs.")
    else:
        st.write("### 📝 Record an Action")
        
        # Cascading Filter Logic
        all_genera = sorted(df['genus'].unique().tolist())
        selected_genus = st.selectbox("1. Genus:", ["-- All --"] + all_genera)
        
        genus_df = df if selected_genus == "-- All --" else df[df['genus'] == selected_genus]
        all_species = sorted(genus_df['species'].unique().tolist())
        selected_species = st.selectbox("2. Species:", ["-- All --"] + all_species)
            
        final_df = genus_df if selected_species == "-- All --" else genus_df[genus_df['species'] == selected_species]
        plant_dict = dict(zip(final_df['display_name'], final_df['seed_id']))
        
        with st.form("log_form", clear_on_submit=True):
            selected_plant = st.selectbox("3. Select Variety:", ["-- Choose --"] + list(plant_dict.keys()))
            action = st.selectbox("4. Action?", ["Started Indoors", "Direct Sowed", "Harvested", "General Observation"])
            notes = st.text_area("5. Notes")
            
            if st.form_submit_button("☁️ Save to Cloud"):
                if selected_plant == "-- Choose --": 
                    st.error("Select a plant!")
                else:
                    save_log(plant_dict[selected_plant], action, notes)
                    st.success("Logged successfully!")
                    st.rerun()

        st.divider()
        st.write("### 📜 My Recent Logs")
        response = supabase.table("field_logs").select("*").order("timestamp", desc=True).execute()
        
        variety_lookup = dict(zip(df['seed_id'], df['variety']))
        
        for log in response.data:
            current_id = log.get('log_id')
            seed_id = log.get('seed_id')
            variety_name = variety_lookup.
