import streamlit as st
import pandas as pd
from supabase import create_client
import datetime
import altair as alt
import requests
import time
import plotly.graph_objects as go
import pandas as pd

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

# UPDATE THIS LINE
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["🗂️ Library", "🌱 Season Plan", "📝 Field Log", "📊 Insights", "🌤️ Weather History", "👤 Profile", "🗺️ Garden Planner"])
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
    st.write("### 🌱 Current Season Planting List")
    st.write("Select the crops from your master library that you are growing this season.")
    
    # Fetch seed data including our new column
    seeds = supabase.table("seeds").select("seed_id, common_name, variety, is_active_season").execute().data
    
    if seeds:
        df = pd.DataFrame(seeds)
        
        # 1. Interactive Checklist
        st.write("**1. Select Active Seeds:**")
        edited_df = st.data_editor(
            df,
            column_config={
                "seed_id": None, # Hides the database ID from the UI
                "common_name": "Common Name",
                "variety": "Variety",
                "is_active_season": st.column_config.CheckboxColumn(
                    "Planting This Season?",
                    help="Check this box to add the seed to your active season list.",
                    default=False,
                )
            },
            disabled=["common_name", "variety"], # Prevents accidental renaming of the seeds here
            hide_index=True,
            use_container_width=True,
            key="season_editor"
        )
        
        # Save Button for the Checklist
        if st.button("💾 Save Season List"):
            for index, row in edited_df.iterrows():
                # Only update the database if the status changed to save API calls
                original_status = next(s['is_active_season'] for s in seeds if s['seed_id'] == row['seed_id'])
                if row['is_active_season'] != original_status:
                    supabase.table("seeds").update({"is_active_season": row["is_active_season"]}).eq("seed_id", row["seed_id"]).execute()
            st.success("Season list updated!")
            st.rerun()
            
        st.write("---")
        
        # 2. Clean Summary View
        st.write("### 📋 Your Active Roster")
        active_seeds = [s for s in seeds if s.get('is_active_season') == True]
        
        if active_seeds:
            # Create a clean dataframe for display
            display_df = pd.DataFrame(active_seeds)[["common_name", "variety"]]
            display_df.columns = ["Crop", "Variety"]
            st.table(display_df)
        else:
            st.info("No seeds selected for this season yet. Check the boxes above and hit save!")
    else:
        st.warning("Your seed library is empty. Add seeds in Tab 1 first.")

with tab3:
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

with tab4:
    logs = supabase.table("field_logs").select("*").eq("user_id", st.session_state["user"].id).execute()
    if logs.data: st.altair_chart(alt.Chart(pd.DataFrame(logs.data)).mark_bar().encode(x='action', y='count()'), use_container_width=True)

with tab5:
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
                    time.sleep(1.2) # Forces pause to keep API connection alive
                    supabase.table("weather_logs").insert({
                        "user_id": str(st.session_state["user"].id), "date": day, "temperature": float(hw['temp']), 
                        "conditions": str(hw['conditions']), "precipitation": float(hw['rain']),
                        "wind_speed": float(hw['wind_speed'])
                    }).execute()
            st.rerun()

        # Display Data
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
with tab6:
    st.write("### 👤 Location Settings")
    zip_code = st.text_input("Enter your ZIP Code:")
    if st.button("Save Location"):
        lat, lon = get_lat_lon(zip_code)
        if lat and lon:
            supabase.table("user_settings").upsert({"user_id": str(st.session_state["user"].id), "lat": lat, "lon": lon}).execute()
            st.success("Location saved!")
        else: st.error("Invalid ZIP Code.")
