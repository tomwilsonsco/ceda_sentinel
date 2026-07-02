"""
Sentinel-1 STAC API search implementation.

This module provides FindS1STAC class that uses the CEDA STAC API
for searching Sentinel-1 ARD data instead of HTML directory scraping.
"""
import logging
from datetime import datetime
import geopandas as gpd
import numpy as np
from shapely.geometry import shape, box
from tqdm import tqdm

from ceda_stac.client import (
    get_stac_client,
    format_datetime_range,
    is_gb_osgb_item,
    extract_image_url_from_item,
    S1_ARD_COLLECTION,
    S1_DATA_ASSET,
)


class FindS1STAC:
    """
    Searches for Sentinel-1 ARD data using the CEDA STAC API.

    Provides the same interface as FindS1 but with server-side filtering
    via the STAC API. Recommended for recent data (2024+).
    """

    def __init__(
        self,
        start_date,
        end_date,
        aoi_filepath,
        orbit_numbers=[52, 59, 74, 81, 103, 96, 125, 132, 161, 154, 1, 8, 30, 23],
        aoi_id="OBJECTID",
        max_no_data_patch=10,
        stac_url="https://api.stac.ceda.ac.uk/",
        platform=None,
        orbit_state=None,
    ):
        """
        Initializes the FindS1STAC class.

        Args:
            start_date (str): The start date for the search in the format 'YYYY-MM-DD'.
            end_date (str): The end date for the search in the format 'YYYY-MM-DD'.
            aoi_filepath (str): The filepath to shapefile, geojson or geopackage for area of interest.
            aoi_id (str): The column name in the AOI file to use as the unique ID for search results.
            orbit_numbers (list): A list of relative orbit numbers to filter results by.
            max_no_data_patch (int): If a continuous region of no data pixels is larger than this value, the image is discarded.
            stac_url (str): The CEDA STAC API endpoint URL.
            platform (str, optional): Filter by platform (e.g., 'sentinel-1a', 'sentinel-1b', 'sentinel-1c').
            orbit_state (str, optional): Filter by orbit state ('asc' or 'desc').
        """
        self.start_date = start_date
        self.end_date = end_date
        self.orbit_numbers = orbit_numbers
        self.aoi_filepath = aoi_filepath
        self.aoi_id = aoi_id
        self.max_no_data_patch = max_no_data_patch
        self.stac_url = stac_url
        self.platform = platform
        self.orbit_state = orbit_state

        logging.basicConfig(
            level=logging.INFO,
            format="\n%(asctime)s.%(msecs)03d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.FileHandler("s1_image_search.log", mode="w"),
                logging.StreamHandler(),
            ],
        )
        self.__logger = logging.getLogger(__name__)

    def _read_aoi_file(self):
        """
        Reads the area of interest (AOI) file using geopandas.

        Returns:
            GeoDataFrame: The AOI data.
        """
        try:
            aoi_data = gpd.read_file(self.aoi_filepath)
            self.__logger.info(f"Read AOI file with {len(aoi_data)} features.")
            return aoi_data
        except Exception as e:
            self.__logger.error(f"Failed to read AOI file: {e}")
            raise

    def _build_orbit_filter(self):
        """
        Builds CQL2 filter for sat:relative_orbit property.

        Converts integer orbit numbers to strings as required by the STAC API.

        Returns:
            dict or None: CQL2 filter dict, or None if no orbit filtering needed.
        """
        if not self.orbit_numbers:
            return None

        return {
            "op": "in",
            "args": [
                {"property": "sat:relative_orbit"},
                [str(o) for o in self.orbit_numbers]
            ]
        }

    def _build_platform_filter(self):
        """
        Builds CQL2 filter for platform property.

        Returns:
            dict or None: CQL2 filter dict, or None if no platform filtering needed.
        """
        if not self.platform:
            return None

        return {
            "op": "=",
            "args": [
                {"property": "platform"},
                self.platform
            ]
        }

    def _build_orbit_state_filter(self):
        """
        Builds CQL2 filter for sat:orbit_state property.

        Returns:
            dict or None: CQL2 filter dict, or None if no orbit state filtering needed.
        """
        if not self.orbit_state:
            return None

        return {
            "op": "=",
            "args": [
                {"property": "sat:orbit_state"},
                self.orbit_state
            ]
        }

    def _build_combined_filter(self):
        """
        Builds combined CQL2 filter from all active filters.

        Returns:
            dict or None: Combined CQL2 filter dict, or None if no filters.
        """
        filters = []

        orbit_filter = self._build_orbit_filter()
        if orbit_filter:
            filters.append(orbit_filter)

        platform_filter = self._build_platform_filter()
        if platform_filter:
            filters.append(platform_filter)

        orbit_state_filter = self._build_orbit_state_filter()
        if orbit_state_filter:
            filters.append(orbit_state_filter)

        if not filters:
            return None

        if len(filters) == 1:
            return filters[0]

        return {"op": "and", "args": filters}

    def _search_stac(self):
        """
        Executes STAC API search with spatial, temporal, and property filters.

        Returns:
            list: List of pystac.Item objects matching the search criteria.
        """
        client = get_stac_client(self.stac_url)
        aoi_gdf = self._read_aoi_file()

        # Get AOI bounds in EPSG:4326 for STAC search
        aoi_wgs84 = aoi_gdf.to_crs(epsg=4326)
        bbox = list(aoi_wgs84.total_bounds)

        datetime_range = format_datetime_range(self.start_date, self.end_date)

        # Build combined filter
        cql2_filter = self._build_combined_filter()

        self.__logger.info(
            f"Searching STAC API for S1 ARD data from {self.start_date} to {self.end_date}"
        )
        self.__logger.info(f"AOI bbox (WGS84): {bbox}")
        if cql2_filter:
            self.__logger.info(f"Applying filters: {cql2_filter}")

        search = client.search(
            collections=[S1_ARD_COLLECTION],
            bbox=bbox,
            datetime=datetime_range,
            filter=cql2_filter,
        )

        items = list(search.items())
        self.__logger.info(f"STAC search returned {len(items)} items")

        # Filter for GB_OSGB (UK grid) items
        gb_osgb_items = [item for item in items if is_gb_osgb_item(item)]
        self.__logger.info(
            f"Filtered to {len(gb_osgb_items)} GB_OSGB items from {len(items)} total"
        )

        return gb_osgb_items

    def _aoi_check_images(self, items):
        """
        Checks which AOI features fall within each STAC item's geometry.

        Uses item geometry instead of opening COGs — major performance improvement
        over the HTML scraping approach.

        Args:
            items (list): List of pystac.Item objects.

        Returns:
            dict: Dictionary mapping feature IDs to lists of image URLs.
        """
        aoi_gdf = self._read_aoi_file()
        retained_images = {int(uid): [] for uid in aoi_gdf[self.aoi_id].unique()}
        orbits = []

        for item in tqdm(items, desc="Checking aoi intersection of images"):
            # Extract orbit number for logging
            if "sat:relative_orbit" in item.properties:
                orbit = item.properties["sat:relative_orbit"]
                if orbit not in orbits:
                    orbits.append(orbit)

            # Use item geometry for intersection check
            try:
                item_geom = shape(item.geometry)
            except Exception as e:
                self.__logger.error(
                    f"Error reading geometry for item {item.id}: {e}"
                )
                continue

            intersect_aoi = aoi_gdf[aoi_gdf.within(item_geom)]
            if intersect_aoi.empty:
                continue

            # Extract image URL from STAC asset
            img_link = extract_image_url_from_item(item, S1_DATA_ASSET)
            if not img_link:
                self.__logger.warning(
                    f"No data asset found for item {item.id}"
                )
                continue

            ids = intersect_aoi[self.aoi_id].astype("uint16").to_list()
            for id in ids:
                current = retained_images[id]
                current.append(img_link)
                retained_images[id] = current

        if orbits:
            self.__logger.info(
                f"Found images for relative orbits {' '.join(orbits)}"
            )
        return retained_images

    def get_img_feature_dict(self):
        """
        Searches for Sentinel-1 ARD images using the STAC API and filters by AOI.

        Returns:
            tuple: (aoi_img_dict, img_links)
                - aoi_img_dict: dict mapping feature IDs to lists of image URLs
                - img_links: sorted list of all unique image URLs
        """
        self.__logger.info(
            f"Searching for images between {self.start_date} and {self.end_date}"
        )

        # Execute STAC search
        items = self._search_stac()

        if not items:
            self.__logger.warning(
                "No STAC items found. This may indicate that data for the specified "
                "date range is not yet indexed in the STAC API. Consider using the "
                "HTML scraping approach (without --use-stac flag) for historical data."
            )

        # Check AOI intersection using item geometries
        aoi_img_dict = self._aoi_check_images(items)

        # Create flat list of all image links
        img_links = []
        for links in aoi_img_dict.values():
            img_links.extend(links)
        img_links = sorted(list(set(img_links)))

        self.__logger.info(
            f"Returning image search results for {len(aoi_img_dict.keys())} features."
        )
        self.__logger.info(f"Total unique image links: {len(img_links)}")

        return aoi_img_dict, img_links