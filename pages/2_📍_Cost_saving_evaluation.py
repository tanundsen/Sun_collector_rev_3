
from heat_loss_utils import compute_heat_losses
import streamlit as st
import pandas as pd
import numpy as np
from streamlit_folium import st_folium
import folium
import matplotlib.pyplot as plt

st.set_page_config(page_title="📍 Monthly Ship Location & Energy Savings", layout="wide")
st.title("📍 Monthly Ship Location & Energy Savings")

@st.cache_data
def load_data():
    return pd.read_csv("climate_data_sea.csv")

df = load_data()

# Sidebar input
cop = st.sidebar.slider("COP of Electric Heating System", 1.0, 6.0, 3.0)
st.sidebar.header("System Parameters")
usd_per_liter = st.sidebar.slider("Diesel Cost (USD/liter)", 0.5, 2.0, 1.2)
helideck_area = st.sidebar.slider("Solar collector Area (m²)", 50, 140, 75)
collector_efficiency = st.sidebar.slider("Collector Efficiency (%)", 10, 100, 70) / 100
pool_temp = st.sidebar.slider("Desired Pool Temp (°C)", 20, 35, 28)
pool_area = st.sidebar.slider("Pool Area (m²)", 10, 100, 50)
pool_depth = 1.5
night_hours = 12
cover_used = st.sidebar.checkbox("Use Pool Cover at Night", value=True)

shielding = st.sidebar.selectbox(
    "Wind speed at pool surface relative to 10 m reference wind speed", [
        "Open exposure (70%) – e.g. Open deck without any obstructions",
        "Partly shielded (40%) – some walls or windbreaks",
        "Recessed or surrounded (15%) – Recessed or large wind breaks",
        "Highly shielded (5%) – partly enclosed"
    ]
)
shielding_factor = {
    "Open exposure (70%) – e.g. Open deck without any obstructions": 0.7,
    "Partly shielded (40%) – some walls or windbreaks": 0.4,
    "Recessed or surrounded (15%) – Recessed or large wind breaks": 0.15,
    "Highly shielded (5%) – partly enclosed": 0.05
}[shielding]

months_ordered = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]
short_months = [m[:3].lower() for m in months_ordered]

# Session state initialization
if "coords_by_month" not in st.session_state:
    st.session_state.coords_by_month = {}

# Month label mapping
month_display_labels = []
month_label_to_real = {}
for month in months_ordered:
    short = month[:3].lower()
    has_coords = short in st.session_state.coords_by_month
    label = f"✅ {month}" if has_coords else f"⬜ {month}"
    month_display_labels.append(label)
    month_label_to_real[label] = month

# Pick the next unassigned month by default
remaining_months = [m for m in months_ordered if m[:3].lower() not in st.session_state.coords_by_month]
default_label = f"⬜ {remaining_months[0]}" if remaining_months else month_display_labels[0]

selected_labels = st.multiselect(
    "Select month(s) to assign vessel location:",
    options=month_display_labels,
    default=[default_label],
    key="month_selection"
)
selected_months = [month_label_to_real[label] for label in selected_labels]

# Map section
st.markdown("Click a point on the map to set the ship's location for the selected month(s):")
m = folium.Map(location=[20, 0], zoom_start=2)
for mkey, coord in st.session_state.coords_by_month.items():
    folium.Marker(
        coord,
        tooltip=mkey.title(),
        popup=mkey.title(),
        icon=folium.DivIcon(html=f"<div style='font-size: 10pt'>📍 {mkey.title()}</div>")
    ).add_to(m)

map_data = st_folium(m, height=720, width=1200, returned_objects=["last_clicked"])

