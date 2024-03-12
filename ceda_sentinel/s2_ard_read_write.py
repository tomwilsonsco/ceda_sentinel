import requests
from bs4 import BeautifulSoup
import re
import lxml
from datetime import datetime, timedelta
from shapely.geometry import box
from fiona.drvsupport import supported_drivers
import geopandas as gpd
import rasterio as rio
from rasterio.windows import from_bounds
from rasterio.plot import show
from pathlib import Path
import numpy as np


def read_from_row(gdf_row, link_col="image_links", band_idx_list=[1, 2, 3, 7]):
    s2_link = gdf_row["image_links"]
    minx, miny, maxx, maxy = gdf_row.geometry.bounds
    with rio.open(s2_link) as src:
        window = from_bounds(minx, miny, maxx, maxy, src.transform)
        window_data = src.read(band_idx_list, window=window)
        prof = src.profile
    return window_data, prof, window


def band_descriptions(gdf, link_col="image_links"):
    s2_link = gdf.head(1)[link_col]
    with rio.open(s2_link) as src:
        band_names = src.descriptions
    return band_names


def check_no_data(window_data, prof):
    nodata = prof["nodata"]
    return np.all(window_data == nodata) or np.all(np.isnan(window_data))


def plot_sample_image(gdf, link_col="image_links", plot_row=0):
    gdf = gdf[gdf[link_col].notna()]
    # Check if the GeoDataFrame is empty
    if gdf.empty:
        raise ValueError("The GeoDataFrame is empty.")

    # Select a random row
    current_row = gdf.iloc[plot_row]

    # Get the image link (assuming it's the first link in 'image_links' column)
    window_data, prof, window = read_from_row(current_row)
    window_data = window_data[[3, 2, 1], :, :]
    if check_no_data(window_data, prof):
        return plot_sample_image(gdf, link_col, plot_row + 1)
    else:
        show(window_data)


def write_s2_windows_to_tif(
    gdf,
    output_folder="outputs",
    link_col="image_links",
    aoi_id_column=None,
    band_idx_list=[1, 2, 3, 7],
):
    gdf = gdf[gdf[link_col].notna()]
    # Check if the GeoDataFrame is empty
    if gdf.empty:
        raise ValueError("The GeoDataFrame is empty.")
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    for idx, row in gdf.iterrows():
        window_data, prof, window = read_from_row(
            row, link_col=link_col, band_idx_list=band_idx_list
        )

        if check_no_data(window_data, prof):
            print(f"Skipping row {idx} as all pixels are no-data values.")
            continue

        new_transform = rio.windows.transform(window, prof["transform"])

        # Determine the file name
        if aoi_id_column and aoi_id_column in row:
            aoi_id = f"{row[aoi_id_column]}"
        else:
            aoi_id = idx

        image_file_name = Path(row[link_col]).name
        file_name = output_folder / f"{aoi_id}_{image_file_name}"

        # Write to a TIFF file

        prof.update(
            count=len(band_idx_list),
            transform=new_transform,
            width=window_data.shape[2],
            height=window_data.shape[1],
        )
        with rio.open(f"{file_name}.tif", "w", **prof) as dst:
            dst.write(window_data)
        print(f"written {file_name}")
