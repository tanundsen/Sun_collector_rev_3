import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from heat_loss_utils import compute_heat_losses
from scipy.interpolate import griddata
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# --- Page config ---
st.set_page_config(page_title="♨️ Heat Loss Components", layout="wide")
st.title("🔥 Pool Heat Loss Breakdown by Component")

# --- Sidebar controls ---
st.sidebar.header("Input Parameters")

month = st.sidebar.selectbox("Select Month", [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
])

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
        "Highly shielded (5%) – Partly enclosed"
    ]
)
shielding_factor = {
    "Open exposure (70%) – e.g. Open deck without any obstructions": 0.7,
    "Partly shielded (40%) – some walls or windbreaks": 0.4,
    "Recessed or surrounded (15%) – Recessed or large wind breaks": 0.15,
    "Highly shielded (5%) – Partly enclosed": 0.05
}[shielding]

# --- Load climate data ---
@st.cache_data
def load_data():
    return pd.read_csv("climate_data_sea.csv")

df = load_data()
lat = df["lat"].values
lon = df["lon"].values

ghi_cols = df.columns[df.columns.str.startswith("ghi_")]
mask = (df['lat'] < -65) | ((df['lat'] > 60) & (df['lon'].between(-60, -20)))
df.loc[mask, ghi_cols] *= 0.5

# Clean polar outliers
ghi_cols = df.columns[df.columns.str.startswith("ghi_")]
mask = (df['lat'] < -65) | ((df['lat'] > 60) & (df['lon'].between(-60, -20)))
df.loc[mask, ghi_cols] *= 0.5

# Climate values
tmin = df[f"tmin_{month}"].values
tmax = df[f"tmax_{month}"].values
tavg = df.get(f"tavg_{month}", (tmin + tmax) / 2).values
T_day = (tavg + tmax) / 2
T_night = (tavg + tmin) / 2
wind = df[f"ws10m_{month}"].values
wind_day = wind * shielding_factor
wind_night = 0.8 * wind * shielding_factor
rh = df[f"rh_{month}"].values
rh_day = rh
rh_night = 1.1 * rh

# --- Compute losses ---
loss = compute_heat_losses(
    pool_temp, pool_area, pool_depth, T_day, T_night,
    wind_day, wind_night, rh_day, rh_night, night_hours, cover_used
)

rad_loss = loss["rad_day"] + loss["rad_night"]
evap_loss = loss["evap_day"] + loss["evap_night"]
conv_loss = loss["conv_day"] + loss["conv_night"]
total_loss = loss["Q_day"] + loss["Q_night"]

# --- Plot function ---
def plot_loss_map(data, title, cmap):
    lon_grid = np.linspace(min(lon), max(lon), 200)
    lat_grid = np.linspace(min(lat), max(lat), 150)
    lon_mesh, lat_mesh = np.meshgrid(lon_grid, lat_grid)
    grid = griddata((lon, lat), data, (lon_mesh, lat_mesh), method='linear')

    fig, ax = plt.subplots(figsize=(8, 5), subplot_kw={'projection': ccrs.PlateCarree()})
    cf = ax.contourf(lon_mesh, lat_mesh, grid, levels=100, cmap=cmap)
    cs = ax.contour(lon_mesh, lat_mesh, grid, levels=10, colors='black', linewidths=0.4)
    ax.clabel(cs, inline=True, fontsize=8, fmt="%.0f")
    ax.coastlines()
    ax.add_feature(cfeature.BORDERS, linestyle=':')
    ax.set_title(title)
    fig.colorbar(cf, ax=ax, orientation='vertical', shrink=0.7, label='kWh/day')
    return fig

# --- Show plots ---
col1, col2 = st.columns(2)
with col1:
    st.pyplot(plot_loss_map(rad_loss, "Radiation Loss per Day", "jet"))
    st.pyplot(plot_loss_map(evap_loss, "Evaporation Loss per Day", "jet"))
with col2:
    st.pyplot(plot_loss_map(conv_loss, "Convection Loss per Day", "jet"))
    st.pyplot(plot_loss_map(total_loss, "Total Heat Loss per Day", "jet"))
