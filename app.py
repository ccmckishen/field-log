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

# --- 2. WEATHER HELPERS ---
LAT, LON = "41.109", "-74.585"
WMO_CODES = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain"}

def fetch_weather():
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,precipitation,weather_code,wind_speed_10m,wind_direction_10m&temperature_unit=fahrenheit&precipitation_unit=inch&wind_speed_unit=mph&timezone=America/New_York"
        res = requests.get(url).json().get('current', {})
        return {
            "temp": res.get('temperature_2m', 0),
            "rain": res.get('precipitation', 0),
            "conditions": WMO_CODES.get(res.get('weather_code', 0), "Clear"),
            "wind_speed": res.get('wind_speed_10m', 0),
            "wind_dir": res.get('wind_direction_10m', 0)
        }
    except Exception: return None

def fetch_weather_historical(date_str):
    try:
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={LAT}&longitude={LON}&start_date={date_str}&end_date={date_str}&daily=temperature_2m_mean,precipitation_sum,weather_code,wind_speed_10m_max,wind_direction_10m_dominant&temperature_unit=fahrenheit&precipitation_unit=inch&wind_speed_unit=mph&timezone=America/New_York"
        res = requests.get(url).json().get('daily', {})
        return {
            "temp": res.get('temperature_2m_mean', [0])[0],
            "rain": res.get('precipitation_sum', [0])[0],
            "conditions": WMO_CODES.get(res.get('weather_code', [0])[0], "Clear"),
            "wind_speed": res.get('wind_speed_10m_max', [0])[0],
            "wind_dir": res.get('wind_direction_10m_dominant', [0])[0]
        }
    except Exception: return None

# --- 3. AUTH & LIBRARY ---
if "user" not in st.session_state:
    session = supabase.auth.get_session()
    if session: st.session_state["user"] = session.user

@st.cache_data(ttl=3600)
def load_library():
    try:
        response = supabase.table("seeds").select("seed_id, genus, species, common_name, variety, sowing_instructions").execute()
        df = pd.DataFrame(response.data)
        df['display_name'] = df['common_name'] + " - " + df['variety'] + " (" + df['genus'] + " " + df['species'] + ")"
        return df
    except Exception: return pd.DataFrame()

df = load_library()

# --- 4. APP UI ---
st.title("☁️ Cloud Field App")
tab1, tab2, tab3, tab4 = st.tabs(["🗂️ Library", "📝 Field Log", "📊 Insights", "🌤️ Weather History"])

with tab1:
    search = st.text_input("🔍 Search Library...")
    filtered = df[df['common_name'].str.contains(search, case=False, na=False) | df['variety'].str.contains(search, case=False, na=False)] if search else df
    for _, row in filtered.iterrows():
        with st.expander(f"🌿 {row['common_name']} - {row['variety']}"):
            st.write(f"Botanical: *{row['genus']} {row['species']}*")
            st.info(row.get('sowing_instructions', 'No instructions.'))

with tab2:
    if "user" in st.session_state:
        with st.form("log_form", clear_on_submit=True):
            plant = st.selectbox("Plant:", ["-- Choose --"] + list(df['display_name'].tolist()))
            action = st.selectbox("Action?", ["Watering", "Direct Sowed", "Harvested", "General Observation", "Weather Event"])
            notes = st.text_area("Notes")
            if st.form_submit_button("☁️ Save to Cloud"):
                seed_id = df[df['display_name'] == plant]['seed_id'].iloc[0]
                supabase.table("field_logs").insert({"seed_id": int(seed_id), "action": action, "notes": notes, "user_id": str(st.session_state["user"].id)}).execute()
                st.success("Logged!")
                st.rerun()

with tab3:
    st.write("### 📈 Analytics")
    if "user" in st.session_state:
        logs = supabase.table("field_logs").select("*").eq("user_id", st.session_state["user"].id).execute()
        if logs.data:
            # This is the corrected line
            st.altair_chart(alt.Chart(pd.DataFrame(logs.data)).mark_bar().encode(x='action', y='count()'), use_container_width=True)
