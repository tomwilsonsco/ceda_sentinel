"""
Shared CEDA STAC API client utilities.

This module provides constants and utility functions for interacting with
the CEDA STAC API (https://api.stac.ceda.ac.uk/).
"""
from pystac_client import Client

# API endpoint
CEDA_STAC_API_URL = "https://api.stac.ceda.ac.uk/"

# Collection IDs
S1_ARD_COLLECTION = "sentinel1_ard"
S2_ARD_COLLECTION = "sentinel2_ard"

# Sentinel-1 asset keys
S1_DATA_ASSET = "data"
S1_METADATA_ASSET = "metadata"

# Sentinel-2 asset keys
S2_COG_ASSET = "cog"
S2_CLOUD_ASSET = "cloud"
S2_CLOUD_PROBABILITY_ASSET = "cloud_probability"
S2_METADATA_ASSET = "metadata"
S2_THUMBNAIL_ASSET = "thumbnail"
S2_SATURATED_PIXELS_ASSET = "saturated_pixels"
S2_TOPOGRAPHIC_SHADOW_ASSET = "topographic_shadow"
S2_VALID_PIXELS_ASSET = "valid_pixels"


def get_stac_client(url=CEDA_STAC_API_URL):
    """
    Opens and returns a pystac-client Client for the CEDA STAC API.

    Args:
        url (str): STAC API endpoint URL. Defaults to CEDA_STAC_API_URL.

    Returns:
        Client: A pystac-client Client instance.

    Raises:
        Exception: If the client cannot connect to the STAC API.
    """
    try:
        client = Client.open(url)
        return client
    except Exception as e:
        raise Exception(f"Failed to connect to STAC API at {url}: {e}")


def format_datetime_range(start_date, end_date):
    """
    Formats date strings into RFC 3339 datetime range for STAC API.

    Args:
        start_date (str): Start date in 'YYYY-MM-DD' format.
        end_date (str): End date in 'YYYY-MM-DD' format.

    Returns:
        str: RFC 3339 formatted datetime range 'YYYY-MM-DDTHH:MM:SSZ/YYYY-MM-DDTHH:MM:SSZ'

    Example:
        >>> format_datetime_range("2024-06-01", "2024-06-30")
        '2024-06-01T00:00:00Z/2024-06-30T23:59:59Z'
    """
    return f"{start_date}T00:00:00Z/{end_date}T23:59:59Z"


def is_gb_osgb_item(item):
    """
    Checks if a STAC item contains GB_OSGB (British National Grid) data.

    This function checks the asset href for 'GB_OSGB' in the filename,
    which indicates the data is in the British National Grid projection.

    Args:
        item: A pystac.Item object.

    Returns:
        bool: True if the item contains GB_OSGB data, False otherwise.
    """
    # Check the data asset href for GB_OSGB
    if S1_DATA_ASSET in item.assets:
        href = item.assets[S1_DATA_ASSET].href
        return "GB_OSGB" in href

    # For S2 items, check the cog asset
    if S2_COG_ASSET in item.assets:
        href = item.assets[S2_COG_ASSET].href
        return "GB_OSGB" in href or "osgb" in href.lower()

    return False


def extract_image_url_from_item(item, asset_key=S1_DATA_ASSET):
    """
    Extracts the COG image URL from a STAC item.

    Args:
        item: A pystac.Item object.
        asset_key (str): The asset key to extract the URL from.
                        Defaults to S1_DATA_ASSET.

    Returns:
        str or None: The image URL if the asset exists, None otherwise.
    """
    if asset_key in item.assets:
        return item.assets[asset_key].href
    return None


def extract_cloud_url_from_item(item):
    """
    Extracts the cloud mask URL from a Sentinel-2 STAC item.

    Args:
        item: A pystac.Item object.

    Returns:
        str or None: The cloud mask URL if the asset exists, None otherwise.
    """
    return extract_image_url_from_item(item, S2_CLOUD_ASSET)


def extract_date_from_item(item):
    """
    Extracts the date string from a STAC item's datetime property.

    Args:
        item: A pystac.Item object.

    Returns:
        str or None: Date string in 'YYYY-MM-DD' format, or None if not available.
    """
    if "datetime" in item.properties:
        datetime_str = item.properties["datetime"]
        # Extract date part from ISO format datetime (e.g., "2024-06-02T18:16:37Z")
        return datetime_str.split("T")[0]
    return None


def extract_tile_from_item_id(item_id):
    """
    Extracts MGRS tile ID from a STAC item ID.

    This is a fallback method when the 'tile' property is not populated
    in the STAC item properties.

    Example item ID:
        neodc.sentinel_ard.data.sentinel_2.2024.06.24.S2A_20240624_latn554lonw0006_T30UXG_ORB137_...

    Args:
        item_id (str): The STAC item ID string.

    Returns:
        str or None: The MGRS tile ID (e.g., 'T30UXG') or None if not found.
    """
    import re
    match = re.search(r'_(T\d{2}[A-Z]{3})_', item_id)
    if match:
        return match.group(1)
    return None