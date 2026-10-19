"""
Unit tests for smaller Sentinel-2 fixes: the caller's AOI is left unchanged,
ImagePlotter honours plot_geom, and FindS2STAC can reuse a STAC client.
"""

from types import SimpleNamespace

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin
from shapely.geometry import box

from ceda_s2 import FindS2, FindS2STAC, ImagePlotter


@pytest.mark.parametrize("finder_cls", [FindS2, FindS2STAC], ids=["FindS2", "STAC"])
def test_aoi_passed_in_is_not_changed(finder_cls):
    # No id column and not in EPSG:27700, so both AOI checks would change it
    aoi = gpd.GeoDataFrame(
        {"name": ["a"]}, geometry=[box(-3.2, 55.9, -3.1, 56.0)], crs=4326
    )
    original = aoi.copy()
    finder = finder_cls(aoi, "2024-06-01", "2024-06-07")
    finder._check_id_column()
    finder._check_and_reproject_aoi()

    assert finder.aoi.crs.to_epsg() == 27700
    assert "id" in finder.aoi.columns
    assert aoi.crs.to_epsg() == 4326
    assert list(aoi.columns) == list(original.columns)
    assert aoi.geom_equals(original).all()


@pytest.fixture
def plot_gdf(tmp_path):
    image = tmp_path / "image.tif"
    with rio.open(
        image,
        "w",
        driver="GTiff",
        width=50,
        height=50,
        count=3,
        dtype="uint8",
        crs="EPSG:27700",
        transform=from_origin(0, 500, 10, 10),
    ) as dst:
        dst.write(np.full((3, 50, 50), 100, dtype="uint8"))
    return gpd.GeoDataFrame(
        {"id": [1], "image_link": [str(image)], "image_date": ["2024-06-01"]},
        geometry=[box(200, 200, 300, 300)],
        crs=27700,
    )


@pytest.mark.filterwarnings("ignore:FigureCanvasAgg is non-interactive")
@pytest.mark.parametrize("plot_geom", [True, False])
def test_image_plotter_plot_geom(plot_gdf, plot_geom):
    plt.switch_backend("Agg")
    try:
        plotter = ImagePlotter(plot_gdf, plot_geom=plot_geom)
        # The red feature outline is the only collection added to the axes
        assert (len(plotter.ax.collections) > 0) is plot_geom
    finally:
        plt.close("all")


def test_stac_search_reuses_client(monkeypatch):
    def fail(url):
        raise AssertionError("a new STAC client was opened")

    monkeypatch.setattr("ceda_s2.stac_find.get_stac_client", fail)
    searches = []
    client = SimpleNamespace(
        search=lambda **kwargs: searches.append(kwargs)
        or SimpleNamespace(items=lambda: iter(["item"]))
    )
    aoi = gpd.GeoDataFrame({"id": [1]}, geometry=[box(0, 0, 10, 10)], crs=27700)
    finder = FindS2STAC(aoi, "2024-06-01", "2024-06-07", client=client)

    assert finder._search_stac() == ["item"]
    assert finder._search_stac() == ["item"]
    assert len(searches) == 2
