import streamlit as st
import pandas as pd
from supabase import create_client
import datetime
import altair as alt
import requests

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Cloud Field App", page_icon="☁️", layout="wide")

@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# --- 2. AUTHENTICATION UI ---
def render_auth_ui():
    st.title("🔐 Login / Sign Up")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    
    col1, col2 = st.columns(2)
    if col1.button("Login"):
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state["user"] = res.user
            st.rerun()
        except Exception as e:
            st.error("Login failed. Check your credentials.")
            
    if col2.button("Sign Up"):
        try:
            supabase.auth.sign_up({"email": email, "password": password})
            st.success("Account created! Please log in.")
        except Exception as e:
            st.error(f"Signup failed: {e}")
    st.stop()

# --- 3. WEATHER HELPERS ---
LAT, LON = "41.109", "-74.585"
WMO_CODES = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain"}

def fetch_weather():
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,precipitation,weather_code,wind_speed_10m,wind_direction_10m&temperature_unit=fahrenheit&precipitation_unit=inch&wind_speed_unit=mph&timezone=America/New_York"
        res = requests.get(url).json().get('current', {})
        return {
            "temp": res.get('temperature_2m', 0.0),
            "rain": res.get('precipitation', 0.0),
            "conditions": WMO_CODES.get(res.get('weather_code', 0), "Clear"),
            "wind_speed": res.get('wind_speed_10m', 0.0),
            "wind_dir": res.get('wind_direction_10m', 0.0)
        }
    except Exception: return {"temp": 0.0, "rain": 0.0, "conditions": "Clear", "wind_speed": 0.0, "wind_dir": 0.0}

def fetch_weather_historical(date_str):
    try:
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={LAT}&longitude={LON}&start_date={date_str}&end_date={date_str}&daily=temperature_2m_mean,precipitation_sum,weather_code,wind_speed_10m_max,wind_direction_10m_dominant&temperature_unit=fahrenheit&precipitation_unit=inch&wind_speed_unit=mph&timezone=America/New_York"
        res = requests.get(url).json().get('daily', {})
        return {
            "temp": res.get('temperature_2m_mean', [0.0])[0],
            "rain": res.get('precipitation_sum', [0.0])[0],
            "conditions": WMO_CODES.get(res.get('weather_code', [0])[0], "Clear"),
            "wind_speed": res.get('wind_speed_10m_max', [0.0])[0],
            "wind_dir": res.get('wind_direction_10m_dominant', [0.0])[0]
        }
    except Exception: return {"temp": 0.0, "rain": 0.0, "conditions": "Clear", "wind_speed": 0.0, "wind_dir": 0.0}

# --- 4. DATA LOADING ---
@st.cache_data(ttl=3600)
def load_library():
    try:
        response = supabase.table("seeds").select("seed_id, genus, species, common_name, variety, sowing_instructions").execute()
        df = pd.DataFrame(response.data)
        df['display_name'] = df['common_name'] + " - " + df['variety'] + " (" + df['genus'] + " " + df['species'] + ")"
        return df
    except Exception: return pd.DataFrame()

# --- 5. MAIN APP FLOW ---
if "user" not in st.session_state:
    session = supabase.auth.get_session()
    if session: 
        st.session_state["user"] = session.user
    else:
        render_auth_ui()

# If we reached here, the user is logged in
df = load_library()
st.title("☁️ Cloud Field App")

if st.sidebar.button("Logout"):
    supabase.auth.sign_out()
    del st.session_state["user"]
    st.rerun()

tab1, tab2, tab3, tab4 = st.tabs(["🗂️ Library", "📝 Field Log", "📊 Insights", "🌤️ Weather History"])

with tab1:
    st.write("### 🗂️ Seed Library")
    if not df.empty:
        common = st.selectbox("Common Name:", ["-- All --"] + sorted(df['common_name'].unique().tolist()), key="lib_common")
        genus_df = df if common == "-- All --" else df[df['common_name'] == common]
        genus = st.selectbox("Genus:", ["-- All --"] + sorted(genus_df['genus'].unique().tolist()), key="lib_genus")
        spec_df = genus_df if genus == "-- All --" else genus_df[genus_df['genus'] == genus]
        species = st.selectbox("Species:", ["-- All --"] + sorted(spec_df['species'].unique().tolist()), key="lib_species")
        final_df = spec_df if species == "-- All --" else spec_df[spec_df['species'] == species]
        
        if common == "-- All --" and genus == "-- All --" and species == "-- All --":
            st.info("Select a category above to view your seeds.")
        else:
            for _, row in final_df.iterrows():
                with st.expander(f"🌿 {row['common_name']} - {row['variety']}"):
                    st.write(f"Botanical: *{row['genus']} {row['species']}*")
                    st.info(row.get('sowing_instructions', 'No instructions.'))

