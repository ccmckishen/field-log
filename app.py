import streamlit as st
import pandas as pd
from supabase import create_client, Client
import datetime
import altair as alt
import requests

# --- 1. CONFIGURATION & SUPABASE SETUP ---
st.set_page_config(page_title="Franklinville Field Log", page_icon="☁️", layout="wide")

@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# --- WEATHER HELPER ---
def fetch_current_weather():
    try:
        key = st.secrets["WEATHER_API_KEY"]
        # Fetching for Franklin, NJ
        url = f"https://api.openweathermap.org/data/2.5/weather?q=Franklin,NJ&appid={key}&units=imperial"
        res = requests.get(url).json()
        
        return {
            "temp": res['main']['temp'],
            "conditions": res['weather'][0]['description'],
            "rain": res.get('rain', {}).get('1h', 0)
        }
    except Exception as e:
        st.error(f"Weather API Error: {e}")
        return None

# --- [AUTHENTICATION & DATA FUNCTIONS REMAIN AS PREVIOUS] ---
# Ensure your load_library and save_log functions are present here.

# --- 4. APP UI ---
st.title("☁️ Cloud Field App")
tab1, tab2, tab3, tab4 = st.tabs(["🗂️ Library", "📝 Field Log", "📊 Insights", "🌤️ Weather History"])

# ... [Include Tab 1, 2, 3 logic as previously defined] ...

with tab4:
    st.write("### 🌤️ Daily Weather Log")
    if "user" in st.session_state:
        today = datetime.date.today().isoformat()
        
        # 1. Lazy Load: Does today's log exist?
        try:
            exists = supabase.table("weather_logs").select("*").eq("user_id", st.session_state["user"].id).eq("date", today).execute()
            
            if not exists.data:
                weather = fetch_current_weather()
                if weather:
                    supabase.table("weather_logs").insert({
                        "user_id": st.session_state["user"].id,
                        "date": today,
                        "temperature": weather['temp'],
                        "conditions": weather['conditions'],
                        "precipitation": weather['rain']
                    }).execute()
                    st.success("Automatically logged today's weather!")
                    st.rerun() # Refresh to show the new data
        except Exception as e:
            st.error(f"Error checking/logging weather: {e}")

        # 2. Display History
        st.write("#### Historical Weather Data")
        try:
            hist = supabase.table("weather_logs").select("*").eq("user_id", st.session_state["user"].id).order("date", desc=True).execute()
            if hist.data:
                hist_df = pd.DataFrame(hist.data)
                st.dataframe(hist_df[['date', 'temperature', 'conditions', 'precipitation']], use_container_width=True)
                
                # Chart
                chart = alt.Chart(hist_df).mark_line(color='#4682B4').encode(
                    x='date',
                    y='temperature',
                    tooltip=['date', 'temperature', 'conditions']
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No weather data logged yet.")
        except Exception as e:
            st.error(f"Could not load history: {e}")
    else:
        st.warning("Please log in to view weather history.")
