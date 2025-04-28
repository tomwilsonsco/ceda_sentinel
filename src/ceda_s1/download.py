import rasterio as rio
from rasterio.mask import mask
from rasterio.features import rasterize
from rasterio.windows import from_bounds
from shapely.geometry import box
import geopandas as gpd
import numpy as np
from pathlib import Path
import logging
import concurrent.futures
from io import BytesIO

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
        image_links (dict): Dictionary of image links to download per feature.
        aoi_filepath (str): The filepath to shapefile, geojson or geopackage for area of interest.
        output_dir (Path): Directory where output images will be saved.
        tif_output (bool): Whether to save images as tif files if False (default) will be npz file.
        aoi_id (str): The column name in the AOI file to use as the unique ID for search results.
        feature_ids (list): List of feature IDs to process. If None, all features will be processed.
        ratio_band (bool): Whether to calculate a ratio band from dB VV - VH.
        download_all (bool): Whether to download all individual images.
        use_threads (bool): Whether to use multi-threading faster for downloading. Default is True.
    """

    def __init__(
        self,
        image_links,
        aoi_filepath,
        output_dir,
        tif_output=False,
        aoi_id="OBJECTID",
        feature_ids=None,
        ratio_band=False,
        download_all=False,
        use_threads=True,
    ):

        self.image_links = image_links
        self.aoi_filepath = aoi_filepath
        self.output_dir = output_dir
        self.tif_output = tif_output
        self.aoi_id = aoi_id
        self.feature_ids = feature_ids
        self.ratio_band = ratio_band
        self.download_all = download_all
        self.use_threads = use_threads
        self.__logger = logging.getLogger(__name__)

    def _get_array(self, image_link, aoi_gdf):
        """
        Read image feature from image link.
        Args:
            image_link (str): The image link to read.
            aoi_gdf (geopandas.GeoDataFrame): The AOI. Only first row used to make window.
        Returns:
            tuple: A tuple containing the window image array and metadata.
        """
        try:
            with rio.open(image_link) as src:
                aoi_geom = [geom for geom in aoi_gdf.geometry]
                bounds = aoi_gdf.total_bounds
                window = from_bounds(*bounds, src.transform)
                img_arr = src.read(window=window)
                nodata = src.nodata
                if nodata is not None:
                    img_arr = np.where(img_arr == nodata, -999, img_arr)
                    nodata = -999
                if img_arr.shape[1] == 0 or img_arr.shape[2] == 0:
                    return None
                if np.all(img_arr == nodata):
                    return None
                window_transform = src.window_transform(window)

                mask_arr = rasterize(
                    [(geom, 1) for geom in aoi_geom],
                    out_shape=(img_arr.shape[1], img_arr.shape[2]),
                    transform=window_transform,
                    fill=0,
                    all_touched=True,
                    dtype=np.uint8,
                )

                img_arr[:, mask_arr == 0] = -999
                if not self.tif_output:
                    return img_arr
                out_metadata = src.profile.copy()
                out_metadata.update(
                    height=img_arr.shape[1],
                    width=img_arr.shape[2],
                    transform=window_transform,
                    nodata=-999,
                    dtype=img_arr.dtype,
                )
                return img_arr, out_metadata
        except Exception as e:
            self.__logger.error(f"Error reading {image_link}: {e}")
            return None

    @staticmethod
    def _write_arr(img_arr, out_metadata, output_path):
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

    def _process_image_tif(self, aoi_gdf, id, img_links):
        """
        Clips a list of image files by geometry feature and saves tifs for each.
        Args:
            aoi_gdf (GeoDataFrame): A GeoDataFrame containing the area of interest (AOI) geometries.
            id (str): The identifier for the specific AOI row to process.
            img_links (list): A list of image URLs or file paths to be processed.
        Returns:
            None
        """
        output_folder = Path(self.output_dir) / f"{Path(self.aoi_filepath).stem}_{id}"
        output_folder.mkdir(parents=True, exist_ok=True)

        aoi_row = aoi_gdf[aoi_gdf[self.aoi_id] == id]
        for img in img_links:
            output_fp = (
                output_folder
                / f"{Path(img).stem}_{Path(self.aoi_filepath).stem}_{id}.tif"
            )
            if Path.exists(output_fp):
                continue
            try:
                img_arr, out_metadata = self._get_array(img, aoi_row)
            except Exception as e:
                self.__logger.error(f"Error processing image: {e}")
                continue
            if self.ratio_band:
                img_arr = self._calculate_ratio_band(img_arr)
                out_metadata.update(count=3)

            if self.download_all:
                self._write_arr(img_arr, out_metadata, output_fp)
                self.__logger.info(f"Downloaded {output_fp}")

    def _process_image_npz(self, aoi_gdf, id, img_links):
        """
        Clips a list of image files by geometry feature and saves them into one npz file.
        Args:
            aoi_gdf (GeoDataFrame): A GeoDataFrame containing the area of interest (AOI) geometries.
            id (str): The identifier for the specific AOI row to process.
            img_links (list): A list of image URLs or file paths to process.
        Returns:
            None
        """
        output_folder = Path(self.output_dir) / f"{Path(self.aoi_filepath).stem}"
        output_folder.mkdir(parents=True, exist_ok=True)
        npz_path = output_folder / f"{Path(self.aoi_filepath).stem}_{id}.npz"
        if Path.exists(npz_path):
            return
        aoi_row = aoi_gdf[aoi_gdf[self.aoi_id] == id]
        img_dict = {}
        for img in img_links:
            try:
                img_arr = self._get_array(img, aoi_row)
                if img_arr is None:
                    continue
                if self.ratio_band:
                    img_arr = self._calculate_ratio_band(img_arr)
                img_dict[Path(img).stem] = img_arr
            except Exception as e:
                self.__logger.error(f"Error processing image: {e}")
                continue
        self.__logger.info(f"Processed {len(img_dict)} images for {id}")
        np.savez_compressed(npz_path, **img_dict)
        self.__logger.info(f"Saved image arrays to {npz_path}")

    def download_images(self):
        """
        Downloads and saves images to npz or tif files depending on options set.
        Uses a thread pool to process images concurrently if self.use_threads is True.
        Raises:
            Exception: If an error occurs during the processing of an image.
        """
        aoi_gdf = gpd.read_file(self.aoi_filepath)

        process_function = (
            self._process_image_tif if self.tif_output else self._process_image_npz
        )

        if self.use_threads:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [
                    executor.submit(process_function, aoi_gdf, id, img_links)
                    for id, img_links in self.image_links.items()
                    if not self.feature_ids or id in self.feature_ids
                ]

            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    self.__logger.error(f"Error processing image: {e}")
        else:
            for id, img_links in self.image_links.items():
                if not self.feature_ids or id in self.feature_ids:
                    try:
                        process_function(aoi_gdf, id, img_links)
                    except Exception as e:
                        self.__logger.error(f"Error processing image: {e}")


        self.__logger.info("Download complete.")
