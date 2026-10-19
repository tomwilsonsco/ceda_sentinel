"""
Unit tests for ceda_stac.client module.

These tests verify the utility functions and constants in the shared STAC client module.
"""

import pytest

from ceda_stac.client import (
    CEDA_STAC_API_URL,
    S1_ARD_COLLECTION,
    S1_DATA_ASSET,
    S1_METADATA_ASSET,
    S2_ARD_COLLECTION,
    S2_CLOUD_ASSET,
    S2_COG_ASSET,
    extract_cloud_url_from_item,
    extract_date_from_item,
    extract_image_url_from_item,
    extract_tile_from_item_id,
    format_datetime_range,
    is_gb_osgb_item,
)


class TestConstants:
    """Test that constants are correctly defined."""

    def test_api_url(self):
        """Test that the API URL is correctly set."""
        assert CEDA_STAC_API_URL == "https://api.stac.ceda.ac.uk/"
        assert CEDA_STAC_API_URL.startswith("https://")
        assert "stac.ceda.ac.uk" in CEDA_STAC_API_URL

    def test_s1_collection(self):
        """Test that S1 collection ID is correct."""
        assert S1_ARD_COLLECTION == "sentinel1_ard"
        assert isinstance(S1_ARD_COLLECTION, str)

    def test_s2_collection(self):
        """Test that S2 collection ID is correct."""
        assert S2_ARD_COLLECTION == "sentinel2_ard"
        assert isinstance(S2_ARD_COLLECTION, str)

    def test_s1_asset_keys(self):
        """Test that S1 asset keys are defined."""
        assert S1_DATA_ASSET == "data"
        assert S1_METADATA_ASSET == "metadata"
        assert isinstance(S1_DATA_ASSET, str)
        assert isinstance(S1_METADATA_ASSET, str)

    def test_s2_asset_keys(self):
        """Test that S2 asset keys are defined."""
        assert S2_COG_ASSET == "cog"
        assert S2_CLOUD_ASSET == "cloud"
        assert isinstance(S2_COG_ASSET, str)
        assert isinstance(S2_CLOUD_ASSET, str)


class TestFormatDatetimeRange:
    """Test the format_datetime_range function."""

    def test_basic_format(self):
        """Test basic datetime range formatting."""
        result = format_datetime_range("2024-06-01", "2024-06-30")
        expected = "2024-06-01T00:00:00Z/2024-06-30T23:59:59Z"
        assert result == expected

    def test_single_day(self):
        """Test datetime range for a single day."""
        result = format_datetime_range("2024-06-15", "2024-06-15")
        expected = "2024-06-15T00:00:00Z/2024-06-15T23:59:59Z"
        assert result == expected

    def test_year_boundary(self):
        """Test datetime range across year boundary."""
        result = format_datetime_range("2023-12-31", "2024-01-01")
        expected = "2023-12-31T00:00:00Z/2024-01-01T23:59:59Z"
        assert result == expected

    def test_leap_year(self):
        """Test datetime range in a leap year."""
        result = format_datetime_range("2024-02-28", "2024-02-29")
        expected = "2024-02-28T00:00:00Z/2024-02-29T23:59:59Z"
        assert result == expected

    def test_return_type(self):
        """Test that the function returns a string."""
        result = format_datetime_range("2024-01-01", "2024-01-31")
        assert isinstance(result, str)

    def test_contains_time_component(self):
        """Test that the result includes time components."""
        result = format_datetime_range("2024-06-01", "2024-06-30")
        assert "T00:00:00Z" in result
        assert "T23:59:59Z" in result

    def test_contains_z_suffix(self):
        """Test that the result uses Z (UTC) timezone indicator."""
        result = format_datetime_range("2024-06-01", "2024-06-30")
        assert result.count("Z") == 2  # One for start, one for end


class TestExtractTileFromItemId:
    """Test the extract_tile_from_item_id function."""

    def test_standard_tile_id(self):
        """Test extraction of standard MGRS tile ID."""
        item_id = "neodc.sentinel_ard.data.sentinel_2.2024.06.24.S2A_20240624_latn554lonw0006_T30UXG_ORB137_20240624131003_utm30n_osgb"
        result = extract_tile_from_item_id(item_id)
        assert result == "T30UXG"

    def test_different_tile_id(self):
        """Test extraction of different MGRS tile ID."""
        item_id = "neodc.sentinel_ard.data.sentinel_2.2024.06.24.S2A_20240624_latn554lonw0006_T30UXF_ORB137_20240624131003_utm30n_osgb"
        result = extract_tile_from_item_id(item_id)
        assert result == "T30UXF"

    def test_no_tile_id(self):
        """Test when no tile ID is present."""
        item_id = "neodc.sentinel_ard.data.sentinel_1.2024.06.02.S1A_20240602_1_asc_181637_181702_VVVH_G0_GB_OSGB_RTCK_SpkRL"
        result = extract_tile_from_item_id(item_id)
        assert result is None

    def test_invalid_format(self):
        """Test with invalid item ID format."""
        item_id = "invalid_item_id"
        result = extract_tile_from_item_id(item_id)
        assert result is None

    def test_empty_string(self):
        """Test with empty string."""
        result = extract_tile_from_item_id("")
        assert result is None


