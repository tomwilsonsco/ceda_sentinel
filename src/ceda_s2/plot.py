import rasterio as rio
import re
from rasterio.windows import from_bounds
from rasterio.plot import show
import matplotlib.pyplot as plt
from matplotlib.widgets import Button


class ImagePlotter:
    def __init__(
        self, gdf, link_col="image_links", band_indices=(1, 2, 3), feature_col="id"
    ):
        self.gdf = gdf[gdf[link_col].notna()].reset_index(drop=True)
        self.link_col = link_col
        self.band_indices = list(band_indices)
        self.feature_col = feature_col
        self.plot_row = 0

        if self.feature_col not in self.gdf.columns:
            raise ValueError("Feature column {id} not found in features.")

        if self.gdf.empty:
            raise ValueError("The GeoDataFrame is empty.")

        # Setup Matplotlib figure and button
        self.fig, self.ax = plt.subplots()
        self.ax_next = plt.axes([0.8, 0.05, 0.1, 0.075])
        self.btn_next = Button(self.ax_next, "Next")
        self.btn_next.on_clicked(self.update_image)

        # Plot the first image
        self.plot_sample_image()

        plt.show()

    @staticmethod
    def _extract_date_from_link(file_name):
        try:
            date_str = re.search(r"_(\d{8})_", file_name).group(1)
            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            return formatted_date
        except Exception as e:
            print(f"Error extracting date from {file_name}: {e}")
            return None

    def _create_plot_title(self, gdf_row):
        s2_link = gdf_row[self.link_col]
        feature_id = gdf_row[self.feature_col]
        file_name = s2_link.split("/")[-1]
        file_name = file_name.replace("_osgb_vmsk_sharp_rad_srefdem_stdsref.tif", "")
        image_date = self._extract_date_from_link(file_name)
        return f"Feature {feature_id} {image_date}\n{file_name}"

    def _read_from_row(self, gdf_row):
        plot_title = self._create_plot_title(gdf_row)
        s2_link = gdf_row[self.link_col]
        minx, miny, maxx, maxy = gdf_row.geometry.bounds
        with rio.open(s2_link) as src:
            window = from_bounds(minx, miny, maxx, maxy, src.transform)
            window_data = src.read(self.band_indices, window=window)
            prof = src.profile
        return window_data, prof, window, plot_title

    def plot_sample_image(self):
        if self.plot_row >= len(self.gdf):
            self.plot_row = 0  # Loop back to the beginning

        current_row = self.gdf.iloc[self.plot_row]
        window_data, prof, window, plot_title = self._read_from_row(current_row)

        # Assuming RGB ordering is [2, 1, 0]
        if len(window_data.shape) == 3 and window_data.shape[0] >= 3:
            window_data = window_data[[2, 1, 0], :, :]  # RGB bands
            self.ax.clear()
            show(window_data, ax=self.ax, transform=prof["transform"])
            self.ax.set_title(f"{plot_title}")
            plt.draw()

    def update_image(self, event):
        self.plot_row += 1
        self.plot_sample_image()
