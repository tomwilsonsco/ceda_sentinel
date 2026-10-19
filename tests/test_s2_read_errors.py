"""
Unit tests for how FindS2 and FindS2STAC report image read errors.

Readable images are small local GeoTIFFs; unreadable ones are paths that don't
exist, which rasterio fails to open in the same way as an unreachable URL.
"""

import logging
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from ceda_s2 import FindS2, FindS2STAC, ImageReadError
from ceda_stac.client import S2_CLOUD_ASSET, S2_COG_ASSET

AOI_BOUNDS = (300000, 700000, 300100, 700100)
TILE = "T30VVJ"


@pytest.fixture
def aoi_gdf():
    return gpd.GeoDataFrame({"id": [1]}, geometry=[box(*AOI_BOUNDS)], crs=27700)


def write_tif(path, value):
    minx, _, _, maxy = AOI_BOUNDS
    with rio.open(
        path,
        "w",
        driver="GTiff",
        width=20,
        height=20,
        count=1,
        dtype="uint8",
        crs="EPSG:27700",
        transform=from_origin(minx - 50, maxy + 50, 10, 10),
        nodata=0,
    ) as dst:
        dst.write(np.full((1, 20, 20), value, dtype="uint8"))


def make_image(tmp_path, name, readable):
    """Returns the image path, writing it and its cloud mask if readable."""
    image = tmp_path / f"{name}_{TILE}_vmsk_sharp_rad_srefdem_stdsref.tif"
    cloud = tmp_path / f"{name}_{TILE}_clouds.tif"
    if readable:
        write_tif(image, 1)
        write_tif(cloud, 0)
    return str(image), str(cloud)


def make_find_s2(aoi_gdf, monkeypatch, images):
    finder = FindS2(aoi_gdf, "2024-06-01", "2024-06-07")
    monkeypatch.setattr(finder, "_filter_tiles_feature", lambda row: [TILE])
    return finder, [image for image, _ in images]


def make_find_s2_stac(aoi_gdf, monkeypatch, images):
    finder = FindS2STAC(aoi_gdf, "2024-06-01", "2024-06-07")
    monkeypatch.setattr(finder, "_extract_date_from_item", lambda item: "2024-06-01")
    item_geometry = mapping(aoi_gdf.buffer(1000).to_crs(4326).iloc[0])
    items = [
        SimpleNamespace(
            id=f"item{i}",
            geometry=item_geometry,
            assets={
                S2_COG_ASSET: SimpleNamespace(href=image),
                S2_CLOUD_ASSET: SimpleNamespace(href=cloud),
            },
        )
        for i, (image, cloud) in enumerate(images)
    ]
    return finder, items


@pytest.fixture(params=[make_find_s2, make_find_s2_stac], ids=["FindS2", "STAC"])
def make_finder(request, aoi_gdf, monkeypatch, tmp_path):
    def make(*readable):
        images = [make_image(tmp_path, f"img{i}", ok) for i, ok in enumerate(readable)]
        return request.param(aoi_gdf, monkeypatch, images)

    return make


def test_all_reads_failing_raises(make_finder):
    finder, candidates = make_finder(False, False)
    with pytest.raises(ImageReadError) as excinfo:
        finder._find_images_per_feature(candidates)
    assert len(excinfo.value.read_errors) == 2
    assert excinfo.value.read_errors == finder.read_errors
    assert {e["feature_id"] for e in finder.read_errors} == {1}


def test_some_reads_failing_returns_results_and_errors(make_finder, caplog):
    finder, candidates = make_finder(True, False)
    with caplog.at_level(logging.WARNING):
        results = finder._find_images_per_feature(candidates)
    assert len(results) == 1
    assert len(finder.read_errors) == 1
    assert "1 of 2 image checks failed with read errors" in caplog.text


def test_no_read_errors(make_finder):
    finder, candidates = make_finder(True, True)
    assert len(finder._find_images_per_feature(candidates)) == 2
    assert finder.read_errors == []


def test_no_candidates_does_not_raise(make_finder):
    finder, _ = make_finder()
    assert finder._find_images_per_feature([]) == []
    assert finder.read_errors == []


def test_read_errors_reset_between_searches(make_finder):
    finder, candidates = make_finder(True, False)
    finder._find_images_per_feature(candidates)
    finder._find_images_per_feature(candidates[:1])
    assert finder.read_errors == []
