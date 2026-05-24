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

# --- WEATHER DATA FETCHING (Open-Meteo) ---
LAT, LON = "41.109", "-74.585"

# WMO Weather Interpretation Codes
WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
    55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain"
}

def fetch_weather():
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,precipitation,weather_code&temperature_unit=fahrenheit&precipitation_unit=inch&timezone=America/New_York"
        res = requests.get(url).json()
        code = res['current']['weather_code']
        return {
            "temp": res['current']['temperature_2m'],
            "rain": res['current']['precipitation'],
            "conditions": WMO_CODES.get(code, f"Code: {code}")
        }
    except Exception as e:
        return None

# --- 2. AUTHENTICATION ---
if "user" not in st.session_state:
    session = supabase.auth.get_session()
    if session: st.session_state["user"] = session.user

# --- 3. APP UI ---
st.title("☁️ Cloud Field App")
tab1, tab2, tab3, tab4 = st.tabs(["🗂️ Library", "📝 Field Log", "📊 Insights", "🌤️ Weather History"])

with tab1:
    # (Keep your existing Library logic here)
    st.write("Library Tab Active")

with tab2:
    if "user" not in st.session_state:
        st.warning("Please log in.")
    else:
        # (Keep your Field Log form logic here)
        st.write("Field Log Tab Active")

with tab3:
    st.write("### 📈 My Personal Gardening Analytics")
    # (Keep your Insights chart logic here)

with tab4:
    st.write("### 🌤️ Daily Weather Log")
    if "user" in st.session_state:
        today = datetime.date.today().isoformat()
        
        # Automatic Lazy Log
        exists = supabase.table("weather_logs").select("*").eq("user_id", st.session_state["user"].id).eq("date", today).execute()
        if not exists.data:
            weather = fetch_weather()
            if weather:
                supabase.table("weather_logs").insert({
                    "user_id": st.session_state["user"].id,
                    "date": today,
                    "temperature": weather['temp'],
                    "conditions": weather['conditions'],
                    "precipitation": weather['rain']
                }).execute()
                st.rerun()

        # Display History
        hist = supabase.table("weather_logs").select("*").eq("user_id", st.session_state["user"].id).order("date", desc=True).execute()
        if hist.data:
            df_weather = pd.DataFrame(hist.data)
            st.dataframe(df_weather[['date', 'temperature', 'conditions', 'precipitation']], use_container_width=True)
            st.altair_chart(alt.Chart(df_weather).mark_line(point=True).encode(x='date', y='temperature', tooltip=['date', 'temperature', 'conditions']), use_container_width=True)
    else:
        st.warning("Please log in to view weather history.")
