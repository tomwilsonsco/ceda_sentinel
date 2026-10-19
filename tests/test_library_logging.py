"""
Tests that importing and constructing the library classes leaves logging alone.

Run in a subprocess so that pytest's own logging handlers don't interfere.
"""

import subprocess
import sys

SCRIPT = """
import logging

import geopandas as gpd
from shapely.geometry import box

from ceda_s1 import FindS1, FindS1STAC, S1Downloader
from ceda_s2 import FindS2, FindS2STAC, ImageDownloader

gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[box(0, 0, 10, 10)], crs=27700)
FindS2(gdf, "2024-06-01", "2024-06-07")
FindS2STAC(gdf, "2024-06-01", "2024-06-07")
ImageDownloader(gdf, "out")
FindS1("2024-06-01", "2024-06-07", "aoi.gpkg")
FindS1STAC("2024-06-01", "2024-06-07", "aoi.gpkg")
S1Downloader([], "aoi.gpkg", "out")

root = logging.getLogger()
assert root.handlers == [], root.handlers
assert root.level == logging.WARNING, root.level
"""


def test_library_does_not_configure_logging(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []
