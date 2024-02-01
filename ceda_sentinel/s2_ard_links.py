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


def filter_sentinel2_tiles(aoi, tiles_layer=None):
    """
    Filters Sentinel-2 satellite tiles based on a given area of
    interest (AOI).

    Intersects input AOI with a layer of Sentinel-2 tiles.
    If no specific tile layer is provided, the function defaults to ESA
    KML file.

    Args:
        aoi (GeoDataFrame): A GeoDataFrame representing the area of
            interest (AOI) for which Sentinel-2 tiles are to be
            filtered.
        tiles_layer (GeoDataFrame, optional): A GeoDataFrame
            containing Sentinel-2 tile information. If None, the
            function automatically loads online ESA KML file.
            Defaults to None.

    Returns:
        list of str: A list of tile names (prefixed with 'T') that
            intersect with the given AOI.

    Raises:
        Any exception raised by `gpd.read_file` or `gpd.sjoin` if the
        reading of the default KML file or the spatial join operation
        fails.

    Examples:
        >>> aoi = gpd.read_file('path_to_aoi_file.shp')
        >>> filter_sentinel2_tiles(aoi)
        ['T36LYH', 'T36LZH', ...]
    """
    if tiles_layer is None:
        supported_drivers["KML"] = "rw"
        tiles_layer = gpd.read_file(
            (
                "https://sentinels.copernicus.eu/documents/247904/1955685/"
                "S2A_OPER_GIP_TILPAR_MPC__20151209T095117_V20150622T000000"
                "_21000101T000000_B00.kml"
            ),
            driver="kml",
        )
    tile_list = gpd.sjoin(
        tiles_layer, aoi.to_crs(epsg=4326), how="inner", predicate="intersects"
    )["Name"].to_list()
    return [f"T{t}" for t in tile_list]


def _create_date_url(base_url, input_date):
    year = input_date.strftime("%Y")
    month = input_date.strftime("%m")
    day = input_date.strftime("%d")
    return f"{base_url}/{year}/{month}/{day}"


def _get_existing_folders(base_url, start_date, end_date):
    start_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_date = datetime.strptime(end_date, "%Y-%m-%d")
    current_date = start_date
    urls = []
    while current_date <= end_date:
        check_url = _create_date_url(base_url, current_date)
        response = requests.get(check_url, timeout=5)
        if response.status_code == 200:
            urls.append(check_url)
        current_date += timedelta(days=1)
    return urls


def extract_xml_links(url, tile_list=None):
    """
    Extracts XML file links from a specified HTML webpage URL.

    This function sends a GET request to the provided URL, parses
    the HTML content, and extracts all links that end with
    '.xml?download=1'.
    If a tile_list is provided, only links containing any of the
    tiles in the list are extracted.

    Args:
        url (str): The URL of the HTML webpage from which to extract XML
        file links.
        tile_list (list of str, optional): A list of specific tiles to
            filter the XML links. If None, all XML links are extracted.
            Defaults to None.

    Returns:
        set: A set of unique XML file links that meet the specified
            criteria.

    Raises:
        requests.exceptions.RequestException: If the request to the
        URL fails.
    """
    xml_links = []
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, "html.parser")

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".xml?download=1"):
                if isinstance(tile_list, list):
                    for t in tile_list:
                        if t in href:
                            xml_links.append(href)
                else:
                    xml_links.append(href)

    return set(xml_links)


def all_xml_list(base_url, start_date, end_date, tile_list=None):
    """
    Gathers all XML file links from a range of URLs constructed
    based on a base CEDA URL and a date range.

    This function generates URLs for each date between the start and
    end dates, inclusive. For each generated URL, it extracts XML file
    links. If a tile_list is provided, only links containing any of
    the specified tiles are included.

    Args:
        base_url (str): The base URL used to construct date-specific
        URLs.
        start_date (datetime.date): The starting date of the range.
        end_date (datetime.date): The ending date of the range.
        tile_list (list of str, optional): A list of specific tiles to
            filter the XML links. If None, all XML links are extracted.
            Defaults to None.

    Returns:
        list: A list of all extracted XML file links across the
            specified date range.
    """
    date_urls = _get_existing_folders(base_url, start_date, end_date)
    xml_links = []
    for url in date_urls:
        xml_links.extend(extract_xml_links(url, tile_list))
    return xml_links