with tab2:
    if not df.empty:
        common = st.selectbox("1. Common Name:", ["-- All --"] + sorted(df['common_name'].unique().tolist()), key="log_common")
        genus_df = df if common == "-- All --" else df[df['common_name'] == common]
        genus = st.selectbox("2. Genus:", ["-- All --"] + sorted(genus_df['genus'].unique().tolist()), key="log_genus")
        spec_df = genus_df if genus == "-- All --" else genus_df[genus_df['genus'] == genus]
        species = st.selectbox("3. Species:", ["-- All --"] + sorted(spec_df['species'].unique().tolist()), key="log_species")
        final_df = spec_df if species == "-- All --" else spec_df[spec_df['species'] == species]
        
        with st.form("log_form", clear_on_submit=True):
            plant_options = dict(zip(final_df['display_name'], final_df['seed_id']))
            selected_plant = st.selectbox("4. Plant:", ["-- Choose --"] + list(plant_options.keys()))
            action = st.selectbox("5. Action?", ["Watering", "Direct Sowed", "Harvested", "General Observation", "Weather Event"])
            notes = st.text_area("6. Notes")
            if st.form_submit_button("☁️ Save to Cloud"):
                supabase.table("field_logs").insert({"seed_id": int(plant_options[selected_plant]), "action": action, "notes": notes, "user_id": str(st.session_state["user"].id)}).execute()
                st.success("Logged!")
                st.rerun()

with tab3:
    st.write("### 📈 Analytics")
    logs = supabase.table("field_logs").select("*").eq("user_id", st.session_state["user"].id).execute()
    if logs.data:
        st.altair_chart(alt.Chart(pd.DataFrame(logs.data)).mark_bar().encode(x='action', y='count()'), use_container_width=True)

with tab4:
    st.write("### 🌤️ Daily Weather Log")
    if "user" in st.session_state:
        # Automatic Log
        today = datetime.date.today().isoformat()
        if not supabase.table("weather_logs").select("date").eq("user_id", st.session_state["user"].id).eq("date", today).execute().data:
            w = fetch_weather()
            supabase.table("weather_logs").insert({
                "user_id": str(st.session_state["user"].id), "date": today, "temperature": float(w['temp']), 
                "conditions": str(w['conditions']), "precipitation": float(w['rain']),
                "wind_speed": float(w['wind_speed']), "wind_direction": float(w['wind_dir'])
            }).execute()
            st.rerun()
        
        # Sync Historical
        if st.button("🔄 Sync Historical Data"):
            start = datetime.date(2026, 1, 1)
            for i in range((datetime.date.today() - start).days + 1):
                day = (start + datetime.timedelta(days=i)).isoformat()
                if not supabase.table("weather_logs").select("date").eq("user_id", st.session_state["user"].id).eq("date", day).execute().data:
                    hw = fetch_weather_historical(day)
                    supabase.table("weather_logs").insert({
                        "user_id": str(st.session_state["user"].id), "date": day, "temperature": float(hw['temp']), 
                        "conditions": str(hw['conditions']), "precipitation": float(hw['rain']),
                        "wind_speed": float(hw['wind_speed']), "wind_direction": float(hw['wind_dir'])
                    }).execute()
            st.rerun()

        # Display Data with "Zero-Fill" Logic
        hist = supabase.table("weather_logs").select("*").eq("user_id", st.session_state["user"].id).order("date", desc=True).execute()
        if hist.data:
            df_w = pd.DataFrame(hist.data)
            
            # This forces 'None' or empty values to be 0
            df_w['wind_speed'] = pd.to_numeric(df_w['wind_speed'], errors='coerce').fillna(0)
            df_w['wind_direction'] = pd.to_numeric(df_w['wind_direction'], errors='coerce').fillna(0)
            
            st.dataframe(df_w, use_container_width=True)
