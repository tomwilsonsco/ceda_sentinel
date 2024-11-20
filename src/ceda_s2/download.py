import rasterio as rio
from rasterio.windows import from_bounds
from pathlib import Path


class ImageDownloader:
    def __init__(
        self,
        gdf,
        output_dir,
        link_col="image_links",
        band_indices=(1, 2, 3),
        feature_col="id",
    ):
        self.gdf = gdf
        self.output_dir = Path(output_dir)
        self.link_col = link_col
        self.band_indices = list(band_indices)
        self.feature_col = feature_col

        if self.feature_col not in self.gdf.columns:
            raise ValueError("Feature column {id} not found in features.")

        if self.gdf.empty:
            raise ValueError("The GeoDataFrame is empty.")

    @staticmethod
    def _create_file_name(s2_link, feature_id):
        file_name = s2_link.split("/")[-1]
        return f"fid{feature_id}_{file_name}"

    def _read_from_row(self, gdf_row):
        s2_link = gdf_row[self.link_col]
        feature_id = gdf_row[self.feature_col]
        file_name = self._create_file_name(s2_link, feature_id)
        minx, miny, maxx, maxy = gdf_row.geometry.bounds
        with rio.open(s2_link) as src:
            window = from_bounds(minx, miny, maxx, maxy, src.transform)
            window_data = src.read(self.band_indices, window=window)
            prof = src.profile
        return file_name, window_data, prof, window

    def _write_window(self, file_name, window_data, prof, window):
        output_file = self.output_dir / file_name
        new_transform = rio.windows.transform(window, prof["transform"])
        prof.update(
            count=len(self.band_indices),
            transform=new_transform,
            width=window_data.shape[2],
            height=window_data.shape[1],
        )
        with rio.open(output_file, "w", **prof) as f:
            f.write(window_data)
            print(f"written {output_file}")

    def download_from_gdf(self):
        for i, row in self.gdf.iterrows():
            self._write_window(*self._read_from_row(row))