def _extract_xml_cloud(xml_extract):
    supp = xml_extract.find("gmd:supplementalinformation")
    character_string = supp.find("gco:characterstring").text
    lines = character_string.split("\n")
    lines = ["".join(l.split()) for l in lines]
    for line in lines:
        if line.startswith("ARCSI_CLOUD_COVER"):
            arcsi_cloud_cover = line.split(":")[1].strip()
            val = arcsi_cloud_cover
            break
    return float(val)


def _clean_coord(coord):
    coord = coord.replace("\n", "")
    return float(coord)


def _extract_extent(xml_extract):
    minx = _clean_coord(xml_extract.find("gmd:westboundlongitude").text)
    miny = _clean_coord(xml_extract.find("gmd:southboundlatitude").text)
    maxx = _clean_coord(xml_extract.find("gmd:eastboundlongitude").text)
    maxy = _clean_coord(xml_extract.find("gmd:northboundlatitude").text)
    return box(minx, miny, maxy, maxy)


def _read_xml(url):
    # Send an HTTP GET request to the URL
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        # Parse the XML content using BeautifulSoup with lxml parser
        soup = BeautifulSoup(response.text, "lxml")
    return soup


def filter_xmls_to_gdf(xml_links, cloud_cover_max=0.4):
    """
    Filters a list S2 ARD XML links based on cloud cover and creates a
    GeoDataFrame of corresponding image link and extent geometry.

    Links with cloud cover exceeding the specified maximum are
    discarded.

    Args:
        xml_links (list of str): List of links to CEDA ARD S2 images.
        cloud_cover_max (float, optional): Maximum acceptable cloud
            cover for retaining an image. 0 to 1 scale. Default 0.4.

    Returns:
        GeoDataFrame: A GeoDataFrame with 'image_links' for
            TIFF image URLs and 'geometry' of image extents.
    """
    retained_links = []
    retained_geom = []
    for url in xml_links:
        # read the xml
        try:
            xml_extract = _read_xml(url)
        except:
            continue
        # check if too cloudy overall
        if _extract_xml_cloud(xml_extract) > cloud_cover_max:
            continue

        # If not get extent geom and append to lists
        retained_geom.append(_extract_extent(xml_extract))
        retained_links.append(url)

    image_links = [
        x.replace("_meta.xml?download=1", ".tif") for x in retained_links
    ]

    return gpd.GeoDataFrame(
        {"image_links": image_links, "geometry": retained_geom},
        crs="epsg:4386",
    )


def image_links_to_aoi_gdf(aoi_gdf, xml_links):
    """Spatial join AOI polygons to corresponding CEDA images and
    add image download link as an attribute.

    Args:
        aoi_gdf (GeoDataFrame): Geodataframe with AOI geometries.
        xml_links (list of str): List of links to CEDA S2 ARD XML.

    Returns:
        GeoDataFrame: GeoDataFrame of AOI polygons with corresponding
        S2 ARD image links. If no suitable images link column will
        be NULL. If multiple matching images AOI polygons are duplicated
        for each matching image URL.
    """
    filtered_image_gdf = filter_xmls_to_gdf(xml_links)
    return gpd.sjoin(
        aoi_gdf,
        filtered_image_gdf.to_crs(epsg=27700),
        how="left",
        predicate="intersects",
    ).reset_index()


def find_image_links(aoi_gdf, start_date, end_date, base_url):
    tile_list = filter_sentinel2_tiles(aoi_gdf)
    xml_links = all_xml_list(base_url, start_date, end_date, tile_list)
    return image_links_to_aoi_gdf(aoi_gdf, xml_links)
