import logging
import requests
from requests.exceptions import ReadTimeout
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import random

logging.basicConfig(
    level=logging.INFO,
    format="\n%(asctime)s.%(msecs)03d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler("image_search.log"), logging.StreamHandler()],
)


class FindS1:
    """
    Searches for Sentinel-1 data within a specified date range from CEDA archive
    and filters results based on relative orbit numbers. Extracts links to tif files
    from the available data folders.
    """

    def __init__(self, start_date, end_date, orbit_numbers=[30, 52, 103, 125, 132]):
        """
        Initializes the FindS1 class.

        Args:
            start_date (str): The start date for the search in the format 'YYYY-MM-DD'.
            end_date (str): The end date for the search in the format 'YYYY-MM-DD'.
            orbit_numbers (list): A list of relative orbit numbers to filter results by.
        """
        self.start_date = start_date
        self.end_date = end_date
        self.orbit_numbers = orbit_numbers
        self.base_url = "https://data.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1"
        self.__logger = logging.getLogger(__name__)

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
                        img_links.append(href.replace("?download=1", ""))

        return set(img_links)

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
        return img_links