if selected_months and map_data and map_data.get("last_clicked"):
    latlng = (map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"])
    for m in selected_months:
        st.session_state.coords_by_month[m[:3].lower()] = latlng
    st.success(f"Saved location for {', '.join(selected_months)}: {latlng}")
    st.rerun()

# Show results only if all 12 months have a location
st.markdown("---")
st.subheader("📊 Yearly Summary of Energy Use and Savings")

if len(st.session_state.coords_by_month) == 12:
    results = []
    days_in_month = {
        "January": 31, "February": 28, "March": 31, "April": 30, "May": 31, "June": 30,
        "July": 31, "August": 31, "September": 30, "October": 31, "November": 30, "December": 31
    }
    hours_day = 24 - night_hours

    for month in months_ordered:
        short = month[:3].lower()
        lat_sel, lon_sel = st.session_state.coords_by_month[short]
        df["dist"] = np.sqrt((df["lat"] - lat_sel)**2 + (df["lon"] - lon_sel)**2)
        row = df.loc[df["dist"].idxmin()]

        T_min = row[f"tmin_{month}"]
        T_max = row[f"tmax_{month}"]
        T_avg = row.get(f"tavg_{month}", (T_min + T_max)/2)
        T_day = (T_avg + T_max) / 2
        T_night = (T_avg + T_min) / 2
        ghi = row[f"ghi_{month}"]
        wind = row[f"ws10m_{month}"]
        wind_day = wind * shielding_factor
        wind_night = 0.8 * wind * shielding_factor
        rh = row[f"rh_{month}"]
        rh_day = rh
        rh_night = 1.1 * rh

        loss = compute_heat_losses(pool_temp, pool_area, pool_depth, T_day, T_night,
                                   wind_day, wind_night, rh_day, rh_night, night_hours, cover_used)

        Q_day = loss["Q_day"]
        Q_night = loss["Q_night"]
        total_loss = Q_day + Q_night
        days = days_in_month[month]

        helideck_gain = ghi * helideck_area * collector_efficiency
        pool_solar_gain = ghi * pool_area * 0.7
        net_pool_heating = max(total_loss - pool_solar_gain, 0)
        net_saving = min(helideck_gain, net_pool_heating)

        electrical_saving = net_saving * days / cop
        diesel_kg = electrical_saving * 0.2
        diesel_liters = diesel_kg / 0.84

        results.append({
            "Month": month,
            "Lat": round(lat_sel, 2),
            "Lon": round(lon_sel, 2),
            "Daily Loss (kWh)": round(total_loss, 1),
            "Daily Solar Gain (kWh)": round(helideck_gain, 1),
            "Daily Net Saving (kWh)": round(net_saving, 1),
            "Monthly Loss (kWh)": round(total_loss * days, 1),
            "Monthly Solar Gain (kWh)": round(helideck_gain * days, 1),
            "Monthly Net Saving (kWh)": round(net_saving * days, 1),
            "Elec. Saving (kWh)": round(electrical_saving, 1),
            "Diesel Saved (liters)": round(diesel_liters, 1),
            "USD Saved": round(diesel_liters * usd_per_liter, 1),
            "Evaporation (kWh)": round(loss["evap_day"] + loss["evap_night"], 1),
            "Radiation (kWh)": round(loss["rad_day"] + loss["rad_night"], 1),
            "Convection (kWh)": round(loss["conv_day"] + loss["conv_night"], 1),
        })

    df_result = pd.DataFrame(results)
    totals = df_result[[
        "Monthly Loss (kWh)", "Monthly Solar Gain (kWh)", "Monthly Net Saving (kWh)",
        "Elec. Saving (kWh)", "Diesel Saved (liters)", "USD Saved"
    ]].sum()

    df_result.loc[len(df_result)] = {
        "Month": "Total", "Lat": "-", "Lon": "-",
        "Daily Loss (kWh)": "-", "Daily Solar Gain (kWh)": "-", "Daily Net Saving (kWh)": "-",
        "Monthly Loss (kWh)": round(totals["Monthly Loss (kWh)"], 1),
        "Monthly Solar Gain (kWh)": round(totals["Monthly Solar Gain (kWh)"], 1),
        "Monthly Net Saving (kWh)": round(totals["Monthly Net Saving (kWh)"], 1),
        "Elec. Saving (kWh)": round(totals["Elec. Saving (kWh)"], 1),
        "Diesel Saved (liters)": round(totals["Diesel Saved (liters)"], 1),
        "USD Saved": round(totals["USD Saved"], 1),
        "Evaporation (kWh)": "-", "Radiation (kWh)": "-", "Convection (kWh)": "-"
    }

    st.dataframe(df_result.set_index("Month"), use_container_width=True, height=(df_result.shape[0] + 1) * 35)

    # Plot: Monthly Energy
    fig1, ax1 = plt.subplots(figsize=(10, 4))
    x = df_result['Month'][:-1]
    loss = df_result['Monthly Loss (kWh)'].iloc[:-1]
    saving = df_result['Monthly Net Saving (kWh)'].iloc[:-1]
    ax1.bar(x, loss, label='Energy Needed', color='lightgray')
    ax1.bar(x, saving, label='Net Saving', color='green')
    ax1.set_ylabel('Energy (kWh/month)')
    ax1.set_title('Monthly Energy Use vs. Solar Savings')
    ax1.legend()
    plt.xticks(rotation=45)  # ← This fixes the overlap
    st.pyplot(fig1)

    # Plot: USD Savings
    fig2, ax2 = plt.subplots(figsize=(10, 4))
    usd_saved = df_result['USD Saved'].iloc[:-1]
    ax2.bar(x, usd_saved, color='skyblue')
    ax2.set_ylabel('USD Saved')
    ax2.set_title('Monthly Diesel Cost Savings')
    plt.xticks(rotation=45)  # ← Add here too
    st.pyplot(fig2)