with tab7:
    st.write("### 🌿 Garden Layout & Planner")

    # --- 1. SETUP SESSION STATE ---
    if 'edit_bed_id' not in st.session_state:
        st.session_state.edit_bed_id = None
        st.session_state.edit_data = None

    # --- 2. ADD/EDIT BED FORM ---
    with st.expander("➕ Define/Update Bed", expanded=(st.session_state.edit_bed_id is not None)):
        with st.form("bed_form"):
            default = st.session_state.edit_data if st.session_state.edit_data else {"name":"", "length_ft":0, "width_ft":0, "row_order":1}
            b_name = st.text_input("Bed Name", value=default['name'])
            c1, c2 = st.columns(2)
            
            # Updated to increment by 1 (Integers)
            b_len = c1.number_input("Length (ft)", value=int(float(default['length_ft'])), step=1)
            b_wid = c2.number_input("Width (ft)", value=int(float(default['width_ft'])), step=1)
            b_ord = st.number_input("Row Order (1, 2, 3...)", value=int(default['row_order']), step=1)
            
            submit_label = "Update Bed" if st.session_state.edit_bed_id else "Create Bed"
            c1, c2 = st.columns(2)
            if c1.form_submit_button(submit_label):
                data = {"user_id": str(st.session_state["user"].id), "name": b_name, "length_ft": b_len, "width_ft": b_wid, "row_order": b_ord}
                if st.session_state.edit_bed_id:
                    supabase.table("garden_beds").update(data).eq("id", st.session_state.edit_bed_id).execute()
                    st.session_state.edit_bed_id = None; st.session_state.edit_data = None
                else:
                    supabase.table("garden_beds").insert(data).execute()
                st.rerun()
            if st.session_state.edit_bed_id and c2.form_submit_button("Cancel"):
                st.session_state.edit_bed_id = None; st.session_state.edit_data = None; st.rerun()

    # --- 3. ADD PLANTING (Search + Cascading) ---
    with st.expander("➕ Plant Crop"):
        beds = supabase.table("garden_beds").select("id, name").eq("user_id", st.session_state["user"].id).execute().data
        seeds = supabase.table("seeds").select("seed_id, common_name, genus, species, botanical_subspecies, variety").execute().data
        
        if seeds and beds:
            search = st.text_input("🔍 Quick Search (Common, Scientific, or Variety)", "").lower()
            
            def matches_search(s, query):
                if not query: return True
                searchable_text = f"{s.get('common_name', '')} {s.get('variety', '')} {s.get('genus', '')} {s.get('species', '')} {s.get('botanical_subspecies', '')}".lower()
                return query in searchable_text

            active_seeds = [s for s in seeds if matches_search(s, search)]

            def get_sci_name(s): return f"{s['genus']} {s['species']} {s['botanical_subspecies'] or ''}".strip()
            
            if active_seeds:
                crop_names = sorted(list(set([s['common_name'] for s in active_seeds])))
                sel_crop = st.selectbox("1. Common Name", crop_names)
                
                sci_names = sorted(list(set([get_sci_name(s) for s in active_seeds if s['common_name'] == sel_crop])))
                sel_scientific = st.selectbox("2. Scientific Name", sci_names)
                
                varieties = [s for s in active_seeds if s['common_name'] == sel_crop and get_sci_name(s) == sel_scientific]
                var_map = {f"{s['variety']}": s['seed_id'] for s in varieties}
                sel_var = st.selectbox("3. Variety", list(var_map.keys()))
                
                with st.form("plant_form_detailed"):
                    c1, c2, c3, c4 = st.columns(4)
                    sel_bed = c1.selectbox("Bed", [b['name'] for b in beds])
                    
                    # Updated to integers and increment by 1
                    lin_ft = c2.number_input("Length (ft)", min_value=0, value=0, step=1)
                    start_pos = c3.number_input("Start Pos (ft)", min_value=0, value=0, step=1)
                    spacing = c4.number_input("Spacing (in)", min_value=0, value=0, step=1)
                    
                    if st.form_submit_button("Confirm Planting"):
                        bed_id = next(b['id'] for b in beds if b['name'] == sel_bed)
                        supabase.table("bed_plantings").insert({"bed_id": bed_id, "seed_id": var_map[sel_var], "linear_feet": lin_ft, "start_position_ft": start_pos, "spacing_inches": spacing}).execute()
                        st.rerun()
            else:
                st.warning("No seeds found for that search. Clear search to see all options.")
        else:
            st.info("Add beds and seeds to your library first.")

    # --- 4. VISUAL ROW DIAGRAM ---
    st.write("---")
    st.write("### 🗺️ Visual Row Inventory")
    
    def get_crop_emoji(name):
        icons = {"Tomato": "🍅", "Carrot": "🥕", "Lettuce": "🥬", "Pepper": "🫑", "Corn": "🌽", "Cucumber": "🥒", "Bean": "🫘", "Potato": "🥔", "Onion": "🧅"}
        return icons.get(name, "🌱")

    beds_data = supabase.table("garden_beds").select("*, bed_plantings(id, linear_feet, start_position_ft, spacing_inches, seeds(common_name, genus, species, botanical_subspecies, variety))").eq("user_id", st.session_state["user"].id).order("row_order").execute().data
    
    for bed in beds_data:
        st.subheader(f"Row {bed['row_order']}: {bed['name']} ({bed['length_ft']}ft)")
        
        # Bed Controls
        c1, c2 = st.columns(2)
        if c1.button("✏️ Edit Bed", key=f"edit_{bed['id']}"):
            st.session_state.edit_bed_id = bed['id']; st.session_state.edit_data = bed; st.rerun()
        if c2.button("🗑️ Delete Entire Bed", key=f"del_{bed['id']}"):
            supabase.table("bed_plantings").delete().eq("bed_id", bed['id']).execute(); supabase.table("garden_beds").delete().eq("id", bed['id']).execute(); st.rerun()
        
        # Visual Layout
        plantings = sorted(bed['bed_plantings'], key=lambda x: x['start_position_ft'])
        
        visual_row = []
        current_pos = 0
        for p in plantings:
            if p['start_position_ft'] > current_pos:
                visual_row.append(f"⚪ Empty ({p['start_position_ft'] - current_pos}ft)")
            emoji = get_crop_emoji(p['seeds']['common_name'])
            visual_row.append(f"{emoji} {p['seeds']['common_name']} ({p['linear_feet']}ft)")
            current_pos = p['start_position_ft'] + p['linear_feet']
        if current_pos < bed['length_ft']:
            visual_row.append(f"⚪ Empty ({bed['length_ft'] - current_pos}ft)")
        st.markdown(f"**Layout:** {' ➡️ '.join(visual_row)}")
            
        # Individual Crop Management
        if plantings:
            display_data = []
            for p in plantings:
                s = p['seeds']
                sci_name = f"{s['genus']} {s['species']} {s['botanical_subspecies'] or ''}".strip()
                display_data.append({"Variety": f"{s['common_name']} ({s['variety']})", "Scientific": sci_name, "Pos": p['start_position_ft'], "Ft": p['linear_feet']})
            st.table(pd.DataFrame(display_data))
            
            st.write("**Remove Crops:**")
            for p in plantings:
                if st.button(f"Remove {p['seeds']['common_name']} @ {p['start_position_ft']}ft", key=f"del_plant_{p['id']}"):
                    supabase.table("bed_plantings").delete().eq("id", p['id']).execute(); st.rerun()
        else:
            st.info("Bed is empty.")
