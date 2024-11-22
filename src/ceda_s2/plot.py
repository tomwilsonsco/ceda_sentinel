import rasterio as rio
from rasterio.windows import from_bounds
from rasterio.plot import show
import matplotlib.pyplot as plt
from matplotlib.widgets import Button
import numpy as np
import geopandas as gpd


class ImagePlotter:
    """
    A class to visualize cloud optimised satellite imagery using GeoDataFrame information.

    Attributes:
        gdf (GeoDataFrame): The GeoDataFrame containing geometry and image links.
        link_col (str): Column name in gdf that contains image file links.
        band_indices (list of int): List of band indices to be used for plotting.
        feature_col (str): Column name in gdf containing feature identifiers.
        plot_row (int): Index to keep track of the current feature being plotted.
        fig (Figure): Matplotlib figure for plotting images.
        ax (Axes): Matplotlib axis for plotting images.
        ax_next (Axes): Matplotlib axis for the next button.
        btn_next (Button): Button widget to display the next image.
    """
    def __init__(
            self, gdf, link_col="image_links", band_indices=(1, 2, 3), feature_col="id", plot_geom=True, geom_buffer=100,
    ):
        """
        Initializes the ImagePlotter with a GeoDataFrame and required settings.

        Args:
            gdf (GeoDataFrame): A GeoDataFrame containing the image links and geometry data.
            link_col (str, optional): Name of the column that contains image links. Default is "image_links".
            band_indices (tuple of int, optional): Tuple of band indices to plot (default is (1, 2, 3)).
            feature_col (str, optional): Name of the feature column in GeoDataFrame (default is "id").
            plot_geom (bool, optional): Whether to overlay geometry on the image plots as red outline (default True).
            geom_buffer (int, optional): How much distance to buffer features when extracting image windows (default 100
            metres).
        Raises:
            ValueError: If the feature column is not found in GeoDataFrame or if GeoDataFrame is empty.
        """
        self.gdf = gdf[gdf[link_col].notna()].reset_index(drop=True)
        self.link_col = link_col
        self.band_indices = list(band_indices)
        self.feature_col = feature_col
        self.plot_geom = plot_geom,
        self.geom_buffer = geom_buffer
        self.normalise_min = 0
        self.normalise_max = 150
        self.plot_row = 0

        if self.feature_col not in self.gdf.columns:
            raise ValueError("Feature column {id} not found in features.")

        if self.gdf.empty:
            raise ValueError("The GeoDataFrame is empty.")

        # Setup Matplotlib figure and button
        self.fig, self.ax = plt.subplots()
        plt.subplots_adjust(bottom=0.2)  # Adjust to make space for buttons

        # Create separate axes for "Previous" and "Next" buttons
        self.ax_prev = plt.axes((0.1, 0.05, 0.1, 0.075))  # Left side for "Previous"
        self.btn_prev = Button(self.ax_prev, "Previous")
        self.btn_prev.on_clicked(self.prev_image)

        self.ax_next = plt.axes((0.8, 0.05, 0.1, 0.075))  # Right side for "Next"
        self.btn_next = Button(self.ax_next, "Next")
        self.btn_next.on_clicked(self.update_image)

        # Plot the first image
        self.plot_sample_image()

        plt.show()

    def _create_plot_title(self, gdf_row):
        """
        Creates a plot title for the given GeoDataFrame row.

        Args:
            gdf_row (Series): A row from the GeoDataFrame.

        Returns:
            str: A formatted plot title containing feature ID, date, and file name.
        """
        s2_link = gdf_row[self.link_col]
        feature_id = gdf_row[self.feature_col]
        image_date = gdf_row["image_date"]
        file_name = s2_link.split("/")[-1]
        file_name = file_name.replace("_osgb_vmsk_sharp_rad_srefdem_stdsref.tif", "")
        return f"Feature {feature_id} {image_date}\n{file_name}"

    def _normalise_window(self, window_data):
        """
        Normalises window array using class attribute normalise_min and normalise max values.

        Args:
             window_data (numpy.array) Array of image pixel values to normalise.
        :return:
        """
        minv = self.normalise_min
        maxv = self.normalise_max
        window_data = np.where(window_data < minv, minv, window_data)
        window_data = np.where(window_data > maxv, maxv, window_data)
        return (window_data - minv) / (maxv - minv)


    def _read_from_row(self, gdf_row):
        """
        Reads image data and metadata from the given GeoDataFrame row.

        Args:
            gdf_row (Series): A row from the GeoDataFrame containing image link and geometry.

        Returns:
            tuple: A tuple containing window data, profile, window object, and plot title.
        """
        plot_title = self._create_plot_title(gdf_row)
        s2_link = gdf_row[self.link_col]
        minx, miny, maxx, maxy = gdf_row.geometry.buffer(self.geom_buffer).bounds
        with rio.open(s2_link) as src:
            window = from_bounds(minx, miny, maxx, maxy, src.transform)
            window_data = src.read(self.band_indices, window=window)
            win_transform = rio.windows.transform(window, src.transform)
        window_data = self._normalise_window(window_data)
        return window_data, win_transform, window, plot_title

    def plot_sample_image(self):
        """
        Plots a sample image from the GeoDataFrame using the current row index.

        Resets the index to 0 if the end of the GeoDataFrame is reached.
        """
        if self.plot_row >= len(self.gdf):
            self.plot_row = 0  # Loop back to the beginning
        elif self.plot_row < 0:
            self.plot_row = len(self.gdf) - 1

        current_row = self.gdf.iloc[self.plot_row]
        window_data, win_transform, window, plot_title = self._read_from_row(current_row)

        # Assuming RGB ordering is [2, 1, 0]
        if len(window_data.shape) == 3 and window_data.shape[0] >= 3:
            window_data = window_data[[2, 1, 0], :, :]  # RGB bands
            self.ax.clear()
            show(window_data, ax=self.ax, transform=win_transform, with_bounds=True)
            self.ax.set_title(f"{plot_title}")
            if self.plot_geom:
                gpd.GeoSeries([current_row.geometry]).boundary.plot(
                ax=self.ax, color='red', linewidth=2
                )

            plt.draw()

    def update_image(self, event):
        """
        Event handler to update the plot with the next image in the GeoDataFrame.

        Args:
            event (Event): The event that triggers the image update.
        """
        self.plot_row += 1
        self.plot_sample_image()

    def prev_image(self, event):
        """
        Event handler to update the plot with the next image in the GeoDataFrame.

        Args:
            event (Event): The event that triggers the image update.
        """
        self.plot_row -= 1
        self.plot_sample_image()