class TestExtractDateFromItem:
    """Test the extract_date_from_item function."""

    def test_standard_datetime(self):
        """Test extraction from standard ISO datetime."""
        item = {"properties": {"datetime": "2024-06-02T18:16:37Z"}}

        # Mock object with properties attribute
        class MockItem:
            def __init__(self, properties):
                self.properties = properties

        result = extract_date_from_item(MockItem(item["properties"]))
        assert result == "2024-06-02"

    def test_different_datetime(self):
        """Test extraction from different datetime."""

        class MockItem:
            def __init__(self, properties):
                self.properties = properties

        result = extract_date_from_item(MockItem({"datetime": "2024-12-31T23:59:59Z"}))
        assert result == "2024-12-31"

    def test_no_datetime_property(self):
        """Test when datetime property is missing."""

        class MockItem:
            def __init__(self, properties):
                self.properties = properties

        result = extract_date_from_item(MockItem({}))
        assert result is None

    def test_invalid_datetime_format(self):
        """Test with invalid datetime format."""

        class MockItem:
            def __init__(self, properties):
                self.properties = properties

        # Should still work if there's a T separator
        result = extract_date_from_item(MockItem({"datetime": "invalid"}))
        assert result == "invalid"


class TestExtractImageUrlFromItem:
    """Test the extract_image_url_from_item function."""

    def test_extract_data_asset(self):
        """Test extracting data asset URL."""

        class MockAsset:
            def __init__(self, href):
                self.href = href

        class MockItem:
            def __init__(self, assets):
                self.assets = assets

        item = MockItem(
            {
                "data": MockAsset(
                    "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2024/06/02/test.tif"
                )
            }
        )

        result = extract_image_url_from_item(item, "data")
        assert (
            result
            == "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2024/06/02/test.tif"
        )

    def test_extract_cog_asset(self):
        """Test extracting COG asset URL."""

        class MockAsset:
            def __init__(self, href):
                self.href = href

        class MockItem:
            def __init__(self, assets):
                self.assets = assets

        item = MockItem(
            {
                "cog": MockAsset(
                    "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_2/2024/06/02/test.tif"
                )
            }
        )

        result = extract_image_url_from_item(item, "cog")
        assert (
            result
            == "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_2/2024/06/02/test.tif"
        )

    def test_missing_asset(self):
        """Test when asset key is missing."""

        class MockItem:
            def __init__(self, assets):
                self.assets = assets

        item = MockItem({})
        result = extract_image_url_from_item(item, "data")
        assert result is None


class TestExtractCloudUrlFromItem:
    """Test the extract_cloud_url_from_item function."""

    def test_extract_cloud_asset(self):
        """Test extracting cloud asset URL."""

        class MockAsset:
            def __init__(self, href):
                self.href = href

        class MockItem:
            def __init__(self, assets):
                self.assets = assets

        item = MockItem(
            {
                "cloud": MockAsset(
                    "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_2/2024/06/02/clouds.tif"
                )
            }
        )

        result = extract_cloud_url_from_item(item)
        assert (
            result
            == "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_2/2024/06/02/clouds.tif"
        )

    def test_missing_cloud_asset(self):
        """Test when cloud asset is missing."""

        class MockItem:
            def __init__(self, assets):
                self.assets = assets

        item = MockItem({})
        result = extract_cloud_url_from_item(item)
        assert result is None


class TestIsGbOsgbItem:
    """Test the is_gb_osgb_item function."""

    def test_s1_gb_osgb(self):
        """Test S1 item with GB_OSGB in data asset."""

        class MockAsset:
            def __init__(self, href):
                self.href = href

        class MockItem:
            def __init__(self, assets):
                self.assets = assets

        item = MockItem(
            {
                "data": MockAsset(
                    "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2024/06/02/S1A_20240602_1_asc_GB_OSGB_RTCK_SpkRL.tif"
                )
            }
        )

        assert is_gb_osgb_item(item) is True

    def test_s1_non_gb_osgb(self):
        """Test S1 item without GB_OSGB in data asset."""

        class MockAsset:
            def __init__(self, href):
                self.href = href

        class MockItem:
            def __init__(self, assets):
                self.assets = assets

        item = MockItem(
            {
                "data": MockAsset(
                    "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2024/06/02/S1A_20240602_1_asc_NI_TM65_RTCK_SpkRL.tif"
                )
            }
        )

        assert is_gb_osgb_item(item) is False

    def test_s2_osgb(self):
        """Test S2 item with osgb in cog asset."""

        class MockAsset:
            def __init__(self, href):
                self.href = href

        class MockItem:
            def __init__(self, assets):
                self.assets = assets

        item = MockItem(
            {
                "cog": MockAsset(
                    "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_2/2024/06/02/S2A_20240624_osgb_test.tif"
                )
            }
        )

        assert is_gb_osgb_item(item) is True

    def test_item_without_assets(self):
        """Test item without relevant assets."""

        class MockItem:
            def __init__(self, assets):
                self.assets = assets

        item = MockItem({})
        assert is_gb_osgb_item(item) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
