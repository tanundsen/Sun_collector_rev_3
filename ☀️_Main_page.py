
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from heat_loss_utils import compute_heat_losses

st.set_page_config(layout="wide")

# Title and logo
col_logo, col_title = st.columns([2, 5])
with col_logo:
    st.image("logo.png", width=360)
with col_title:
    st.title("☀️ Helideck Solar Collector Analysis")

# Sidebar inputs
st.sidebar.header("Input Parameters")
helideck_area = st.sidebar.slider("Solar collector Area (m²)", 50, 140, 75)
collector_efficiency = st.sidebar.slider("Collector Efficiency (%)", 10, 100, 70) / 100
pool_temp = st.sidebar.slider("Desired Pool Temp (°C)", 20, 35, 28)
pool_area = st.sidebar.slider("Pool Area (m²)", 10, 100, 50)
pool_depth = 1.5

# Nighttime parameters
night_hours = 12  # Fixed night time
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


month = st.sidebar.selectbox(
    "Select Month", [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
)

show_large = st.sidebar.checkbox("Show large savings map only")

# Load data
@st.cache_data
def load_data():
    return pd.read_csv("climate_data_sea.csv")

df = load_data()

lat = df["lat"].values
lon = df["lon"].values

ghi_cols = df.columns[df.columns.str.startswith("ghi_")]
mask = (df['lat'] < -65) | ((df['lat'] > 60) & (df['lon'].between(-60, -20)))
df.loc[mask, ghi_cols] *= 0.5

# Interpolation grid
lon_grid = np.linspace(min(lon), max(lon), 200)
lat_grid = np.linspace(min(lat), max(lat), 150)
lon_mesh, lat_mesh = np.meshgrid(lon_grid, lat_grid)

# Climate and energy parameters
value_column = f"ghi_{month}"
tmin = df[f"tmin_{month}"].values
tmax = df[f"tmax_{month}"].values
tavg = df.get(f"tavg_{month}", (tmin + tmax) / 2).values

T_day = (tavg + tmax) / 2
T_night = (tavg + tmin) / 2

ghi = df[value_column].values
wind = df[f"ws10m_{month}"].values
wind_day = wind * shielding_factor
wind_night = 0.8 * wind * shielding_factor
rh = df[f"rh_{month}"].values
rh_day = rh
rh_night = 1.1 * rh

# Heat loss calculation
loss = compute_heat_losses(pool_temp, pool_area, pool_depth, T_day, T_night, wind_day, wind_night, rh_day, rh_night, night_hours, cover_used)
Q_day = loss["Q_day"]
Q_night = loss["Q_night"]
total_loss = Q_day + Q_night

helideck_gain = ghi * helideck_area * collector_efficiency
pool_solar_gain = ghi * pool_area * 0.7
net_pool_heating = np.clip(total_loss - pool_solar_gain, 0, None)
net_saving = np.minimum(helideck_gain, net_pool_heating)

# Plotting function
def plot_map(data, title, cmap, vmin=None, vmax=None, large=False):
    figsize = (12, 7) if large else (8, 5)
    grid = griddata((lon, lat), data, (lon_mesh, lat_mesh), method='linear')
    fig, ax = plt.subplots(figsize=figsize, subplot_kw={'projection': ccrs.PlateCarree()})
    cf = ax.contourf(lon_mesh, lat_mesh, grid, levels=100, cmap=cmap, vmin=vmin, vmax=vmax)
    cs = ax.contour(lon_mesh, lat_mesh, grid, levels=10, colors='black', linewidths=0.3)
    ax.clabel(cs, inline=True, fontsize=8, fmt="%.0f")
    ax.coastlines()
    ax.add_feature(cfeature.BORDERS, linestyle=':')
    ax.set_title(title, fontsize=14 if large else 12)
    fig.colorbar(cf, ax=ax, orientation='vertical', shrink=0.7, label=title)
    return fig

# Plot results
if show_large:
    st.pyplot(plot_map(net_saving, "Energy per day from solar collector (kWh)", "jet", large=True))
else:
    col1, col2 = st.columns(2)
    with col1:
        st.pyplot(plot_map(net_saving, "Energy per day from solar collector (kWh)", "jet"))
        st.pyplot(plot_map(ghi, "Global hor. irradiance (kWh/m²/day)", "jet"))
    with col2:
        st.pyplot(plot_map(net_pool_heating, f"Total kWh per day required to maintain {pool_temp}°C", "Reds"))
        st.pyplot(plot_map(T_day, "Daytime Temperature (°C)", "coolwarm"))
