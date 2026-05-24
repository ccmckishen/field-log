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
WMO_CODES = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain"}

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
    except Exception:
        return None

# --- 2. AUTHENTICATION & LIBRARY ---
if "user" not in st.session_state:
    session = supabase.auth.get_session()
    if session: st.session_state["user"] = session.user

@st.cache_data(ttl=60)
def load_library():
    try:
        response = supabase.table("seeds").select("seed_id, genus, species, common_name, variety, sowing_instructions").execute()
        df = pd.DataFrame(response.data)
        df['display_name'] = df['common_name'] + " - " + df['variety'] + " (" + df['genus'] + " " + df['species'] + ")"
        return df
    except Exception:
        return pd.DataFrame()

df = load_library()

# --- 3. APP UI ---
st.title("☁️ Cloud Field App")
tab1, tab2, tab3, tab4 = st.tabs(["🗂️ Library", "📝 Field Log", "📊 Insights", "🌤️ Weather History"])

with tab1:
    search_term = st.text_input("🔍 Search Library...")
    if not df.empty:
        filtered = df[df['common_name'].str.contains(search_term, case=False, na=False) | df['variety'].str.contains(search_term, case=False, na=False)] if search_term else df
        for _, row in filtered.iterrows():
            with st.expander(f"🌿 {row['common_name']} - {row['variety']}"):
                st.write(f"Botanical: *{row['genus']} {row['species']}*")
                st.info(row.get('sowing_instructions', 'No instructions.'))

with tab2:
    if "user" not in st.session_state:
        st.warning("Please log in.")
    else:
        common = st.selectbox("1. Common Name:", ["-- All --"] + sorted(df['common_name'].unique().tolist()))
        genus_df = df if common == "-- All --" else df[df['common_name'] == common]
        genus = st.selectbox("2. Genus:", ["-- All --"] + sorted(genus_df['genus'].unique().tolist()))
        spec_df = genus_df if genus == "-- All --" else genus_df[genus_df['genus'] == genus]
        species = st.selectbox("3. Species:", ["-- All --"] + sorted(spec_df['species'].unique().tolist()))
        final_df = spec_df if species == "-- All --" else spec_df[spec_df['species'] == species]
        plant_dict = dict(sorted(zip(final_df['display_name'], final_df['seed_id'])))
        
        with st.form("log_form", clear_on_submit=True):
            selected_plant = st.selectbox("4. Plant:", ["-- Choose --"] + list(plant_dict.keys()))
            action = st.selectbox("5. Action?", ["Soil Amendment", "Started Indoors", "Direct Sowed", "Transplanted", "Fertilized", "Watering", "Pruned/Trained", "Pest Discovery", "Weather Event", "Harvested", "Failed/Lost", "General Observation"])
            notes = st.text_area("6. Notes")
            if st.form_submit_button("☁️ Save to Cloud"):
                if selected_plant != "-- Choose --":
                    supabase.table("field_logs").insert({"seed_id": plant_dict[selected_plant], "action": action, "notes": notes, "user_id": str(st.session_state["user"].id)}).execute()
                    st.success("Logged!")
                    st.rerun()

with tab3:
    st.write("### 📈 Analytics")
    if "user" in st.session_state:
        logs = supabase.table("field_logs").select("*").eq("user_id", st.session_state["user"].id).execute()
        if logs.data:
            log_df = pd.DataFrame(logs.data)
            chart = alt.Chart(log_df['action'].value_counts().reset_index()).mark_bar(color='#2E8B57').encode(x='action', y='count')
            st.altair_chart(chart, use_container_width=True)

with tab4:
    st.write("### 🌤️ Daily Weather Log")
    if "user" in st.session_state:
        # --- NEW: BACK-FILL BUTTON ---
        if st.button("🔄 Sync Historical Data (Jan 1, 2026 - Today)"):
            start_date = datetime.date(2026, 1, 1)
            end_date = datetime.date.today()
            delta = end_date - start_date
            
            with st.spinner("Syncing data... this may take a moment."):
                for i in range(delta.days + 1):
                    day = start_date + datetime.timedelta(days=i)
                    day_str = day.isoformat()
                    
                    # Check if exists
                    check = supabase.table("weather_logs").select("date").eq("user_id", st.session_state["user"].id).eq("date", day_str).execute()
                    if not check.data:
                        # Fetch historical
                        hist_weather = fetch_weather_historical(day_str) # See helper below
                        if hist_weather:
                            supabase.table("weather_logs").insert({
                                "user_id": str(st.session_state["user"].id),
                                "date": day_str,
                                "temperature": float(hist_weather['temp']),
                                "conditions": str(hist_weather['conditions']),
                                "precipitation": float(hist_weather['rain'])
                            }).execute()
                st.success("History sync complete!")
                st.rerun()

        # Display History (Same as before)
        hist = supabase.table("weather_logs").select("*").eq("user_id", st.session_state["user"].id).order("date", desc=True).execute()
        if hist.data:
            st.dataframe(pd.DataFrame(hist.data), use_container_width=True)
