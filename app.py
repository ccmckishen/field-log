import streamlit as st
import psycopg2
import pandas as pd

# --- CLOUD DATABASE CONNECTION ---
# ⚠️ PASTE YOUR SUPABASE URI STRING HERE (Keep the quotation marks!) ⚠️
# Pull the secure connection string from Streamlit's secret vault
import streamlit as st
from supabase import create_client, Client

# Initialize the new Supabase Client
@st.cache_resource
def get_supabase_client():
    # We are now using the URL and KEY, not the URI
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = get_supabase_client()

# 1. Page Configuration
st.set_page_config(page_title="Franklinville Field Log", page_icon="☁️", layout="centered")

# 2. Database Connections (Now powered by Supabase!)
@st.cache_data(ttl=60) # Checks the cloud for updates every 60 seconds
def load_library():
    try:
        conn = psycopg2.connect(CONNECTION_STRING, connect_timeout=10, sslmode='require')
    except Exception as e:
        st.error(f"Connection Failed! Detailed Error: {e}")
        st.stop()
    # Pull the seeds from the cloud
    df = pd.read_sql_query("SELECT seed_id, common_name, variety, genus, species, botanical_subspecies, maturity_days, sowing_instructions, frost_tolerant, source_company FROM seeds", conn)
    conn.close()
    
    expected_cols = ['genus', 'species', 'botanical_subspecies', 'common_name', 'variety']
    for col in expected_cols:
        if col not in df.columns:
            df[col] = "" 
            
    df = df.sort_values(by=expected_cols, ascending=True, na_position='first')
    df['display_name'] = df['common_name'] + " - " + df['variety'] + " (" + df['genus'] + " " + df['species'] + ")"
    return df

def save_log(seed_id, action, notes):
    conn = psycopg2.connect(CONNECTION_STRING)
    cursor = conn.cursor()
    # Postgres uses %s instead of ? for variables!
    cursor.execute('''
        INSERT INTO field_logs (seed_id, action, notes, timestamp)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
    ''', (seed_id, action, notes))
    conn.commit()
    conn.close()

df = load_library()

# 3. Mobile UI Header & TABS
st.title("☁️ Cloud Field App")
tab1, tab2 = st.tabs(["🗂️ Library", "📝 Field Log"])

# ==========================================
# TAB 1: THE LIBRARY
# ==========================================
with tab1:
    st.write(f"Active Collection: **{len(df)}** varieties")
    search_term = st.text_input("🔍 Quick Search (Type a name or variety)...")

    if search_term:
        mask = df['common_name'].str.contains(search_term, case=False, na=False) | \
               df['variety'].str.contains(search_term, case=False, na=False) | \
               df['genus'].str.contains(search_term, case=False, na=False)
        filtered_df = df[mask]
        st.divider()
        st.write(f"Found {len(filtered_df)} matches:")
        
    else:
        st.divider()
        st.write("### 🗂️ Browse Database")
        browse_mode = st.radio("How would you like to browse?", ["By Common Name", "By Botanical Name"], horizontal=True)
        filtered_df = pd.DataFrame() 
        
        if browse_mode == "By Common Name":
            common_names = sorted([c for c in df['common_name'].unique() if pd.notna(c) and str(c).strip() != ""])
            selected_common = st.selectbox("Select a Plant Type:", ["-- Select Plant --"] + common_names)
            
            if selected_common != "-- Select Plant --":
                filtered_df = df[df['common_name'] == selected_common]
                st.write(f"Showing **{len(filtered_df)}** varieties of {selected_common}:")
                
        else:
            genera = sorted([g for g in df['genus'].unique() if pd.notna(g) and str(g).strip() != ""])
            selected_genus = st.selectbox("1. Botanical Genus:", ["-- Select Genus --"] + genera)
            
            if selected_genus != "-- Select Genus --":
                current_df = df[df['genus'] == selected_genus]
                species_list = sorted([s for s in current_df['species'].unique() if pd.notna(s) and str(s).strip() != ""])
                
                if species_list:
                    selected_species = st.selectbox("2. Species (Optional):", ["-- All Species --"] + species_list)
                    if selected_species != "-- All Species --":
                        current_df = current_df[current_df['species'] == selected_species]
                        subspecies_list = sorted([sub for sub in current_df['botanical_subspecies'].unique() if pd.notna(sub) and str(sub).strip() != ""])
                        
                        if subspecies_list:
                            selected_sub = st.selectbox("3. Subspecies (Optional):", ["-- All Subspecies --"] + subspecies_list)
                            if selected_sub != "-- All Subspecies --":
                                current_df = current_df[current_df['botanical_subspecies'] == selected_sub]
                
                filtered_df = current_df
                st.write(f"Showing **{len(filtered_df)}** varieties:")

    if not filtered_df.empty:
        for index, row in filtered_df.iterrows():
            c_name = row.get('common_name', 'Unknown')
            var_name = row.get('variety', 'Unknown')
            g, s, sub = row.get('genus', ''), row.get('species', ''), row.get('botanical_subspecies', '')
            full_botanical = f"{g} {s} {sub}".strip()
            
            with st.expander(f"🌿 {c_name} - {var_name}"):
                st.caption(f"Botanical: *{full_botanical}*")
                col1, col2 = st.columns(2)
                mat, frost = row.get('maturity_days', ''), row.get('frost_tolerant', '')
                col1.metric("Maturity", mat if pd.notna(mat) and mat != "" else "Unknown")
                col2.metric("Frost Tolerant?", frost if pd.notna(frost) and frost != "" else "Unknown")
                
                sowing = row.get('sowing_instructions', '')
                st.write("**Sowing Instructions:**")
                st.info(sowing if pd.notna(sowing) and sowing != "" else "None logged.")
                source = row.get('source_company', '')
                if pd.notna(source) and source != "":
                    st.caption(f"Source: {source}")


# ==========================================
# TAB 2: DATA ENTRY (The Field Log)
# ==========================================
with tab2:
    st.write("### 📝 Record an Action")
    st.write("Use this form to log planting, feeding, or harvesting directly to the cloud.")
    
    plant_dict = dict(zip(df['display_name'], df['seed_id']))
    
    with st.form("log_form", clear_on_submit=True):
        selected_plant_name = st.selectbox("1. Which plant?", ["-- Choose a Plant --"] + list(plant_dict.keys()))
        
        action_types = [
            "Started Indoors", 
            "Direct Sowed", 
            "Transplanted to Garden", 
            "Watered / Fertilized", 
            "Pest / Disease Spotted", 
            "Harvested", 
            "General Observation"
        ]
        selected_action = st.selectbox("2. What happened?", action_types)
        notes = st.text_area("3. Notes (Yield amount, weather, growth stage, etc.)")
        submitted = st.form_submit_button("☁️ Save to Cloud")
        
        if submitted:
            if selected_plant_name == "-- Choose a Plant --":
                st.error("⚠️ Please select a plant from the dropdown first!")
            else:
                target_seed_id = plant_dict[selected_plant_name]
                save_log(target_seed_id, selected_action, notes)
                st.success(f"✅ Successfully logged '{selected_action}' to the cloud for {selected_plant_name.split(' -')[0]}!")
                st.balloons() # A little celebration for your first cloud save!
