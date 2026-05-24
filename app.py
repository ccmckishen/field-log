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

# --- WEATHER HELPERS ---
LAT, LON = "41.109", "-74.585"
WMO_CODES = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain"}

def fetch_weather():
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,precipitation,weather_code&temperature_unit=fahrenheit&precipitation_unit=inch&timezone=America/New_York"
        res = requests.get(url).json()
        code = res['current']['weather_code']
        return {"temp": res['current']['temperature_2m'], "rain": res['current']['precipitation'], "conditions": WMO_CODES.get(code, f"Code: {code}")}
    except Exception: return None

def fetch_weather_historical(date_str):
    try:
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={LAT}&longitude={LON}&start_date={date_str}&end_date={date_str}&daily=temperature_2m_mean,precipitation_sum,weather_code&temperature_unit=fahrenheit&precipitation_unit=inch&timezone=America/New_York"
        res = requests.get(url).json()
        return {
            "temp": res['daily']['temperature_2m_mean'][0],
            "rain": res['daily']['precipitation_sum'][0],
            "conditions": WMO_CODES.get(res['daily']['weather_code'][0], "N/A")
        }
    except Exception: return None

# --- 2. AUTHENTICATION & LIBRARY ---
if "user" not in st.session_state:
    session = supabase.auth.get_session()
    if session: st.session_state["user"] = session.user

@st.cache_data(ttl=3600) # Increased TTL for performance
def load_library():
    try:
        response = supabase.table("seeds").select("seed_id, genus, species, common_name, variety, sowing_instructions").execute()
        return pd.DataFrame(response.data)
    except Exception: return pd.DataFrame()

df = load_library()

# --- 3. APP UI ---
st.title("☁️ Cloud Field App")
tab1, tab2, tab3, tab4 = st.tabs(["🗂️ Library", "📝 Field Log", "📊 Insights", "🌤️ Weather History"])

with tab1:
    search = st.text_input("🔍 Search Library...")
    if not df.empty:
        filtered = df[df['common_name'].str.contains(search, case=False, na=False)] if search else df
        for _, row in filtered.iterrows():
            with st.expander(f"🌿 {row['common_name']} - {row['variety']}"):
                st.write(f"Botanical: *{row['genus']} {row['species']}*")
                st.info(row.get('sowing_instructions', 'No instructions.'))

with tab2:
    if "user" in st.session_state:
        with st.form("log_form", clear_on_submit=True):
            action = st.selectbox("Action?", ["Watering", "Direct Sowed", "Harvested", "General Observation"])
            notes = st.text_area("Notes")
            if st.form_submit_button("☁️ Save"):
                supabase.table("field_logs").insert({"action": action, "notes": notes, "user_id": str(st.session_state["user"].id)}).execute()
                st.rerun()

with tab3:
    st.write("### 📈 Analytics")
    if "user" in st.session_state:
        logs = supabase.table("field_logs").select("*").eq("user_id", st.session_state["user"].id).execute()
        if logs.data:
            st.altair_chart(alt.Chart(pd.DataFrame(logs.data)).mark_bar().encode(x='action', y='count()'), use_container_width=True)

with tab4:
    st.write("### 🌤️ Daily Weather Log")
    if "user" in st.session_state:
        # Sync logic
        if st.button("🔄 Sync Historical Data"):
            start = datetime.date(2026, 1, 1)
            for i in range((datetime.date.today() - start).days + 1):
                day = (start + datetime.timedelta(days=i)).isoformat()
                if not supabase.table("weather_logs").select("date").eq("date", day).execute().data:
                    hw = fetch_weather_historical(day)
                    if hw:
                        supabase.table("weather_logs").insert({"user_id": str(st.session_state["user"].id), "date": day, "temperature": float(hw['temp']), "conditions": str(hw['conditions']), "precipitation": float(hw['rain'])}).execute()
            st.rerun()

        hist = supabase.table("weather_logs").select("*").eq("user_id", st.session_state["user"].id).order("date", desc=True).execute()
        if hist.data: st.dataframe(pd.DataFrame(hist.data), use_container_width=True)
