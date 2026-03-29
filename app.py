# =====================================================
# 🌊 PERMANENT DEPLOYMENT VERSION — STREAMLIT CLOUD
# AI UNIVERSAL FLOOD MAPPING SYSTEM
# FINAL YEAR PROJECT — PRODUCTION READY
# =====================================================

# THIS FILE IS YOUR FINAL app.py FOR GITHUB + STREAMLIT
# NO ee.Authenticate() REQUIRED
# USES SERVICE ACCOUNT FROM STREAMLIT SECRETS

# =====================================================
# REQUIREMENTS.TXT (CREATE SEPARATE FILE IN GITHUB)
# =====================================================

# streamlit
# earthengine-api
# geemap
# geopandas
# pandas

# =====================================================
# STREAMLIT APP CODE STARTS HERE
# =====================================================

import streamlit as st
import ee
import geemap.foliumap as geemap
import geopandas as gpd
import pandas as pd
import zipfile
import json
import os

# =====================================================
# AUTHENTICATION USING SERVICE ACCOUNT (NO LOGIN)
# =====================================================

# Streamlit Cloud stores credentials in secrets.toml
# We load them here

service_account_info = st.secrets["gcp_service_account"]

credentials = ee.ServiceAccountCredentials(
    service_account_info["client_email"],
    key_data=json.dumps(service_account_info)
)

ee.Initialize(credentials)

# =====================================================
# PAGE SETTINGS
# =====================================================

st.set_page_config(
    page_title="AI Flood Mapping System",
    layout="wide"
)

st.title("🌊 AI-Based Universal Flood Mapping System")

# =====================================================
# INPUT SECTION
# =====================================================

st.header("1️⃣ Select Area Input")

input_type = st.radio(
    "Choose Input Type",
    ["Coordinates", "Upload Shapefile ZIP"]
)

# ---------------- COORDINATES ----------------

if input_type == "Coordinates":

    col1, col2 = st.columns(2)

    with col1:
        lon_min = st.number_input(
            "Longitude Min",
            value=76.5
        )

        lat_min = st.number_input(
            "Latitude Min",
            value=31.2
        )

    with col2:
        lon_max = st.number_input(
            "Longitude Max",
            value=77.6
        )

        lat_max = st.number_input(
            "Latitude Max",
            value=32.0
        )

    aoi = ee.Geometry.Rectangle([
        lon_min,
        lat_min,
        lon_max,
        lat_max
    ])

# ---------------- SHAPEFILE ----------------

else:

    uploaded_file = st.file_uploader(
        "Upload ZIP Shapefile",
        type="zip"
    )

    if uploaded_file is not None:

        zip_path = "uploaded_shape.zip"

        with open(zip_path, "wb") as f:
            f.write(uploaded_file.read())

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall("shapefile")

        gdf = gpd.read_file("shapefile")

        aoi = geemap.geopandas_to_ee(gdf)

# =====================================================
# DATE INPUT
# =====================================================

st.header("2️⃣ Select Flood Dates")

col1, col2 = st.columns(2)

with col1:

    before_start = st.date_input(
        "Before Start",
        pd.to_datetime("2025-07-01")
    )

    before_end = st.date_input(
        "Before End",
        pd.to_datetime("2025-07-20")
    )

with col2:

    after_start = st.date_input(
        "After Start",
        pd.to_datetime("2025-08-01")
    )

    after_end = st.date_input(
        "After End",
        pd.to_datetime("2025-08-20")
    )

before_start = str(before_start)
before_end = str(before_end)
after_start = str(after_start)
after_end = str(after_end)

# =====================================================
# PREPROCESS BUTTON
# =====================================================

st.header("3️⃣ Preprocess Data")

if st.button("Run Preprocessing"):

    st.info("Analyzing terrain and preparing satellite data...")

    terrain = ee.Terrain.slope(
        ee.Image("USGS/SRTMGL1_003")
    )

    avg_slope = terrain.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=90,
        maxPixels=1e13
    ).get('slope')

    avg_slope = ee.Number(avg_slope)

    st.success("Preprocessing completed")

    st.write(
        "Average Slope:",
        avg_slope.getInfo()
    )

# =====================================================
# GENERATE FLOOD MAP BUTTON
# =====================================================

st.header("4️⃣ Generate Flood Map")

if st.button("Generate Flood Map"):

    st.info("Detecting flood areas...")

    def reduce_speckle(img):
        return img.focal_median(40, 'square', 'meters')

    def get_s1(start, end):
        return (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filterDate(start, end)
            .filter(ee.Filter.eq('instrumentMode', 'IW'))
            .filter(
                ee.Filter.listContains(
                    'transmitterReceiverPolarisation',
                    'VV'
                )
            )
            .select('VV')
            .map(reduce_speckle)
        )

    before = get_s1(before_start, before_end).median()
    after = get_s1(after_start, after_end).median()

    change = before.subtract(after)

    stats = change.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.stdDev(),
            sharedInputs=True
        ),
        geometry=aoi,
        scale=30,
        maxPixels=1e13
    )

    mean = ee.Number(stats.get('VV_mean'))
    std = ee.Number(stats.get('VV_stdDev'))

    terrain = ee.Terrain.slope(
        ee.Image("USGS/SRTMGL1_003")
    )

    avg_slope = terrain.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=90,
        maxPixels=1e13
    ).get('slope')

    avg_slope = ee.Number(avg_slope)

    k = ee.Algorithms.If(
        avg_slope.gt(5),
        1.3,
        1.0
    )

    k = ee.Number(k)

    threshold = mean.add(std.multiply(k))

    flood = change.gt(threshold)

    jrc = ee.Image(
        "JRC/GSW1_4/GlobalSurfaceWater"
    ).select('occurrence')

    flood = flood.updateMask(jrc.lt(90))

    flood = flood.updateMask(terrain.lt(6))

    cleaned = flood.focal_max(1).focal_min(1)

    connected = cleaned.connectedComponents(
        connectedness=ee.Kernel.plus(1),
        maxSize=800
    )

    labeled = connected.select('labels')

    flood_zones = labeled.reduceToVectors(
        geometry=aoi,
        scale=30,
        geometryType='polygon',
        labelProperty='zone_id',
        reducer=ee.Reducer.countEvery(),
        maxPixels=1e13
    )

    flood_zones = flood_zones.filter(
        ee.Filter.gt('count', 120)
    )

    st.success("Flood Map Generated")

    Map = geemap.Map()

    Map.addLayer(
        cleaned.clip(aoi),
        {
            'palette': ['blue']
        },
        'Flood'
    )

    Map.addLayer(
        flood_zones.style(
            color='yellow',
            fillColor='00000000'
        ),
        {},
        'Flood Zones'
    )

    Map.centerObject(
        aoi,
        9
    )

    Map.addLayerControl()

    Map.to_streamlit(height=650)

# =====================================================
# END OF FILE
# =====================================================
