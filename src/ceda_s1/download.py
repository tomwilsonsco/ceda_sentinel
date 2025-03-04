import rasterio as rio
from rasterio.windows import from_bounds
import geopandas as gpd
import numpy as np
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format="\n%(asctime)s.%(msecs)03d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
                logging.FileHandler("s1_image_search.log", mode="w"),
                logging.StreamHandler(),
            ],
)


class S1Downloader:
    """
    Download cloud optimised geotiffs image extracts using geodataframe geometries.

    Attributes:
        image_links (list): List of image links to download.
        aoi_filepath (str): The filepath to shapefile, geojson or geopackage for area of interest.
        output_dir (Path): Directory where output images will be saved.
        ratio_band (bool): Whether to calculate a ratio band from dB VV - VH.
        median_composite (bool): Whether to create a median composite from the images.
        download_all (bool): Whether to download all individual images.
        median_name (str): The prefix name to give median composite image will have \
            _asc or _desc suffix recommended to be start and end month year.
    """

    def __init__(
        self,
        image_links,
        aoi_filepath,
        output_dir,
        ratio_band=False,
        median_composite=False,
        download_all=False,
        median_name="s1_median",
    ):

        self.image_links = image_links
        self.aoi_filepath = aoi_filepath
        self.output_dir = output_dir
        self.ratio_band = ratio_band
        self.median_composite = median_composite
        self.download_all = download_all
        self.median_name = median_name
        self.__logger = logging.getLogger(__name__)

    def _get_window(self, image_link, aoi_gdf):
        """
        Read image window from image link.
        Args:
            image_link (str): The image link to read.
            aoi_gdf (geopandas.GeoDataFrame): The AOI. Only first row used to make window.
        Returns:
            tuple: A tuple containing the window image array and metadata.
        """
        try:
            with rio.open(image_link) as src:
                bounds = aoi_gdf.bounds.values[0]
                window = from_bounds(*bounds, transform=src.transform)
                img_arr = src.read(window=window)
                out_transform = src.window_transform(window)
                out_metadata = src.profile.copy()
                out_metadata.update(
                    height=img_arr.shape[1],
                    width=img_arr.shape[2],
                    transform=out_transform,
                    dtype=img_arr.dtype,
                )
                self.__logger.info(f"Read array from {image_link}")
                return img_arr, out_metadata
        except Exception as e:
            self.__logger.error(f"Error reading {image_link}: {e}")

    @staticmethod
    def _write_window(img_arr, out_metadata, output_path):
        """
        Writes image array to tif file at the specified output path.
        Args:
            img_arr (numpy.ndarray): The image array to be written to the file.
            out_metadata (dict): Rasterio metadata for the output file.
            output_path (str): The path where the output file will be saved.
        Returns:
            str: The path to the output file.
        """
        with rio.open(output_path, "w", **out_metadata) as dst:
            dst.write(img_arr)

    @staticmethod
    def _median_of_arrays(array_list):
        """
        Calculate the median of a list of arrays.

        Parameters:
        array_list (list): A list of numpy arrays.

        Returns:
        numpy.ndarray: The median array.
        """
        if not array_list:
            return None

        stacked_arrays = np.stack(array_list, axis=0)

        return np.median(stacked_arrays, axis=0)

    def _calculate_ratio_band(self, img_arr):
        """
        Calculate the ratio band from dB VV - VH.

        Parameters:
        img_arr (numpy.ndarray): The image array.

        Returns:
        numpy.ndarray: The ratio band array.
        """
        diff = img_arr[0, :, :] - img_arr[1, :, :]
        return np.concatenate([img_arr, diff[np.newaxis, :, :]])

    def download_images(self):
        """
        Download images from image links.
        """
        aoi_gdf = gpd.read_file(self.aoi_filepath)

        if self.median_composite:
            self.asc_list = []
            self.desc_list = []
        else:
            self.asc_list = None
            self.desc_list = None

        for image_link in self.image_links:
            img_arr, out_metadata = self._get_window(image_link, aoi_gdf)
            if self.ratio_band:
                img_arr = self._calculate_ratio_band(img_arr)
                out_metadata.update(count=3)
            if self.median_composite:
                if "_asc_" in image_link:
                    self.asc_list.append(img_arr)
                else:
                    self.desc_list.append(img_arr)

            if self.download_all:
                output_path = (
                    Path(self.output_dir)
                    / f"{Path(image_link).stem}_{Path(self.aoi_filepath).stem}.tif"
                )
                self._write_window(img_arr, out_metadata, output_path)
                self.__logger.info(f"Downloaded {output_path}")

        if self.asc_list:
            self.__logger.info(f"Calculating median for {len(self.asc_list)} ascending images.")
            asc_median = self._median_of_arrays(self.asc_list)
            asc_output_path = Path(self.output_dir) / f"{self.median_name}_asc.tif"
            self._write_window(asc_median, out_metadata, asc_output_path)
            self.__logger.info(f"Downloaded {asc_output_path}")

        if self.desc_list:
            self.__logger.info(f"Calculating median for {len(self.desc_list)} descending images.")
            desc_median = self._median_of_arrays(self.desc_list)
            desc_output_path = Path(self.output_dir) / f"{self.median_name}_desc.tif"
            self._write_window(desc_median, out_metadata, desc_output_path)
            self.__logger.info(f"Downloaded {desc_output_path}")

        self.__logger.info("Download complete.")
