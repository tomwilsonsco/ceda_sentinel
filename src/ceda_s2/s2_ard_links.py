import requests
from requests.exceptions import ReadTimeout
from bs4 import BeautifulSoup
import time
import random
from datetime import datetime, timedelta
from shapely.geometry import box
from fiona.drvsupport import supported_drivers
import geopandas as gpd

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
    def __init__(self,
                 aoi_gdf,
                 start_date,
                 end_date,
                 base_url,
                 cloud_cover_max):
        self.aoi = aoi_gdf
        self.start_date = start_date
        self.end_date = end_date
        self.base_url = base_url
        self.cloud_cover_max = cloud_cover_max
        self.tile_list = None

    def _filter_sentinel2_tiles(self):
        """
        Filters Sentinel-2 satellite tiles based on the given AOI.

        This function intersects the input AOI with a layer of Sentinel-2 tiles. The default layer is sourced from an ESA KML file.

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
            self.tile_list = gpd.sjoin(tiles_layer, self.aoi.to_crs(epsg=4326), how="inner")[
                "Name"
            ].to_list()
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
        date_range = (start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1))
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

        Sends a GET request to the provided URL, parses the HTML content, and extracts all links that end with '.xml?download=1'.
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
        Gathers all XML file links from a range of URLs constructed based on a base CEDA URL and a date range.

        Extracts XML links from each generated URL within the date range. Filters links based on provided tiles if available.

        Returns:
            list: A list of all extracted XML file links across the specified date range.
        """
        date_urls = self._get_existing_folders()
        xml_links = []
        for url in date_urls:
            xml_links.extend(self._extract_xml_links(url))
            time.sleep(random.uniform(0.5, 1.5))
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
        lines = ["".join(l.split()) for l in lines]
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

    @staticmethod
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
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return BeautifulSoup(response.text, "lxml")

    def filter_xmls_to_gdf(self, xml_links):
        """
        Filters a list of Sentinel-2 XML links based on cloud cover and creates a
        GeoDataFrame of corresponding image links and extent geometry.

        Args:
            xml_links (list of str): List of links to Sentinel-2 XML files.

        Returns:
            GeoDataFrame: A GeoDataFrame with 'image_links' for TIFF image URLs
            and 'geometry' of image extents.
        """
        retained_links = []
        retained_geom = []
        for url in xml_links:
            try:
                xml_extract = self._read_xml(url)
            except Exception as e:
                print(f"Error reading XML from {url}: {e}")
                continue

            if self._extract_xml_cloud(xml_extract) > self.cloud_cover_max:
                continue

            retained_geom.append(self._extract_extent(xml_extract))
            retained_links.append(url)
            time.sleep(random.uniform(0.5, 1.5))

        image_links = [x.replace("_meta.xml?download=1", ".tif") for x in retained_links]

        return gpd.GeoDataFrame(
            {"image_links": image_links, "geometry": retained_geom},
            crs="epsg:4386",
        )

    def image_links_to_aoi_gdf(self, xml_links):
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
        filtered_image_gdf = self.filter_xmls_to_gdf(xml_links)
        return gpd.sjoin(
            self.aoi,
            filtered_image_gdf.to_crs(epsg=27700),
            how="left",
        ).reset_index()

    def find_image_links(self):
        """
        Main method to find Sentinel-2 image links matching the given AOI, date range, and cloud cover criteria.

        Returns:
            GeoDataFrame: A GeoDataFrame with AOI polygons and corresponding Sentinel-2 image links.
        """
        print("filtering S2 tiles using AOI...")
        self._filter_sentinel2_tiles()
        print("extracting xml image metadata...")
        xml_links = self.all_xml_list()
        print("joining suitable images to aoi...")
        return self.image_links_to_aoi_gdf(xml_links)
