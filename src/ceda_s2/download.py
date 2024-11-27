import rasterio as rio
from rasterio.windows import from_bounds
from pathlib import Path


class ImageDownloader:
    """
    Download cloud optimised geotiffs image extracts using geodataframe geometries.

    Attributes:
        gdf (GeoDataFrame): GeoDataFrame with polygon geometries and image links.
        output_dir (Path): Directory where output images will be saved.
        link_col (str): Name of the column in gdf containing image links.
        band_indices (tuple): Tuple of band indices to write when downloading. NOTE: This is rasterio 1-indexed order,
        not 0 indexed.
        feature_col (str): Name of the column in gdf containing unique feature identifiers.
        band_descriptions (list): List of strings of band names, used when writing image, must match number of bands.
    """

    def __init__(
        self,
        gdf,
        output_dir,
        link_col="image_link",
        band_indices=(1, 2, 3, 4),
        feature_col="id",
        band_descriptions=None,
    ):
        """
        Initializes ImageDownloader with given GeoDataFrame and parameters.

        Args:
            gdf (GeoDataFrame): GeoDataFrame with polygon geometries and image links.
            output_dir (str or Path): Directory where output images will be saved.
            link_col (str, optional): Name of the column in gdf containing image links. Defaults to "image_links".
            band_indices (tuple, optional): Tuple of band indices to read and save.
                                            Rasterio 1-indexed. Defaults to (1, 2, 3,7) for B,G,R,NiR.
            feature_col (str, optional): Name of the column in gdf containing unique feature identifiers.
                                         Defaults to "id".
            band_descriptions (list): List of strings of band names, used when writing image.
                                      Must match number of bands.
                                      Defaults to None and set from first image read.

        Raises:
            ValueError: If feature_col is not found in gdf columns or if the GeoDataFrame is empty.
        """
        self.gdf = gdf
        self.output_dir = Path(output_dir)
        self.link_col = link_col
        self.band_indices = list(band_indices)
        self.feature_col = feature_col
        self.band_descriptions = None

        if self.feature_col not in self.gdf.columns:
            raise ValueError("Feature column {id} not found in features.")

        if self.gdf.empty:
            raise ValueError("The GeoDataFrame is empty.")

    @staticmethod
    def _create_file_name(s2_link, feature_id):
        """
        Creates a file name for the output image based on the image link and feature ID.

        Args:
            s2_link (str): The link to the Sentinel-2 image.
            feature_id (str or int): The unique identifier for the feature.

        Returns:
            str: The generated file name.
        """
        file_name = s2_link.split("/")[-1]
        return f"fid{feature_id}_{file_name}"

    def _read_from_row(self, i, gdf_row):
        """
        Reads image data for a given row from the GeoDataFrame.

        Args:
            gdf_row (GeoDataFrame row): A row from the GeoDataFrame containing feature geometry and image link.

        Returns:
            tuple: A tuple containing the file name, window data, profile, and window object.
        """
        s2_link = gdf_row[self.link_col]
        feature_id = gdf_row[self.feature_col]
        file_name = self._create_file_name(s2_link, feature_id)
        minx, miny, maxx, maxy = gdf_row.geometry.bounds
        with rio.open(s2_link) as src:
            if i == 0:
                band_names = list(src.descriptions)
                self.band_descriptions = [band_names[j - 1] for j in self.band_indices]
                print(
                    f"Downloading bands {self.band_descriptions}.\nAvailable bands {band_names}"
                )
            window = from_bounds(minx, miny, maxx, maxy, src.transform)
            window_data = src.read(self.band_indices, window=window)
            prof = src.profile
        return file_name, window_data, prof, window

    def _write_window(self, file_name, window_data, prof, window):
        """
        Writes the image data for a given window to an output file.

        Args:
            file_name (str): The name of the output file.
            window_data (numpy array): The image data for the window.
            prof (dict): The profile metadata for the image.
            window (Window): The window object representing the bounds of the data.
        """
        output_file = self.output_dir / file_name
        new_transform = rio.windows.transform(window, prof["transform"])
        prof.update(
            count=len(self.band_indices),
            transform=new_transform,
            width=window_data.shape[2],
            height=window_data.shape[1],
        )
        with rio.open(output_file, "w", **prof) as f:
            f.descriptions = tuple(self.band_descriptions)
            f.write(window_data)
            print(f"written {output_file}")

    def download_from_gdf(self):
        """
        Downloads image data for all features in the GeoDataFrame and saves them to the output directory.
        """
        for i, row in self.gdf.iterrows():
            self._write_window(*self._read_from_row(i, row))
