import logging
import requests
from requests.exceptions import ReadTimeout
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import random
import geopandas as gpd
import numpy as np
import rasterio as rio
from scipy.ndimage import label
from shapely.geometry import box
from tqdm import tqdm


class FindS1:
    """
    Searches for Sentinel-1 data within a specified date range from CEDA archive
    and filters results based area of interest geometries.
    """

    def __init__(
        self,
        start_date,
        end_date,
        aoi_filepath,
        orbit_numbers=[52, 59, 74, 81, 103, 96, 125, 132, 161, 154, 1, 8, 30, 23],
        date_images_list=None,
        aoi_id="OBJECTID",
        max_no_data_patch=10,
    ):
        """
        Initializes the FindS1 class.

        Args:
            start_date (str): The start date for the search in the format 'YYYY-MM-DD'.
            end_date (str): The end date for the search in the format 'YYYY-MM-DD'.
            aoi_filepath (str): The filepath to shapefile, geojson or geopackage for area of interest.
            aoi_id (str): The column name in the AOI file to use as the unique ID for search results.
            orbit_numbers (list): A list of relative orbit numbers to filter results by.
            max_no_data_patch (int): If a continuous region of no data pixels is larger than this value, the image is discarded.
        """
        self.start_date = start_date
        self.end_date = end_date
        self.orbit_numbers = orbit_numbers
        self.date_images_list = date_images_list
        self.aoi_filepath = aoi_filepath
        self.aoi_id = aoi_id
        self.max_no_data_patch = max_no_data_patch
        self.base_url = "https://data.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1"

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
            urls.append(check_url)
            # try:
            #     response = requests.head(check_url, timeout=10)
            #     if response.status_code == 200:
            #         urls.append(check_url)
            # except ReadTimeout:
            #     self.__logger.error(
            #         f"Request timed out for {check_url}. \nSkipping this date..."
            #     )
        return urls

    def _extract_links(self, url):
        """
        Extracts tif file links from a specified HTML webpage URL.

        Sends a GET request to the provided URL, parses the HTML content, and extracts all
        links that end with '.tif'.
        Only extracts links that contain self.orbit_numbers.

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
                if href.endswith("SpkRL.tif?download=1"):
                    if int(href.split("/")[-1].split("_")[2]) in self.orbit_numbers:
                        if "GB_OSGB" in href.split("/")[-1]:
                            img_links.append(href.replace("?download=1", ""))
        return set(img_links)

    def _aoi_check_images(self, img_list):
        """
        Checks if a window of the AOI geometry is entirely within the image.

        Args:
            img_list (list): A list of image links to check.

        Returns:
            str: The first image link that matches the criteria.
        """
        aoi_gdf = self._read_aoi_file()
        retained_images = {int(uid): [] for uid in aoi_gdf[self.aoi_id].unique()}
        orbits = []
        for img_link in tqdm(img_list, desc="Checking aoi intersection of images"):
            orbit = img_link.split("/")[-1].split("_")[2]
            if orbit not in orbits:
                orbits.append(orbit)
            try:
                with rio.open(img_link) as src:
                    img_geom = box(*src.bounds)
            except Exception as e:
                self.__logger.error(f"Error reading image {img_link}: {e}")
                continue
            intersect_aoi = aoi_gdf[aoi_gdf.within(img_geom)]
            if intersect_aoi.empty:
                continue
            ids = intersect_aoi[self.aoi_id].astype("uint16").to_list()
            for id in ids:
                current = retained_images[id]
                current.append(img_link)
                retained_images[id] = current

        self.__logger.info(f"Found images for relative orbits {" ".join(orbits)}")
        return retained_images

    def _find_largest_region(self, binary_image):
        """
        Find the largest continuous region from a binary image.

        Parameters:
        image (numpy.ndarray): The input image.

        Returns:
        int: The size of the largest continuous region.
        """
        if np.max(binary_image) == 0:
            return 0
        # Label connected components
        labeled_array, _ = label(binary_image)

        # Find the size of each connected component
        component_sizes = np.bincount(labeled_array.ravel())[1:]

        # Find the largest connected component
        return int(component_sizes.max())

    def _filter_nodata(self, arr, nodata_value):
        """
        Filters images based on the percentage of nodata pixels.

        Args:
            img_list (list): A list of image links to check.

        Returns:
            list: A list of image links that meet the specified criteria.
        """

        binary_image = (arr[0] == nodata_value).astype(np.uint8)
        largest_region = self._find_largest_region(binary_image)
        return largest_region <= self.max_no_data_patch

    def get_img_feature_dict(self):
        """
        Gathers all tif file links from URLs constructed based from base CEDA URL and a date range.

        Extracts tif image links from each generated URL within the date range.
        Filters links based on orbit numbers.

        Returns:
            dict: A dictionary of feature id keys with lists of applicable images.
        """
        self.__logger.info(
            f"Searching for images between {self.start_date} and {self.end_date}"
        )
        date_urls = self._get_existing_folders()
        if not self.date_images_list:
            img_links = []
            for url in tqdm(date_urls, "Extracting image links from date folders"):
                img_links.extend(self._extract_links(url))
        else:
            img_links = self.date_images_list

        self.__logger.info(f"Checking {len(img_links)} image links.")

        aoi_img_dict = self._aoi_check_images(img_links)
        self.__logger.info(
            f"Returning image search results for {len(aoi_img_dict.keys())} features."
        )

        return aoi_img_dict, img_links
