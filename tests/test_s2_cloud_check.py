"""
Unit tests for the Sentinel-2 per-feature cloud check (FindS2 and FindS2STAC).

The raster filters are mocked so no network access is needed.
"""

from types import SimpleNamespace

import geopandas as gpd
import pytest
from ceda_s2 import FindS2, FindS2STAC
from ceda_stac.client import S2_COG_ASSET
from shapely.geometry import box

S2CLOUDLESS_MAX = 10
IMAGE_LINK = (
    "https://example.com/S2A_20240601_T30VVJ_vmsk_sharp_rad_srefdem_stdsref.tif"
)


@pytest.fixture
def aoi_gdf():
    return gpd.GeoDataFrame(
        {"id": [1]}, geometry=[box(300000, 700000, 300100, 700100)], crs=27700
    )


def make_find_s2(aoi_gdf, monkeypatch, cloud_percent):
    finder = FindS2(
        aoi_gdf=aoi_gdf,
        start_date="2024-06-01",
        end_date="2024-06-07",
        s2cloudless_max=S2CLOUDLESS_MAX,
    )
    monkeypatch.setattr(finder, "_img_bounds_filter", lambda row, link: True)
    monkeypatch.setattr(finder, "_no_data_filter", lambda row, link: True)
    monkeypatch.setattr(finder, "_s2_cloudless_filter", lambda row, link: cloud_percent)
    monkeypatch.setattr(finder, "_filter_tiles_feature", lambda row: ["T30VVJ"])
    return finder, IMAGE_LINK


def make_find_s2_stac(aoi_gdf, monkeypatch, cloud_percent):
    finder = FindS2STAC(
        aoi_gdf=aoi_gdf,
        start_date="2024-06-01",
        end_date="2024-06-07",
        s2cloudless_max=S2CLOUDLESS_MAX,
    )
    monkeypatch.setattr(finder, "_img_bounds_filter", lambda row, item: True)
    monkeypatch.setattr(finder, "_no_data_filter", lambda row, link: True)
    monkeypatch.setattr(finder, "_s2_cloudless_filter", lambda row, item: cloud_percent)
    monkeypatch.setattr(finder, "_extract_date_from_item", lambda item: "2024-06-01")
    item = SimpleNamespace(
        id="S2A_20240601_T30VVJ",
        assets={S2_COG_ASSET: SimpleNamespace(href=IMAGE_LINK)},
    )
    return finder, item


@pytest.fixture(params=[make_find_s2, make_find_s2_stac], ids=["FindS2", "STAC"])
def make_finder(request, aoi_gdf, monkeypatch, tmp_path):
    # The constructors write image_search.log to the working directory
    monkeypatch.chdir(tmp_path)
    return lambda cloud_percent: request.param(aoi_gdf, monkeypatch, cloud_percent)


@pytest.mark.parametrize(
    ("cloud_percent", "expected"),
    [
        (0.0, (True, 0.0)),
        (0.5, (True, 0.5)),
        (3.7, (True, 3.7)),
        (S2CLOUDLESS_MAX, (False, S2CLOUDLESS_MAX)),
        (55.0, (False, 55.0)),
        (None, (False, None)),
    ],
)
def test_validate_feature_image(make_finder, aoi_gdf, cloud_percent, expected):
    finder, image = make_finder(cloud_percent)
    row = aoi_gdf.iloc[0]
    assert finder._validate_feature_image(row, image) == expected


@pytest.mark.parametrize("cloud_percent", [0.0, 0.5, 3.7])
def test_clear_images_are_kept_with_float_percent(make_finder, cloud_percent):
    finder, image = make_finder(cloud_percent)
    results = finder._find_images_per_feature([image])
    assert len(results) == 1
    assert results[0]["image_link"] == IMAGE_LINK
    assert results[0]["s2cloudles"] == cloud_percent
    assert isinstance(results[0]["s2cloudles"], float)


@pytest.mark.parametrize("cloud_percent", [55.0, None])
def test_cloudy_or_unreadable_images_are_dropped(make_finder, cloud_percent):
    finder, image = make_finder(cloud_percent)
    assert finder._find_images_per_feature([image]) == []
