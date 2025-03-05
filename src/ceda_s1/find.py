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
from rasterio.windows import from_bounds, shape
from scipy.ndimage import label

logging.basicConfig(
    level=logging.INFO,
    format="\n%(asctime)s.%(msecs)03d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
                logging.FileHandler("s1_image_search.log", mode="w"),
                logging.StreamHandler(),
            ],
)


class FindS1:
    """
    Searches for Sentinel-1 data within a specified date range from CEDA archive
    and filters results based on relative orbit numbers. Extracts links to tif files
    from the available data folders.
    """

    def __init__(
        self,
        start_date,
        end_date,
        aoi_filepath,
        orbit_numbers=[30, 52, 103, 125, 132],
        filter_orbits=False,
        max_no_data_patch=10,
    ):
        """
        Initializes the FindS1 class.

        Args:
            start_date (str): The start date for the search in the format 'YYYY-MM-DD'.
            end_date (str): The end date for the search in the format 'YYYY-MM-DD'.
            aoi_filepath (str): The filepath to shapefile, geojson or geopackage for area of interest.
            orbit_numbers (list): A list of relative orbit numbers to filter results by.
            filter_orbits (bool): If True only one ascending and one descending orbit will be returned.
            max_no_data_patch (int): If a continuous region of no data pixels is larger than this value, the image is discarded.
        """
        self.start_date = start_date
        self.end_date = end_date
        self.orbit_numbers = orbit_numbers
        self.filter_orbits = filter_orbits
        self.aoi_filepath = aoi_filepath
        self.max_no_data_patch = max_no_data_patch
        self.base_url = "https://data.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1"
        self.aoi = self._read_aoi_file()
        self.__logger = logging.getLogger(__name__)

    def _read_aoi_file(self):
        """
        Reads the area of interest (AOI) file using geopandas.

        Returns:
            GeoDataFrame: The AOI data.
        """
        try:
            aoi_data = gpd.read_file(self.aoi_filepath)
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
            try:
                response = requests.head(check_url, timeout=10)
                if response.status_code == 200:
                    urls.append(check_url)
            except ReadTimeout:
                self.__logger.error(
                    f"Request timed out for {check_url}. \nSkipping this date..."
                )
        logging.info(f"Found {len(urls)} existing data folders in the date range.")
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

    def _count_orbits(self, img_list):
        """
        Counts the number of images per orbit number for ascending and descending orbits.

        Args:
            img_list (list): A list of image links to count.

        Returns:
            tuple: Two lists of orbit numbers ordered by the most images for ascending and descending orbits.
        """
        asc_orbits = {}
        desc_orbits = {}

        for img_link in img_list:
            parts = img_link.split("/")[-1].split("_")
            orbit_number = int(parts[2])
            orbit_type = parts[3]

            if str.upper(orbit_type) == "ASC":
                if orbit_number not in asc_orbits:
                    asc_orbits[orbit_number] = 0
                asc_orbits[orbit_number] += 1
            elif str.upper(orbit_type) == "DESC":
                if orbit_number not in desc_orbits:
                    desc_orbits[orbit_number] = 0
                desc_orbits[orbit_number] += 1

        sorted_asc_orbits = dict(
            sorted(asc_orbits.items(), key=lambda item: item[1], reverse=True)
        )
        sorted_desc_orbits = dict(
            sorted(desc_orbits.items(), key=lambda item: item[1], reverse=True)
        )

        return sorted_asc_orbits, sorted_desc_orbits

    def _spatial_check_images(self, img_list):
        """
        Checks if a window of the AOI geometry is entirely contained within the image.

        Args:
            img_list (list): A list of image links to check.

        Returns:
            str: The first image link that matches the criteria.
        """
        retained_images = []
        aoi_gdf = self._read_aoi_file()
        bounds = aoi_gdf.bounds.values[0]
        for img_link in img_list:
            try:
                with rio.open(img_link) as src:
                    window = from_bounds(*bounds, transform=src.transform)
                    arr = src.read(window=window)
                    if arr.shape[1] > 0 and arr.shape[2] > 0:
                        retained_images.append(img_link)
                        self.__logger.info(f"Image {img_link} retained.")
                    else:
                        self.__logger.info(f"Image {img_link} discarded.")
            except Exception as e:
                self.__logger.error(f"Error reading image {img_link}: {e}")
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

    def _filter_nodata(self, img_list):
        """
        Filters images based on the percentage of nodata pixels.

        Args:
            img_list (list): A list of image links to check.

        Returns:
            list: A list of image links that meet the specified criteria.
        """
        retained_images = []
        aoi_gdf = self._read_aoi_file()
        bounds = aoi_gdf.bounds.values[0]
        for img_link in img_list:
            try:
                with rio.open(img_link) as src:
                    window = from_bounds(*bounds, transform=src.transform)
                    arr = src.read(window=window)
                    no_data_value = src.nodata
                    binary_image = (arr[1] == no_data_value).astype(np.uint8)
                    largest_region = self._find_largest_region(binary_image)
                    if largest_region <= self.max_no_data_patch:
                        retained_images.append(img_link)
                        self.__logger.info(f"Image {img_link} retained.")
                    else:
                        self.__logger.info(f"Image {img_link} discarded.")
            except Exception as e:
                self.__logger.error(f"Error reading image {img_link}: {e}")
        return retained_images

    def _filter_image_extent(self, img_list):
        """
        Checks if the specified orbit numbers are present in the image list and if the image geometry
        entirely contains the AOI geometry.

        Args:
            img_list (list): A list of image links to check.

        Returns:
            str: The first image link that matches the criteria.
        """
        self.__logger.info(f"Filtering {len(img_list)} images based on AOI window.")
        img_list = self._spatial_check_images(img_list)
        self.__logger.info(f"After AOI extent filter {len(img_list)} images.")

        self.__logger.info(
            f"Filtering {len(img_list)} images based on nodata pixel patches."
        )
        img_list = self._filter_nodata(img_list)
        self.__logger.info(f"After no data filter {len(img_list)} images.")

        sorted_asc_orbits, sorted_desc_orbits = self._count_orbits(img_list)

        self.__logger.info(f"Order of asc orbits {sorted_asc_orbits}")
        self.__logger.info(f"Order_of desc orbits {sorted_desc_orbits}")

        if self.filter_orbits:

            use_asc_orbit = list(sorted_asc_orbits.keys())[0]
            use_desc_orbit = list(sorted_desc_orbits.keys())[0]
            self.__logger.info(
                f"Filtering to asc {use_asc_orbit} and desc {use_desc_orbit} orbits."
            )

            img_list = [
                x
                for x in img_list
                if int(x.split("/")[-1].split("_")[2])
                in [use_asc_orbit, use_desc_orbit]
            ]

        return img_list

    def get_img_list(self):
        """
        Gathers all tif file links from URLs constructed based from base CEDA URL and a date range.

        Extracts tif image links from each generated URL within the date range.
        Filters links based on orbit numbers.

        Returns:
            list: A list of all extracted tif image file links across the specified date range.
        """
        date_urls = self._get_existing_folders()
        img_links = []
        for url in date_urls:
            img_links.extend(self._extract_links(url))
            time.sleep(random.uniform(0.01, 0.1))

        img_links = self._filter_image_extent(img_links)
        self.__logger.info(f"Returning {len(img_links)} suitable image links.")

        return img_links
