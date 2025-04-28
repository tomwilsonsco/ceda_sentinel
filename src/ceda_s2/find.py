import logging
import requests
from requests.exceptions import ReadTimeout
from bs4 import BeautifulSoup
import time
import random
from datetime import datetime, timedelta
from shapely.geometry import Polygon, MultiPolygon, box
from fiona.drvsupport import supported_drivers
import geopandas as gpd
import pandas as pd
import rasterio as rio
from rasterio.windows import from_bounds
import numpy as np
import re


class FindS2:
    """
    Class for filtering Sentinel-2 satellite tiles and extracting image metadata based on an Area of Interest (AOI).

    Attributes:
        aoi (GeoDataFrame): Area of Interest (AOI) as a GeoDataFrame.
        start_date (str): Start date for searching imagery, in "YYYY-MM-DD" format.
        end_date (str): End date for searching imagery, in "YYYY-MM-DD" format.
        base_url (str): Base URL used for constructing the URLs to search.
        cloud_cover_max (float): Maximum acceptable cloud cover (0.0 to 1.0).
        tile_list (list of str): List of Sentinel-2 tiles intersecting the AOI.
    """

    def __init__(
        self,
        aoi_gdf,
        start_date,
        end_date,
        id_col="id",
        base_url="https://data.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_2",
        check_img_cloud=False,
        tile_cloud_max=20,
        s2cloudless_max=10,
        nodata_max=10,
        tile_gdf=None,
        tile_list=None,
        min_cloud_only=False,
    ):
        """
        Initializes the FindS2 class with the given parameters.

        Args:
            aoi_gdf (GeoDataFrame): Area of Interest as a GeoDataFrame.
            start_date (str): Start date for the imagery search in "YYYY-MM-DD" format.
            end_date (str): End date for the imagery search in "YYYY-MM-DD" format.
            id_col (str): Column name containing unique IDs in AOI GeoDataFrame.
            base_url (str): Base URL for Sentinel-2 data.
            check_img_cloud (bool): Whether to check image cloud cover from image tile metadata.
            tile_cloud_max (float): Maximum allowable cloud cover percentage from image tile metadata.
            s2cloudless_max (float): Maximum allowable cloud cover percentage using S2 Cloudless filter within each aoi feature.
            nodata_max (float): Maximum allowable nodata percentage within aoi.
            tile_gdf (GeoDataFrame): GeoDataFrame for Sentinel-2 tiles.
            tile_list (list): List of Sentinel-2 tiles intersecting the AOI.
            min_cloud_only (bool): If True, only the image with the minimum cloud cover percentage is kept for each feature.
        """
        self.aoi = aoi_gdf
        self.start_date = start_date
        self.end_date = end_date
        self.id_col = id_col
        self.base_url = base_url
        self.check_img_cloud = check_img_cloud
        self.tile_cloud_max = tile_cloud_max
        self.s2cloudless_max = s2cloudless_max
        self.nodata_max = nodata_max
        self.tile_gdf = tile_gdf
        self.tile_list = tile_list
        self.min_cloud_only = min_cloud_only

        logging.basicConfig(
            level=logging.INFO,
            format="\n%(asctime)s.%(msecs)03d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.FileHandler("image_search.log", mode="w"),
                logging.StreamHandler(),
            ],
        )
        self.__logger = logging.getLogger(__name__)

    def _filter_sentinel2_tiles(self):
        """
        Filters Sentinel-2 satellite tiles based on the given AOI.

        Spatial joins the input AOI with a layer of Sentinel-2 tiles.
        The default tile layer is an online ESA KML file.

        Returns:
            None: Updates `self.tile_gdf` with the intersecting tiles and `self.tile_list` with the tile names.
        """
        try:
            supported_drivers["KML"] = "rw"
            tiles_layer = gpd.read_file(
                (
                    "https://sentinels.copernicus.eu/documents/247904/1955685/"
                    "S2A_OPER_GIP_TILPAR_MPC__20151209T095117_V20150622T000000"
                    "_21000101T000000_B00.kml"
                ),
                driver="kml",
            )
            self.tile_gdf = gpd.sjoin(
                tiles_layer, self.aoi.to_crs(epsg=4326), how="inner"
            ).to_crs(epsg=27700)
            self.tile_list = self.tile_gdf["Name"].to_list()
        except Exception as e:
            self.__logger.error(f"Cannot read tiles reference layer: {e}")

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
        # Check if all geometries are of type Polygon
        if not all(isinstance(geom, (Polygon, MultiPolygon)) for geom in self.aoi.geometry):
            raise ValueError("AOI must be of geometry type Polygon.")

        # Check CRS and reproject if necessary
        if self.aoi.crs.to_epsg() != 27700:
            self.__logger.info("Reprojecting AOI layer to EPSG:27700...")
            self.aoi = self.aoi.to_crs(epsg=27700)

        return self.aoi

    def _filter_tiles_feature(self, gdf_row):
        """
        Filters Sentinel-2 tiles based on the given AOI feature and returns the Name column values.

        Args:
            gdf_row (GeoDataFrame row): A row from the AOI GeoDataFrame.

        Returns:
            list: List of Name column values where the tile intersects the AOI feature.
        """
        intersecting_tiles = self.tile_gdf[self.tile_gdf.intersects(gdf_row.geometry)]
        return intersecting_tiles["Name"].tolist()

    def _create_date_url(self, input_date):
        """
        Creates a URL for a specific date by appending the year, month, and day to the base URL.

        Args:
            input_date (datetime): The date for which the URL is being generated.

        Returns:
            str: The generated URL for the given date.
        """
        year = input_date.strftime("%Y")
        month = input_date.strftime("%m")
        day = input_date.strftime("%d")
        return f"{self.base_url}/{year}/{month}/{day}"

    def _get_existing_folders(self):
        """
        Retrieves URLs for dates that have existing data folders available based on a date range.

        Constructs URLs for each date between the start and end dates and checks for their availability.

        Returns:
            list: A list of URLs for which data folders are available.
        """
        start_date = datetime.strptime(self.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(self.end_date, "%Y-%m-%d")
        date_range = (
            start_date + timedelta(days=i)
            for i in range((end_date - start_date).days + 1)
        )
        urls = []
        for current_date in date_range:
            check_url = self._create_date_url(current_date)
            try:
                response = requests.head(check_url, timeout=10)
                if response.status_code == 200:
                    urls.append(check_url)
            except ReadTimeout:
                self.__logger.error(
                    f"Request timed out for {check_url}. \nSkipping this date..."
                )
        return urls

    def _extract_links(self, url):
        """
        Extracts tif file links from a specified HTML webpage URL.

        Sends a GET request to the provided URL, parses the HTML content, and extracts all
        links that end with '.tif'.
        If `self.tile_list`, only extracts links containing specified tiles.

        Args:
            url (str): The URL of the HTML webpage to extract tif links from.

        Returns:
            set: A set of unique tif file links that meet the specified criteria.
        """
        img_links = []
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")

            for link in soup.find_all("a", href=True):
                href = link["href"]
                if href.endswith("stdsref.tif?download=1"):
                    if self.tile_list:
                        for t in self.tile_list:
                            if t in href:
                                img_links.append(href.replace("?download=1", ""))
                    else:
                        img_links.append(href)

        return set(img_links)

    def all_img_list(self):
        """
        Gathers all tif file links from URLs constructed based from base CEDA URL and a date range.

        Extracts tif image links from each generated URL within the date range.
        Filters links based on provided tiles if available.

        Returns:
            list: A list of all extracted tif image file links across the specified date range.
        """
        date_urls = self._get_existing_folders()
        img_links = []
        for url in date_urls:
            img_links.extend(self._extract_links(url))
            time.sleep(random.uniform(0.01, 0.1))
        return img_links

    def _extract_xml_cloud(self, xml_extract):
        """
        Extracts cloud cover percentage from XML metadata associated with Sentinel 2 image.

        Args:
            xml_extract (BeautifulSoup): Parsed XML metadata using BeautifulSoup.

        Returns:
            float: The cloud cover percentage extracted from the XML.
        """
        try:
            supp = xml_extract.find("gmd:supplementalinformation")
            character_string = supp.find("gco:characterstring").text
            lines = character_string.split("\n")
            lines = ["".join(aline.split()) for aline in lines]
            for line in lines:
                if line.startswith("ARCSI_CLOUD_COVER"):
                    arcsi_cloud_cover = line.split(":")[1].strip()
                    val = arcsi_cloud_cover
                    return float(val)
            raise ValueError("ARCSI_CLOUD_COVER not found in the XML metadata")
        except Exception as e:
            self.__logger.error(f"Error extracting ARCSI_CLOUD_COVER: {e}")
            return None

    def _read_xml(self, url):
        """
        Reads and parses XML data from a given URL.

        Args:
            url (str): The URL pointing to the XML file.

        Returns:
            BeautifulSoup: Parsed XML data.
        """
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return BeautifulSoup(response.text, "lxml")
            else:
                self.__logger.error(
                    f"Error: Received status code {response.status_code} for {url}"
                )
        except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
            self.__logger.info(f"Error reading XML from {url}: {e}")
        return None

    def _img_bounds_filter(self, gdf_row, image_link):
        """
        Checks whether the geometry in a GeoDataFrame row intersects image bounds.
        Args:
            gdf_row (GeoSeries): A row from a GeoDataFrame with a geometry.
            image_link (str): Path to the raster image file (can be URL or file path).
        Returns:
            bool: True if the geometry in `gdf_row` intersects with the image bounds, False otherwise.
        """
        try:
            with rio.open(image_link) as src:
                image_bounds = src.bounds
            image_geom = box(*image_bounds)
            return gdf_row.geometry.intersects(image_geom)
        except Exception as e:
            self.__logger.error(f"Cannot open image {e}")
            return False

    def _no_data_filter(self, gdf_row, image_link):
        """
        Filters out images with too much nodata based on the specified percentage threshold.

        Args:
            gdf_row (GeoDataFrame row): Row of the GeoDataFrame representing an image.
            image_link (str): Path to the raster image file (can be URL or file path).
        Returns:
            bool: True if the nodata percentage exceeds the threshold, False otherwise.
        """
        minx, miny, maxx, maxy = gdf_row.geometry.bounds
        try:
            with rio.open(image_link) as src:
                nodata = src.profile["nodata"]
                window = from_bounds(minx, miny, maxx, maxy, src.transform)
                window_data = src.read(1, window=window)
                window_size = window_data.shape[0] * window_data.shape[1]
                nodata_total = np.sum(window_data == nodata)
                return nodata_total / window_size * 100 < self.nodata_max
        except Exception as e:
            self.__logger.error(f"Cannot open image {e}")
            return False

    def _s2_cloudless_filter(self, gdf_row, image_link):
        """
        Filters out images with too much cloud cover based on the S2 cloudless product.

        Args:
            gdf_row (GeoDataFrame row): Row of the GeoDataFrame representing an image.
            image_link (str): Path to the raster image file (can be URL or file path).
        Returns:
            bool: True if the cloud cover percentage exceeds the threshold, False otherwise.
        """
        image_link = image_link.replace(
            "vmsk_sharp_rad_srefdem_stdsref.tif", "clouds.tif"
        )
        minx, miny, maxx, maxy = gdf_row.geometry.bounds
        try:
            with rio.open(image_link) as src:
                window = from_bounds(minx, miny, maxx, maxy, src.transform)
                window_data = src.read(1, window=window)
                window_size = window_data.shape[0] * window_data.shape[1]
                cloud_issues = np.sum((window_data == 1) | (window_data == 2))
                cloud_percent = cloud_issues / window_size * 100
                if cloud_percent < self.s2cloudless_max:
                    return cloud_percent
                else:
                    return False

        except Exception as e:
            self.__logger.error(f"Cannot open cloud mask image {e}")
            return False

    def _extract_date_from_link(self, image_link):
        """
        Extracts a date string from the given file name.

        Args:
            image_link (str): Path to the raster image file (can be URL or file path).

        Returns:
            str: The formatted date string (YYYY-MM-DD) if found, otherwise None.
        """

        file_name = image_link.split("/")[-1]
        try:
            date_str = re.search(r"_(\d{8})_", file_name).group(1)
            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            return formatted_date
        except Exception as e:
            self.__logger.error(f"Error extracting date from {file_name}: {e}")
            return None

    def _filter_overall_cloud(self, image_link):
        """
        Checks XML metadata overall cloudy pixel percentage and returns true if exceeds threshold.

        Args:
            image_link (str): Path to the raster image file (can be URL or file path).

        Returns:
            bool: True if the overall cloud cover percentage exceeds the threshold, False otherwise.
        """
        if self.check_img_cloud:
            xml_url = image_link.replace(".tif", "_meta.xml?download=1")
            xml_extract = self._read_xml(xml_url)
            xml_cloud_percent = self._extract_xml_cloud(xml_extract) * 100
            self.__logger.info(
                f"{image_link.split("/")[-1]}:\nCloud cover percentage: {xml_cloud_percent}"
            )
            overall_check = xml_cloud_percent <= self.tile_cloud_max
            return overall_check
        else:
            return True

    def _overall_cloud_check_all(self, image_links):
        """
        Filters a list of image links based on overall cloud cover percentage.

        Checks the XML metadata of each image using _filter_overall_cloud.

        Args:
            image_links (list): A list of paths to raster image files (can be URLs or file paths).

        Returns:
            list: A list of image links where the overall cloud cover percentage exceeds the threshold.
        """
        return [i for i in image_links if self._filter_overall_cloud(i)]

    def _validate_feature_image(self, row, image_link):
        """
        Validates an image based on various filters.

        Args:
            row (GeoDataFrame row): A row from the AOI GeoDataFrame.
            image_link (str): Image link.

        Returns:
            bool: True if the image passes all filters, False otherwise.
        """
        if not self._img_bounds_filter(row, image_link):
            self.__logger.info("Bounds check failed - out of bounds")
            return False
        if not self._no_data_filter(row, image_link):
            self.__logger.info(f"No data check failed - too much no data")
            return False

        cloud_percent_feature = self._s2_cloudless_filter(row, image_link)
        if not cloud_percent_feature:
            self.__logger.info(f"S2Cloudless check failed - too cloudy")
            return False

        self.__logger.info(
            f"Image / feature passes all checks. s2cloudless percent {cloud_percent_feature}"
        )
        return int(cloud_percent_feature)

    def _find_images_per_feature(self, image_links):
        """
        Finds suitable images for each feature in the area of interest (AOI).

        This method iterates over each feature in the AOI and filters the provided image links
        to find images that intersect with the feature's tiles. It then validates each image
        for the feature.

        Args:
            image_links (list): A list of image URLs to be filtered and validated.

        Returns:
            list: A list of dictionaries, each containing:
                - 'id_col_name': The identifier of the feature. Key name is self.id_col.
                - 'image_link': The URL of the suitable image.
                - 'image_date': The date extracted from the image link.

        """
        self.__logger.info("Looking for suitable images per feature...")
        result_list = []
        for _, aoi_feature in self.aoi.iterrows():
            current_id = aoi_feature[self.id_col]
            self.__logger.info(f"Checking images for feature {current_id}...")
            try:
                # tiles that intersect the feature
                tiles_filtered = self._filter_tiles_feature(aoi_feature)
                # images for those tiles
                img_links_filtered = [
                    i for i in image_links if any(t in i for t in tiles_filtered)
                ]
            except Exception as e:
                self.__logger.error(
                    f"Error filtering tiles for feature {current_id}: {e}"
                )
                img_links_filtered = image_links
            for img_link in img_links_filtered:
                self.__logger.info(
                    f"Checking {img_link.split('/')[-1]} for feature {current_id}..."
                )
                valid_cloud_percent = self._validate_feature_image(
                    aoi_feature, img_link
                )
                if valid_cloud_percent:
                    row_dict = {
                        self.id_col: current_id,
                        "image_link": img_link,
                        "image_date": self._extract_date_from_link(img_link),
                        "s2cloudles": valid_cloud_percent,
                    }
                    result_list.append(row_dict)
        return result_list

    def _results_to_gdf(self, result_list):
        """
        Merges a list of result dictionaries into aoi GeoDataFrame.

        The resulting geodataframe has all input aoi columns plus image_link and image_date
        columns found from the Sentinel 2 image search. If multiple images are found for a feature,
        the geodataframe will have multiple rows for that feature / id.

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
        self.__logger.info("Filtering S2 tiles...")
        self._filter_sentinel2_tiles()
        self.__logger.info(f"Intersecting tiles: {self.tile_list}")
        self.__logger.info("Extracting image links...")
        img_links = self.all_img_list()
        self.__logger.info(f"{len(img_links)} available images")
        if self.check_img_cloud:
            img_links = self._overall_cloud_check_all(img_links)
            self.__logger.info(
                f"filtered to {len(img_links)} images based on overall cloud cover"
            )

        result_list = self._find_images_per_feature(img_links)

        if not result_list:
            self.__logger.warning("Found no suitable images.")
            return None

        output_gdf = self._results_to_gdf(result_list)
        return output_gdf
