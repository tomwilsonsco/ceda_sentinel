"""
Unit tests for the window used by the S2 nodata and cloud checks: the optional
check_buffer and features that fall partly outside an image.

Images are small local GeoTIFFs: 10 x 10 pixels of 10 m, covering x 0-100 and
y 0-100 (EPSG:27700).
"""

from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pytest
import rasterio as rio
from ceda_s2 import FindS2, FindS2STAC
from ceda_stac.client import S2_CLOUD_ASSET
from rasterio.transform import from_origin
from shapely.geometry import box

# 2 x 2 pixels: rows 4-5, columns 4-5
SMALL_FEATURE = box(40, 40, 60, 60)
# Half outside the right-hand edge of the image
EDGE_FEATURE = box(80, 20, 120, 60)


def write_tif(path, data):
    with rio.open(
        path,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="uint8",
        crs="EPSG:27700",
        transform=from_origin(0, 100, 10, 10),
        nodata=0,
    ) as dst:
        dst.write(data[np.newaxis].astype("uint8"))


@pytest.fixture
def images(tmp_path):
    """Writes a fully valid image and a clear cloud mask, returning both paths."""
    image = tmp_path / "S2_vmsk_sharp_rad_srefdem_stdsref.tif"
    cloud = tmp_path / "S2_clouds.tif"
    write_tif(image, np.ones((10, 10)))
    write_tif(cloud, np.zeros((10, 10)))
    return str(image), str(cloud)


@pytest.fixture(params=[FindS2, FindS2STAC], ids=["FindS2", "STAC"])
def finder_cls(request):
    return request.param


def make_finder(finder_cls, geometry, **kwargs):
    gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[geometry], crs=27700)
    return finder_cls(gdf, "2024-06-01", "2024-06-07", **kwargs), gdf.iloc[0]


def cloud_percent(finder, row, images):
    image, cloud = images
    if isinstance(finder, FindS2STAC):
        item = SimpleNamespace(
            id="item", assets={S2_CLOUD_ASSET: SimpleNamespace(href=cloud)}
        )
        return finder._s2_cloudless_filter(row, item)
    return finder._s2_cloudless_filter(row, image)


def test_default_buffer_checks_feature_bounds_only(finder_cls, images):
    # Cloudy pixel just right of the feature (row 4, column 6)
    mask = np.zeros((10, 10))
    mask[4, 6] = 1
    write_tif(images[1], mask)
    finder, row = make_finder(finder_cls, SMALL_FEATURE)
    assert cloud_percent(finder, row, images) == 0.0


def test_buffer_includes_nearby_cloud(finder_cls, images):
    mask = np.zeros((10, 10))
    mask[4, 6] = 1
    write_tif(images[1], mask)
    # 10 m buffer gives a 4 x 4 pixel window, of which one pixel is cloud
    finder, row = make_finder(finder_cls, SMALL_FEATURE, check_buffer=10)
    assert cloud_percent(finder, row, images) == pytest.approx(100 / 16)


def test_buffer_applies_to_nodata_check(finder_cls, images):
    # Nodata ring around the feature: none inside it, 12 of 16 pixels with buffer
    data = np.ones((10, 10))
    data[3:7, 3:7] = 0
    data[4:6, 4:6] = 1
    write_tif(images[0], data)
    finder, row = make_finder(finder_cls, SMALL_FEATURE, nodata_max=50)
    assert finder._no_data_filter(row, images[0])
    finder, row = make_finder(finder_cls, SMALL_FEATURE, nodata_max=50, check_buffer=10)
    assert not finder._no_data_filter(row, images[0])


def test_feature_partly_outside_image_counts_as_nodata(finder_cls, images):
    # Half the feature is off the image, so 50% nodata
    finder, row = make_finder(finder_cls, EDGE_FEATURE, nodata_max=60)
    assert finder._no_data_filter(row, images[0])
    finder, row = make_finder(finder_cls, EDGE_FEATURE, nodata_max=40)
    assert not finder._no_data_filter(row, images[0])


def test_cloud_percent_is_of_feature_inside_image(finder_cls, images):
    # Inside part is columns 8-9, rows 4-7: 8 pixels, 2 of them cloud
    mask = np.zeros((10, 10))
    mask[4:6, 9] = 1
    write_tif(images[1], mask)
    finder, row = make_finder(finder_cls, EDGE_FEATURE)
    assert cloud_percent(finder, row, images) == pytest.approx(25.0)
