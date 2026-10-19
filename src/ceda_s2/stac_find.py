"""
Sentinel-2 STAC API search implementation.

This module provides FindS2STAC class that uses the CEDA STAC API
for searching Sentinel-2 ARD data instead of HTML directory scraping.
"""

import logging

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio as rio
from rasterio.windows import from_bounds
from shapely.geometry import shape

from ceda_s2.exceptions import ImageReadError
from ceda_stac.client import (
    S2_ARD_COLLECTION,
    S2_COG_ASSET,
    extract_cloud_url_from_item,
    extract_date_from_item,
    extract_image_url_from_item,
    extract_tile_from_item_id,
    format_datetime_range,
    get_stac_client,
)


class FindS2STAC:
    """
    Searches for Sentinel-2 ARD data using the CEDA STAC API.

    Provides the same interface as FindS2 but with server-side filtering
    via the STAC API. Recommended for recent data.
    """

    def __init__(
        self,
        aoi_gdf,
        start_date,
        end_date,
        id_col="id",
        check_img_cloud=False,
        tile_cloud_max=20,
        s2cloudless_max=10,
        nodata_max=10,
        tile_gdf=None,
        tile_list=None,
        min_cloud_only=False,
        stac_url="https://api.stac.ceda.ac.uk/",
        check_buffer=0,
        client=None,
    ):
        """
        Initializes the FindS2STAC class.

        Args:
            aoi_gdf (GeoDataFrame): Area of Interest as a GeoDataFrame.
            start_date (str): Start date for the imagery search in "YYYY-MM-DD" format.
            end_date (str): End date for the imagery search in "YYYY-MM-DD" format.
            id_col (str): Column name containing unique IDs in AOI GeoDataFrame.
            check_img_cloud (bool): Whether to check image cloud cover from metadata.
            tile_cloud_max (float): Maximum allowable cloud cover percentage from tile metadata.
            s2cloudless_max (float): Maximum allowable cloud cover percentage using S2 Cloudless filter.
            nodata_max (float): Maximum allowable nodata percentage within aoi.
            tile_gdf (GeoDataFrame): GeoDataFrame for Sentinel-2 tiles (not used in STAC mode).
            tile_list (list): List of Sentinel-2 tiles intersecting the AOI.
            min_cloud_only (bool): If True, only the image with minimum cloud cover is kept per feature.
            stac_url (str): The CEDA STAC API endpoint URL.
            check_buffer (float): Distance in metres to buffer each feature by for the
                nodata and cloud checks. Useful for small features covering only a few
                pixels.
            client (pystac_client.Client, optional): An open STAC client to reuse,
                for example across searches in a long-running app. If None, a new
                client is opened from stac_url for each search.
        """
        self.aoi = aoi_gdf.copy()
        self.start_date = start_date
        self.end_date = end_date
        self.id_col = id_col
        self.check_img_cloud = check_img_cloud
        self.tile_cloud_max = tile_cloud_max
        self.s2cloudless_max = s2cloudless_max
        self.nodata_max = nodata_max
        self.tile_gdf = tile_gdf
        self.tile_list = tile_list
        self.min_cloud_only = min_cloud_only
        self.stac_url = stac_url
        self.check_buffer = check_buffer
        self.client = client
        self.read_errors = []

        self.__logger = logging.getLogger(__name__)

    def _check_id_column(self):
        """
        Ensures that the GeoDataFrame `self.aoi` has a column named `self.id_col`.
        If the column does not exist, it adds the column and populates it with row index integers.

        Returns:
            None
        """
        if self.id_col not in self.aoi.columns:
            self.aoi[self.id_col] = self.aoi.index

    def _check_and_reproject_aoi(self):
        """
        Checks if the AOI is of geometry type Polygon and if its CRS is EPSG:27700 (BNG).
        Fails if the AOI is not a Polygon.
        Reprojected if CRS is not EPSG:27700.

        Returns:
            GeoDataFrame: The AOI GeoDataFrame, reprojected to EPSG:27700 if necessary.
        """
        from shapely.geometry import MultiPolygon, Polygon

        # Check if all geometries are of type Polygon
        if not all(
            isinstance(geom, (Polygon, MultiPolygon)) for geom in self.aoi.geometry
        ):
            raise ValueError("AOI must be of geometry type Polygon.")

        # Check CRS and reproject if necessary
        if self.aoi.crs.to_epsg() != 27700:
            self.__logger.info("Reprojecting AOI layer to EPSG:27700...")
            self.aoi = self.aoi.to_crs(epsg=27700)

        return self.aoi

    def _get_aoi_bbox(self):
        """
        Gets AOI bounds in EPSG:4326 for STAC search.

        Returns:
            list: Bounding box [west, south, east, north] in EPSG:4326.
        """
        aoi_wgs84 = self.aoi.to_crs(epsg=4326)
        return list(aoi_wgs84.total_bounds)

    def _build_cloud_filter(self):
        """
        Builds CQL2 filter for eo:cloud_cover property.

        Returns:
            dict or None: CQL2 filter dict, or None if no cloud filtering needed.
        """
        if self.tile_cloud_max < 100:
            return {
                "op": "<=",
                "args": [{"property": "eo:cloud_cover"}, self.tile_cloud_max],
            }
        return None

    def _build_tile_filter(self):
        """
        Builds CQL2 filter for tile property if tile_list is provided.

        Returns:
            dict or None: CQL2 filter dict, or None if no tile filtering needed.
        """
        if not self.tile_list:
            return None

        # Note: The 'tile' property may not be reliably populated in the STAC API
        # This filter may not work as expected
        return {"op": "in", "args": [{"property": "tile"}, self.tile_list]}

    def _build_combined_filter(self):
        """
        Builds combined CQL2 filter from all active filters.

        Returns:
            dict or None: Combined CQL2 filter dict, or None if no filters.
        """
        filters = []

        cloud_filter = self._build_cloud_filter()
        if cloud_filter:
            filters.append(cloud_filter)

        tile_filter = self._build_tile_filter()
        if tile_filter:
            filters.append(tile_filter)

        if not filters:
            return None

        if len(filters) == 1:
            return filters[0]

        return {"op": "and", "args": filters}

    def _search_stac(self):
        """
        Executes STAC API search with spatial, temporal, cloud, and tile filters.

        Returns:
            list: List of pystac.Item objects matching the search criteria.
        """
        client = self.client or get_stac_client(self.stac_url)
        bbox = self._get_aoi_bbox()
        datetime_range = format_datetime_range(self.start_date, self.end_date)
        cql2_filter = self._build_combined_filter()

        self.__logger.info(
            f"Searching STAC API for S2 ARD data from {self.start_date} to {self.end_date}"
        )
        self.__logger.info(f"AOI bbox (WGS84): {bbox}")
        if cql2_filter:
            self.__logger.info(f"Applying filters: {cql2_filter}")

        search = client.search(
            collections=[S2_ARD_COLLECTION],
            bbox=bbox,
            datetime=datetime_range,
            filter=cql2_filter,
        )

        items = list(search.items())
        self.__logger.info(f"STAC search returned {len(items)} items")

        return items

    def _extract_tile_from_id(self, item_id):
        """
        Extracts MGRS tile ID from STAC item ID.

        Args:
            item_id (str): The STAC item ID string.

        Returns:
            str or None: The MGRS tile ID or None if not found.
        """
        return extract_tile_from_item_id(item_id)

    def _filter_items_by_tile(self, items):
        """
        Client-side tile filtering using item ID parsing.

        This is a fallback when the 'tile' property is not populated in STAC items.

        Args:
            items (list): List of pystac.Item objects.

        Returns:
            list: Filtered list of items matching the tile_list.
        """
        if not self.tile_list:
            return items

        filtered_items = []
        for item in items:
            # Try to get tile from item ID
            tile = self._extract_tile_from_id(item.id)
            if tile and tile in self.tile_list:
                filtered_items.append(item)
                continue

            # Try to get tile from properties
            if "tile" in item.properties and item.properties["tile"] in self.tile_list:
                filtered_items.append(item)

        self.__logger.info(
            f"Filtered to {len(filtered_items)} items matching tile list from {len(items)} total"
        )
        return filtered_items

    def _img_bounds_filter(self, gdf_row, item):
        """
        Checks whether the geometry in a GeoDataFrame row intersects item bounds.

        Converts the STAC item geometry to the AOI's CRS before performing
        the intersection check to ensure consistent coordinate systems.

        Args:
            gdf_row (GeoSeries): A row from a GeoDataFrame with a geometry.
            item: A pystac.Item object.

        Returns:
            bool: True if the geometry intersects with the item bounds, False otherwise.
        """
        try:
            item_geom = shape(item.geometry)
            # Convert item geometry to the AOI's CRS for accurate intersection
            item_geom_reprojected = (
                gpd.GeoSeries([item_geom], crs="EPSG:4326").to_crs(self.aoi.crs).iloc[0]
            )
            return gdf_row.geometry.intersects(item_geom_reprojected)
        except Exception as e:
            self.__logger.error(f"Cannot read item geometry: {e}")
            self._record_read_error(gdf_row, item.id, "bounds", e)
            return False

    def _check_bounds(self, gdf_row):
        """
        Returns the bounds used for the nodata and cloud checks of a feature.

        Args:
            gdf_row (GeoDataFrame row): The AOI feature being checked.

        Returns:
            tuple: (minx, miny, maxx, maxy) of the feature buffered by check_buffer.
        """
        minx, miny, maxx, maxy = gdf_row.geometry.bounds
        b = self.check_buffer
        return minx - b, miny - b, maxx + b, maxy + b

    def _no_data_filter(self, gdf_row, image_link):
        """
        Filters out images with too much nodata based on the specified percentage threshold.

        Any part of the feature that falls outside the image counts as nodata.

        Args:
            gdf_row (GeoDataFrame row): Row of the GeoDataFrame representing an image.
            image_link (str): Path to the raster image file (can be URL or file path).

        Returns:
            bool: True if the nodata percentage is below the threshold, False otherwise.
        """
        minx, miny, maxx, maxy = self._check_bounds(gdf_row)
        try:
            with rio.open(image_link) as src:
                nodata = src.profile["nodata"]
                window = from_bounds(minx, miny, maxx, maxy, src.transform)
                window_data = src.read(
                    1, window=window, boundless=True, fill_value=nodata
                )
                window_size = window_data.shape[0] * window_data.shape[1]
                nodata_total = np.sum(window_data == nodata)
                return nodata_total / window_size * 100 < self.nodata_max
        except Exception as e:
            self.__logger.error(f"Cannot open image {e}")
            self._record_read_error(gdf_row, image_link, "nodata", e)
            return False

    def _s2_cloudless_filter(self, gdf_row, item):
        """
        Filters out images with too much cloud cover based on the S2 cloudless product.

        Uses the cloud asset href from the STAC item instead of string replacement.
        The percentage is of the part of the feature inside the image; coverage is
        left to the nodata check.

        Args:
            gdf_row (GeoDataFrame row): Row of the GeoDataFrame representing an image.
            item: A pystac.Item object.

        Returns:
            float or None: Cloud percentage within the feature bounds, or None if
                the cloud mask cannot be read. The threshold is applied by the caller.
        """
        # Get cloud mask URL from STAC asset
        cloud_link = extract_cloud_url_from_item(item)
        if not cloud_link:
            self.__logger.warning(f"No cloud asset found for item {item.id}")
            return None

        minx, miny, maxx, maxy = self._check_bounds(gdf_row)
        try:
            with rio.open(cloud_link) as src:
                window = from_bounds(minx, miny, maxx, maxy, src.transform)
                window_data = src.read(1, window=window)
                window_size = window_data.shape[0] * window_data.shape[1]
                cloud_issues = np.sum((window_data == 1) | (window_data == 2))
                return float(cloud_issues / window_size * 100)
        except Exception as e:
            self.__logger.error(f"Cannot open cloud mask image {e}")
            self._record_read_error(gdf_row, cloud_link, "s2cloudless", e)
            return None

    def _record_read_error(self, gdf_row, image_link, check, error):
        """
        Records an image check that failed with an error rather than a result.

        Args:
            gdf_row (GeoDataFrame row): The AOI feature being checked.
            image_link (str): The image, cloud mask or item that could not be read.
            check (str): Name of the check that failed.
            error (Exception): The error raised.
        """
        self.read_errors.append(
            {
                "feature_id": gdf_row.get(self.id_col),
                "image_link": image_link,
                "check": check,
                "error": repr(error),
            }
        )

    def _extract_date_from_item(self, item):
        """
        Extracts date string from STAC item datetime property.

        Args:
            item: A pystac.Item object.

        Returns:
            str or None: Date string in YYYY-MM-DD format, or None if not available.
        """
        return extract_date_from_item(item)

    def _validate_feature_image(self, row, item):
        """
        Validates an image based on various filters.

        Args:
            row (GeoDataFrame row): A row from the AOI GeoDataFrame.
            item: A pystac.Item object.

        Returns:
            tuple: (passed, cloud_percent). passed is True if the image passes all
                filters. cloud_percent is the s2cloudless percentage as a float, or
                None if the cloud check was not reached or the mask could not be read.
        """
        image_link = extract_image_url_from_item(item, S2_COG_ASSET)
        if not image_link:
            return False, None

        if not self._img_bounds_filter(row, item):
            self.__logger.info("Bounds check failed - out of bounds")
            return False, None

        if not self._no_data_filter(row, image_link):
            self.__logger.info("No data check failed - too much no data")
            return False, None

        cloud_percent_feature = self._s2_cloudless_filter(row, item)
        if cloud_percent_feature is None:
            self.__logger.info("S2Cloudless check failed - cannot read cloud mask")
            return False, None
        if not cloud_percent_feature < self.s2cloudless_max:
            self.__logger.info("S2Cloudless check failed - too cloudy")
            return False, cloud_percent_feature

        self.__logger.info(
            f"Image / feature passes all checks. s2cloudless percent {cloud_percent_feature}"
        )
        return True, cloud_percent_feature

    def _find_images_per_feature(self, items):
        """
        Finds suitable images for each feature in the area of interest (AOI).

        Args:
            items (list): List of pystac.Item objects.

        Returns:
            list: A list of dictionaries containing feature ID, image link, date, and cloud cover.

        Raises:
            ImageReadError: If every image check failed with a read error. If only
                some failed, their errors are kept in `self.read_errors`.
        """
        self.__logger.info("Looking for suitable images per feature...")
        result_list = []
        self.read_errors = []
        checked = 0

        for _, aoi_feature in self.aoi.iterrows():
            current_id = aoi_feature[self.id_col]
            self.__logger.info(f"Checking images for feature {current_id}...")

            # If tile_list is provided, filter items by tile
            filtered_items = items
            if self.tile_list:
                filtered_items = self._filter_items_by_tile(items)

            for item in filtered_items:
                image_link = extract_image_url_from_item(item, S2_COG_ASSET)
                if not image_link:
                    continue

                self.__logger.info(
                    f"Checking {image_link.split('/')[-1]} for feature {current_id}..."
                )

                checked += 1
                passed, cloud_percent = self._validate_feature_image(aoi_feature, item)
                if passed:
                    row_dict = {
                        self.id_col: current_id,
                        "image_link": image_link,
                        "image_date": self._extract_date_from_item(item),
                        "s2cloudles": cloud_percent,
                    }
                    result_list.append(row_dict)

        if self.read_errors:
            if len(self.read_errors) == checked:
                raise ImageReadError(self.read_errors)
            self.__logger.warning(
                f"{len(self.read_errors)} of {checked} image checks failed with read "
                "errors; see read_errors for details."
            )

        return result_list

    def _results_to_gdf(self, result_list):
        """
        Merges a list of result dictionaries into aoi GeoDataFrame.

        Args:
            result_list (list): A list of results to be joined to aoi GeoDataFrame.

        Returns:
            GeoDataFrame: A processed GeoDataFrame.
        """
        results_df = pd.DataFrame(result_list)

        if hasattr(self, "min_cloud_only") and self.min_cloud_only:
            results_df = results_df.loc[
                results_df.groupby(self.id_col, dropna=False)["s2cloudles"].idxmin()
            ]

        # keep all image links rows or one row per feature if no images found
        output_gdf = self.aoi.merge(results_df, on=self.id_col, how="left")

        output_gdf = output_gdf.sort_values(
            by=[self.id_col, "image_date"], ascending=True
        )
        output_gdf = output_gdf.reset_index(drop=True)
        columns = list(self.aoi.columns) + ["image_link", "image_date", "s2cloudles"]
        return output_gdf[columns]

    def find_image_links(self):
        """
        Main method to find Sentinel-2 image links matching the given AOI, date range, and cloud cover criteria.

        Returns:
            GeoDataFrame: A GeoDataFrame with AOI polygons and corresponding Sentinel-2 image links.
        """
        self._check_id_column()
        self._check_and_reproject_aoi()
        self.__logger.info("Searching STAC API for S2 ARD data...")

        # Execute STAC search
        items = self._search_stac()

        if not items:
            self.__logger.warning(
                "No STAC items found. This may indicate that data for the specified "
                "date range is not yet indexed in the STAC API. Consider using the "
                "HTML scraping approach (without --use-stac flag) for historical data."
            )

        # Find suitable images per feature
        result_list = self._find_images_per_feature(items)

        if not result_list:
            self.__logger.warning("Found no suitable images.")
            return None

        output_gdf = self._results_to_gdf(result_list)
        return output_gdf
