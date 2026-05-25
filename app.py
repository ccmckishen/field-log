import streamlit as st
import pandas as pd
from supabase import create_client
import datetime
import altair as alt
import requests
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Cloud Field App", page_icon="☁️", layout="wide")

@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# --- 2. HELPERS ---
WMO_CODES = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain"}

def get_lat_lon(zip_code):
    try:
        url = f"https://nominatim.openstreetmap.org/search?postalcode={zip_code}&country=US&format=json"
        res = requests.get(url, headers={'User-Agent': 'CloudFieldApp'}).json()
        return (res[0]['lat'], res[0]['lon']) if res else (None, None)
    except Exception: return None, None

def fetch_weather(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,precipitation,weather_code,wind_speed_10m&temperature_unit=fahrenheit&precipitation_unit=inch&wind_speed_unit=mph&timezone=America/New_York"
        res = requests.get(url).json().get('current', {})
        return {
            "temp": res.get('temperature_2m', 0.0), 
            "rain": res.get('precipitation', 0.0),
            "conditions": WMO_CODES.get(res.get('weather_code', 0), "Clear"),
            "wind_speed": res.get('wind_speed_10m', 0.0)
        }
    except Exception: return {"temp": 0.0, "rain": 0.0, "conditions": "Clear", "wind_speed": 0.0}

def fetch_weather_historical(lat, lon, date_str):
    res_om = {"temp": 0.0, "rain": 0.0, "conditions": "Clear"}
    res_vc = {"wind_speed": 0.0}

    # 1. Fetch Open-Meteo
    try:
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={date_str}&end_date={date_str}&daily=temperature_2m_mean,precipitation_sum,weather_code&temperature_unit=fahrenheit&precipitation_unit=inch&timezone=America/New_York"
        data = requests.get(url).json().get('daily', {})
        res_om = {
            "temp": data.get('temperature_2m_mean', [0.0])[0],
            "rain": data.get('precipitation_sum', [0.0])[0],
            "conditions": WMO_CODES.get(data.get('weather_code', [0])[0], "Clear")
        }
    except Exception: pass

    # 2. Fetch Visual Crossing
    try:
        api_key = st.secrets["VC_API_KEY"]
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/{date_str}/{date_str}?unitGroup=us&include=days&key={api_key}&contentType=json"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()['days'][0]
            res_vc = {"wind_speed": data.get('windspeed', 0.0)}
    except Exception: pass

    return {**res_om, **res_vc}
# --- 3. AUTH & LIBRARY ---
def render_auth_ui():
    st.title("🔐 Login / Sign Up")
    email, password = st.text_input("Email"), st.text_input("Password", type="password")
    c1, c2 = st.columns(2)
    if c1.button("Login"):
        try:
            st.session_state["user"] = supabase.auth.sign_in_with_password({"email": email, "password": password}).user
            st.rerun()
        except: st.error("Login failed.")
    if c2.button("Sign Up"):
        try:
            supabase.auth.sign_up({"email": email, "password": password})
            st.success("Account created!")
        except: st.error("Signup failed.")
    st.stop()

if "user" not in st.session_state:
    session = supabase.auth.get_session()
    if session: st.session_state["user"] = session.user
    else: render_auth_ui()

@st.cache_data(ttl=3600)
def load_library():
    try:
        response = supabase.table("seeds").select("seed_id, genus, species, common_name, variety, sowing_instructions").execute()
        df = pd.DataFrame(response.data)
        df['display_name'] = df['common_name'] + " - " + df['variety'] + " (" + df['genus'] + " " + df['species'] + ")"
        return df
    except: return pd.DataFrame()

df = load_library()

# --- 4. APP UI ---
st.title("☁️ Cloud Field App")
if st.sidebar.button("Logout"):
    supabase.auth.sign_out()
    del st.session_state["user"]
    st.rerun()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🗂️ Library", "📝 Field Log", "📊 Insights", "🌤️ Weather History", "👤 Profile"])

with tab1:
    st.write("### 🗂️ Seed Library")
    if not df.empty:
        common = st.selectbox("Common Name:", ["-- All --"] + sorted(df['common_name'].unique().tolist()), key="lib_c")
        g_df = df if common == "-- All --" else df[df['common_name'] == common]
        genus = st.selectbox("Genus:", ["-- All --"] + sorted(g_df['genus'].unique().tolist()), key="lib_g")
        s_df = g_df if genus == "-- All --" else g_df[g_df['genus'] == genus]
        species = st.selectbox("Species:", ["-- All --"] + sorted(s_df['species'].unique().tolist()), key="lib_s")
        f_df = s_df if species == "-- All --" else s_df[s_df['species'] == species]
        
        if common == "-- All --" and genus == "-- All --" and species == "-- All --":
            st.info("Select a category above to view seeds.")
        else:
            for _, row in f_df.iterrows():
                with st.expander(f"🌿 {row['common_name']} - {row['variety']}"):
                    st.write(f"Botanical: *{row['genus']} {row['species']}*")
                    st.info(row.get('sowing_instructions', 'No instructions.'))

with tab2:
    if not df.empty:
        common = st.selectbox("1. Common Name:", ["-- All --"] + sorted(df['common_name'].unique().tolist()), key="log_c")
        g_df = df if common == "-- All --" else df[df['common_name'] == common]
        genus = st.selectbox("2. Genus:", ["-- All --"] + sorted(g_df['genus'].unique().tolist()), key="log_g")
        s_df = g_df if genus == "-- All --" else g_df[g_df['genus'] == genus]
        species = st.selectbox("3. Species:", ["-- All --"] + sorted(s_df['species'].unique().tolist()), key="log_s")
        f_df = s_df if species == "-- All --" else s_df[s_df['species'] == species]
        
        with st.form("log_form", clear_on_submit=True):
            opts = dict(zip(f_df['display_name'], f_df['seed_id']))
            sel = st.selectbox("4. Plant:", ["-- Choose --"] + list(opts.keys()))
            act = st.selectbox("5. Action?", ["Watering", "Direct Sowed", "Harvested", "General Observation"])
            notes = st.text_area("6. Notes")
            if st.form_submit_button("☁️ Save"):
                supabase.table("field_logs").insert({"seed_id": int(opts[sel]), "action": act, "notes": notes, "user_id": str(st.session_state["user"].id)}).execute()
                st.success("Logged!")

with tab3:
    logs = supabase.table("field_logs").select("*").eq("user_id", st.session_state["user"].id).execute()
    if logs.data: st.altair_chart(alt.Chart(pd.DataFrame(logs.data)).mark_bar().encode(x='action', y='count()'), use_container_width=True)

with tab4:
    st.write("### 🌤️ Daily Weather Log")
    loc = supabase.table("user_settings").select("lat, lon").eq("user_id", st.session_state["user"].id).execute()
    
    if not loc.data or len(loc.data) == 0:
        st.warning("Please go to the 'Profile' tab and save your ZIP code first.")
    else:
        lat, lon = loc.data[0]['lat'], loc.data[0]['lon']
        today = datetime.date.today().isoformat()
        
        # Auto-log today
        if not supabase.table("weather_logs").select("date").eq("user_id", st.session_state["user"].id).eq("date", today).execute().data:
            w = fetch_weather(lat, lon)
            supabase.table("weather_logs").insert({
                "user_id": str(st.session_state["user"].id), "date": today, "temperature": float(w['temp']), 
                "conditions": str(w['conditions']), "precipitation": float(w['rain']),
                "wind_speed": float(w['wind_speed'])
            }).execute()
            st.rerun()
        
        # Sync Historical
        if st.button("🔄 Sync Historical Data"):
            start = datetime.date(2026, 1, 1)
            for i in range((datetime.date.today() - start).days + 1):
                day = (start + datetime.timedelta(days=i)).isoformat()
                if not supabase.table("weather_logs").select("date").eq("user_id", st.session_state["user"].id).eq("date", day).execute().data:
                    hw = fetch_weather_historical(lat, lon, day)
                    supabase.table("weather_logs").insert({
                        "user_id": str(st.session_state["user"].id), "date": day, "temperature": float(hw['temp']), 
                        "conditions": str(hw['conditions']), "precipitation": float(hw['rain']),
                        "wind_speed": float(hw['wind_speed'])
                    }).execute()
            st.rerun()

        # Display Refined Data
        hist = supabase.table("weather_logs").select("date, temperature, conditions, precipitation, wind_speed").eq("user_id", st.session_state["user"].id).order("date", desc=True).execute()
        
        if hist.data:
            df_w = pd.DataFrame(hist.data)
            df_w['conditions'] = df_w['conditions'].replace(['N/A', 'None', 'not available'], 'Clear').fillna('Clear')
            df_w['wind_speed'] = df_w['wind_speed'].fillna(0)
            
            # Graphs
            st.write("#### 🌡️ Temperature (°F)")
            st.altair_chart(alt.Chart(df_w).mark_line(point=True).encode(x='date', y='temperature', tooltip=['date', 'temperature']), use_container_width=True)
            
            st.write("#### 💧 Precipitation (inches)")
            st.altair_chart(alt.Chart(df_w).mark_bar(color='steelblue').encode(x='date', y='precipitation', tooltip=['date', 'precipitation']), use_container_width=True)
            
            st.write("#### 🌬️ Wind Speed (mph)")
            st.altair_chart(alt.Chart(df_w).mark_line(color='orange', point=True).encode(x='date', y='wind_speed', tooltip=['date', 'wind_speed']), use_container_width=True)
            
            st.dataframe(df_w, use_container_width=True, hide_index=True)
with tab5:
    st.write("### 👤 Location Settings")
    zip_code = st.text_input("Enter your ZIP Code:")
    if st.button("Save Location"):
        lat, lon = get_lat_lon(zip_code)
        if lat and lon:
            supabase.table("user_settings").upsert({"user_id": str(st.session_state["user"].id), "lat": lat, "lon": lon}).execute()
            st.success("Location saved!")
        else: st.error("Invalid ZIP Code.")
