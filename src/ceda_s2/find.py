from logging import WARNING
import requests
from requests.exceptions import ReadTimeout
from bs4 import BeautifulSoup
import time
import random
from datetime import datetime, timedelta
from shapely.geometry import box
from fiona.drvsupport import supported_drivers
import geopandas as gpd
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
        cloud_cover_max=20,
        s2cloudless_percent=10,
        nodata_percent=10,
    ):
        """
        Initializes the FindS2 class with the given parameters.

        Args:
            aoi_gdf (GeoDataFrame): Area of Interest as a GeoDataFrame.
            start_date (str): Start date for the imagery search in "YYYY-MM-DD" format.
            end_date (str): End date for the imagery search in "YYYY-MM-DD" format.
            id_col (str): Column name representing unique IDs in AOI GeoDataFrame.
            base_url (str): Base URL for Sentinel-2 data.
            cloud_cover_max (float): Maximum allowable cloud cover percentage.
            s2cloudless_percent (float): Maximum allowable cloud cover percentage for S2 cloudless filter.
            nodata_percent (float): Maximum allowable nodata percentage in an image.
        """
        self.aoi = aoi_gdf
        self.start_date = start_date
        self.end_date = end_date
        self.id_col = id_col
        self.base_url = base_url
        self.cloud_cover_max = cloud_cover_max
        self.s2cloudless_percent = s2cloudless_percent
        self.nodata_percent = nodata_percent
        self.tile_list = None

    def _filter_sentinel2_tiles(self):
        """
        Filters Sentinel-2 satellite tiles based on the given AOI.

        This function intersects the input AOI with a layer of Sentinel-2 tiles.
        The default layer is sourced from an ESA KML file.

        Returns:
            None: Updates `tile_list` with the names of intersecting tiles.
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
            self.tile_list = gpd.sjoin(
                tiles_layer, self.aoi.to_crs(epsg=4326), how="inner"
            )["Name"].to_list()
        except Exception as e:
            print(f"Cannot read tiles reference layer: {e}")

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
                print(f"Request timed out for {check_url}. \nSkipping this date...")
        return urls

    def _extract_xml_links(self, url):
        """
        Extracts XML file links from a specified HTML webpage URL.

        Sends a GET request to the provided URL, parses the HTML content, and extracts all
        links that end with '.xml?download=1'.
        If `tile_list` is available, only extracts links containing specified tiles.

        Args:
            url (str): The URL of the HTML webpage to extract XML links from.

        Returns:
            set: A set of unique XML file links that meet the specified criteria.
        """
        xml_links = []
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")

            for link in soup.find_all("a", href=True):
                href = link["href"]
                if href.endswith(".xml?download=1"):
                    if isinstance(self.tile_list, list):
                        for t in self.tile_list:
                            if t in href:
                                xml_links.append(href)
                    else:
                        xml_links.append(href)

        return set(xml_links)

    def all_xml_list(self):
        """
        Gathers all XML file links from a range of URLs constructed based on a
        base CEDA URL and a date range.

        Extracts XML links from each generated URL within the date range. Filters links based on provided
        tiles if available.

        Returns:
            list: A list of all extracted XML file links across the specified date range.
        """
        date_urls = self._get_existing_folders()
        xml_links = []
        for url in date_urls:
            xml_links.extend(self._extract_xml_links(url))
            time.sleep(random.uniform(0.01, 0.1))
        return xml_links

    @staticmethod
    def _extract_xml_cloud(xml_extract):
        """
        Extracts cloud cover percentage from the XML metadata.

        Args:
            xml_extract (BeautifulSoup): Parsed XML metadata using BeautifulSoup.

        Returns:
            float: The cloud cover percentage extracted from the XML.
        """
        supp = xml_extract.find("gmd:supplementalinformation")
        character_string = supp.find("gco:characterstring").text
        lines = character_string.split("\n")
        lines = ["".join(aline.split()) for aline in lines]
        for line in lines:
            if line.startswith("ARCSI_CLOUD_COVER"):
                arcsi_cloud_cover = line.split(":")[1].strip()
                val = arcsi_cloud_cover
                break
        return float(val)

    @staticmethod
    def _clean_coord(coord):
        """
        Cleans coordinate values by removing newline characters and converts them to float.

        Args:
            coord (str): Coordinate value as a string.

        Returns:
            float: The cleaned coordinate value.
        """
        coord = coord.replace("\n", "")
        return float(coord)

    def _extract_extent(self, xml_extract):
        """
        Extracts the extent of the geographic area from XML metadata.

        Args:
            xml_extract (BeautifulSoup): Parsed XML metadata using BeautifulSoup.

        Returns:
            shapely.geometry.Polygon: A polygon representing the bounding box (extent) of the area.
        """
        minx = self._clean_coord(xml_extract.find("gmd:westboundlongitude").text)
        miny = self._clean_coord(xml_extract.find("gmd:southboundlatitude").text)
        maxx = self._clean_coord(xml_extract.find("gmd:eastboundlongitude").text)
        maxy = self._clean_coord(xml_extract.find("gmd:northboundlatitude").text)
        return box(minx, miny, maxx, maxy)

    @staticmethod
    def _read_xml(url):
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
                print(f"Error: Received status code {response.status_code} for {url}")
        except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
            print(f"Error reading XML from {url}: {e}")
        return None

    def _no_data_filter(self, gdf_row):
        """
        Filters out images with too much nodata based on the specified percentage threshold.

        Args:
            gdf_row (GeoDataFrame row): Row of the GeoDataFrame representing an image.

        Returns:
            bool: True if the nodata percentage exceeds the threshold, False otherwise.
        """
        image_link = gdf_row["image_link"]
        if not isinstance(image_link, str):
            return False
        minx, miny, maxx, maxy = gdf_row.geometry.bounds
        try:
            with rio.open(image_link) as src:
                nodata = src.profile["nodata"]
                window = from_bounds(minx, miny, maxx, maxy, src.transform)
                window_data = src.read(1, window=window)
                window_size = window_data.shape[0] * window_data.shape[1]
                nodata_total = np.sum(window_data == nodata)
                return nodata_total / window_size * 100 >= self.nodata_percent
        except Exception as e:
            print(f"Cannot open image {e}")
            return False

    def _s2_cloudless_filter(self, gdf_row):
        """
        Filters out images with too much cloud cover based on the S2 cloudless product.

        Args:
            gdf_row (GeoDataFrame row): Row of the GeoDataFrame representing an image.

        Returns:
            bool: True if the cloud cover percentage exceeds the threshold, False otherwise.
        """
        image_link = gdf_row["image_link"]
        if not isinstance(image_link, str):
            return False
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
                return cloud_issues / window_size * 100 >= self.s2cloudless_percent

        except Exception as e:
            print(f"Cannot open cloud mask image {e}")
            return False

    @staticmethod
    def _extract_date_from_link(gdf_row):
        """
        Extracts a date string from the given file name.

        Args:
            file_name (str): The name of the file containing a date.

        Returns:
            str: The formatted date string (YYYY-MM-DD) if found, otherwise None.
        """
        if not isinstance(gdf_row["image_link"], str):
            return None
        else:
            s2_link = gdf_row["image_link"]

        file_name = s2_link.split("/")[-1]
        try:
            date_str = re.search(r"_(\d{8})_", file_name).group(1)
            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            return formatted_date
        except Exception as e:
            print(f"Error extracting date from {file_name}: {e}")
            return None

    def _filter_xmls_to_gdf(self, xml_links):
        """
        Filters a list of Sentinel-2 XML links based on cloud cover and creates a
        GeoDataFrame of corresponding image links and extent geometry.

        Args:
            xml_links (list of str): List of links to Sentinel-2 XML files.

        Returns:
            GeoDataFrame: A GeoDataFrame with 'image_link' for TIFF image URLs
            and 'geometry' of image extents.
        """
        retained_links = []
        retained_geom = []
        for url in xml_links:
            xml_extract = self._read_xml(url)
            if xml_extract is None:
                continue

            if self._extract_xml_cloud(xml_extract) > self.cloud_cover_max:
                continue

            retained_geom.append(self._extract_extent(xml_extract))
            retained_links.append(url)
            time.sleep(random.uniform(0.01, 0.1))

        image_links = [
            x.replace("_meta.xml?download=1", ".tif") for x in retained_links
        ]

        return gpd.GeoDataFrame(
            {"image_link": image_links, "geometry": retained_geom},
            crs="epsg:4386",
        )

    def _image_links_to_aoi_gdf(self, xml_links):
        """
        Performs a spatial join between AOI polygons and corresponding Sentinel-2 images,
        adding image download links as an attribute.

        Args:
            xml_links (list of str): List of links to Sentinel-2 XML files.

        Returns:
            GeoDataFrame: A GeoDataFrame of AOI polygons with corresponding image links.
            If no suitable images are found, the image link column will be NULL.
            If multiple matching images are found, AOI polygons are duplicated for each matching image URL.
        """
        filtered_image_gdf = self._filter_xmls_to_gdf(xml_links)
        return gpd.sjoin(
            self.aoi,
            filtered_image_gdf.to_crs(epsg=27700),
            how="left",
        ).reset_index()

    def _filter_images(self, gdf):
        """
        Applies nodata and S2 cloudless filters to the GeoDataFrame to remove unsuitable images.

        Args:
            gdf (GeoDataFrame): A GeoDataFrame of AOI polygons with corresponding image links.

        Returns:
            GeoDataFrame: The filtered GeoDataFrame with unsuitable images removed.
        """
        print("applying nodata filter...")
        gdf.loc[gdf.apply(self._no_data_filter, axis=1), "image_link"] = None
        print("applying s2cloudless filter...")
        gdf.loc[gdf.apply(self._s2_cloudless_filter, axis=1), "image_link"] = None
        gdf = gdf.drop_duplicates().reset_index(drop=True)
        gdf["image_date"] = gdf.apply(self._extract_date_from_link, axis=1)
        return gdf

    @staticmethod
    def _filter_group(group):
        """
        Filters a group of rows to retain only the rows with image links available.

        Args:
            group (DataFrameGroupBy object): Grouped DataFrame rows.

        Returns:
            DataFrame: The filtered group of rows.
        """
        non_na_rows = group[group["image_link"].notna()]
        if not non_na_rows.empty:
            return non_na_rows
        else:
            return group.head(1)

    def find_image_links(self):
        """
        Main method to find Sentinel-2 image links matching the given AOI, date range, and cloud cover criteria.

        Returns:
            GeoDataFrame: A GeoDataFrame with AOI polygons and corresponding Sentinel-2 image links.
        """
        print("filtering S2 tiles...")
        self._filter_sentinel2_tiles()
        print("extracting xml image metadata...")
        xml_links = self.all_xml_list()
        print("joining suitable images to features...")
        gdf = self._image_links_to_aoi_gdf(xml_links)
        gdf = self._filter_images(gdf)
        if gdf[gdf["image_link"].notna()].shape[0] == 0:
            print(WARNING, "No suitable cloud free images found")
        # keep all image links rows or one row per feature if no images found
        gdf = gdf.groupby(self.id_col, group_keys=False).apply(self._filter_group)
        gdf = gdf.sort_values(by=[self.id_col, "image_date"], ascending=True)
        gdf = gdf.reset_index(drop=True)
        columns = list(self.aoi.columns) + ["image_link", "image_date"]
        return gdf[columns]
