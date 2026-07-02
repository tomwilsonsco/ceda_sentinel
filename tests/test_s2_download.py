"""
Unit tests for ceda_s2.download.ImageDownloader.

These tests do not require network access to CEDA. They serve a small local
GeoTIFF over a temporary HTTP server and verify that ImageDownloader correctly
populates and writes band descriptions.

The key regression test covers the case where the first row of the GeoDataFrame
does not have a DataFrame index of 0. Previously, ``download_from_gdf`` iterated
with ``for i, row in gdf.iterrows()`` so ``i`` was the DataFrame index; the
``if i == 0`` block that sets ``band_descriptions`` was therefore skipped when
the first surviving row had a non-zero index, leaving ``band_descriptions`` as
``None`` and raising ``TypeError: 'NoneType' object is not iterable`` when
writing.
"""

import socket
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import numpy as np
import pytest
import rasterio as rio
import geopandas as gpd
from rasterio.transform import from_origin
from shapely.geometry import box

from ceda_s2 import ImageDownloader


def _free_port():
    """Return an available TCP port on localhost."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _make_source_tif(path, n_bands=4, width=100, height=100):
    """Create a small GeoTIFF with band descriptions for testing."""
    transform = from_origin(0, 100, 10, 10)  # 10m pixels, origin top-left
    data = np.zeros((n_bands, height, width), dtype="uint16")
    descriptions = tuple(f"band_{i}" for i in range(1, n_bands + 1))
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": n_bands,
        "dtype": "uint16",
        "crs": "EPSG:32630",
        "transform": transform,
    }
    with rio.open(path, "w", **profile) as dst:
        dst.write(data)
        dst.descriptions = descriptions
    return path


@pytest.fixture
def http_server(tmp_path):
    """Serve tmp_path over HTTP on a free port for the duration of the test."""
    port = _free_port()

    def _handler(*args, **kwargs):
        SimpleHTTPRequestHandler(*args, directory=str(tmp_path), **kwargs)

    httpd = HTTPServer(("127.0.0.1", port), _handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _make_gdf(url, indices):
    """
    Build a GeoDataFrame pointing at ``url`` with the given DataFrame index.

    ``indices`` controls the DataFrame index, allowing simulation of a gdf
    whose first row does not have index 0 (e.g. after filtering/concat).
    """
    geom = box(200, 20, 300, 80)  # within the source raster bounds
    rows = [
        {"id": idx, "image_link": url, "geometry": geom} for idx in indices
    ]
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:32630")
    gdf.index = list(indices)
    return gdf


def test_download_writes_band_descriptions(tmp_path, http_server):
    """Band descriptions from the source image are written to the output."""
    src_tif = tmp_path / "source.tif"
    _make_source_tif(src_tif)
    url = f"http://127.0.0.1:{http_server}/source.tif"

    out_dir = tmp_path / "outputs"
    out_dir.mkdir()

    gdf = _make_gdf(url, indices=[0, 1])
    downloader = ImageDownloader(gdf, out_dir, band_indices=(1, 2, 3, 4))
    downloader.download_from_gdf()

    outputs = list(out_dir.glob("*.tif"))
    assert len(outputs) == 2
    with rio.open(outputs[0]) as dst:
        assert dst.descriptions == ("band_1", "band_2", "band_3", "band_4")


def test_download_first_row_nonzero_index(tmp_path, http_server):
    """
    Regression: a gdf whose first row has a non-zero index must still populate
    band_descriptions and write them without raising TypeError.
    """
    src_tif = tmp_path / "source.tif"
    _make_source_tif(src_tif)
    url = f"http://127.0.0.1:{http_server}/source.tif"

    out_dir = tmp_path / "outputs"
    out_dir.mkdir()

    # First (and only) row has index 1, not 0 - this triggered the original bug.
    gdf = _make_gdf(url, indices=[1])
    downloader = ImageDownloader(gdf, out_dir, band_indices=(1, 2, 3, 4))

    # Previously raised: TypeError: 'NoneType' object is not iterable
    downloader.download_from_gdf()

    outputs = list(out_dir.glob("*.tif"))
    assert len(outputs) == 1
    with rio.open(outputs[0]) as dst:
        assert dst.descriptions == ("band_1", "band_2", "band_3", "band_4")
    # band_descriptions should have been populated from the first image read
    assert downloader.band_descriptions == ["band_1", "band_2", "band_3", "band_4"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])