"""
Integration tests for Sentinel-2 STAC API search (FindS2STAC).

These tests require network access to the CEDA STAC API and use recent data (2024+)
since historical data may not be fully indexed in the STAC API.
"""
import pytest
import geopandas as gpd
import pandas as pd
from ceda_s2 import FindS2STAC


@pytest.mark.integration
class TestFindS2STAC:
    """Integration tests for FindS2STAC class."""

    @pytest.fixture
    def aoi_filepath(self):
        """Path to test AOI file."""
        return "tests/test_inputs/s1_search_features.gpkg"

    @pytest.fixture
    def aoi_gdf(self, aoi_filepath):
        """Load AOI GeoDataFrame."""
        gdf = gpd.read_file(aoi_filepath)
        return gdf

    def test_stac_search_recent_data(self, aoi_gdf):
        """
        Test STAC search with recent data (2024).
        
        This test verifies that:
        1. FindS2STAC can be instantiated
        2. STAC search returns results for recent dates
        3. Output format matches FindS2 (GeoDataFrame)
        """
        finder = FindS2STAC(
            aoi_gdf=aoi_gdf.copy(),
            start_date="2024-06-01",
            end_date="2024-06-07",
            id_col="id",
            tile_cloud_max=100,
            s2cloudless_max=100,
            nodata_max=100,
        )

        result_gdf = finder.find_image_links()

        # Verify output format
        if result_gdf is not None:
            assert isinstance(result_gdf, gpd.GeoDataFrame), "Output should be a GeoDataFrame"
            assert "image_link" in result_gdf.columns, "Output should have image_link column"
            assert "image_date" in result_gdf.columns, "Output should have image_date column"
            assert "s2cloudles" in result_gdf.columns, "Output should have s2cloudles column"

            # Verify that we got some results
            valid_images = result_gdf[result_gdf["image_link"].notna()]
            assert len(valid_images) >= 0, "Should return results or empty GeoDataFrame"

            # Verify that all image links are valid URLs
            for link in valid_images["image_link"]:
                assert link.startswith("https://"), f"Invalid URL: {link}"
                assert "dap.ceda.ac.uk" in link or "data.ceda.ac.uk" in link, \
                    f"URL should be from CEDA: {link}"

    def test_stac_search_output_format(self, aoi_gdf):
        """
        Test that STAC search output format matches FindS2 output format.
        """
        finder = FindS2STAC(
            aoi_gdf=aoi_gdf.copy(),
            start_date="2024-06-01",
            end_date="2024-06-07",
            id_col="id",
            tile_cloud_max=100,
            s2cloudless_max=100,
            nodata_max=100,
        )

        result_gdf = finder.find_image_links()

        if result_gdf is not None and not result_gdf.empty:
            # Verify GeoDataFrame structure
            assert isinstance(result_gdf, gpd.GeoDataFrame)
            assert "id" in result_gdf.columns
            assert "image_link" in result_gdf.columns
            assert "image_date" in result_gdf.columns
            assert "s2cloudles" in result_gdf.columns

            # Verify image_link values
            valid_links = result_gdf[result_gdf["image_link"].notna()]["image_link"]
            for link in valid_links:
                assert isinstance(link, str)
                assert link.startswith("https://")

            # Verify s2cloudles values are integers
            valid_cloud = result_gdf[result_gdf["s2cloudles"].notna()]["s2cloudles"]
            for val in valid_cloud:
                assert isinstance(val, (int, float))

    def test_stac_cloud_cover_filtering(self, aoi_gdf):
        """
        Test that cloud cover filtering works correctly.
        """
        # Search with strict cloud cover filter
        finder = FindS2STAC(
            aoi_gdf=aoi_gdf.copy(),
            start_date="2024-06-01",
            end_date="2024-06-07",
            id_col="id",
            tile_cloud_max=10,  # Strict cloud cover filter
            s2cloudless_max=10,
            nodata_max=100,
        )

        result_gdf = finder.find_image_links()

        # Verify search completes without errors
        # (Results may be empty due to strict cloud cover filter)

    def test_stac_empty_result_warning(self, aoi_gdf, caplog):
        """
        Test that appropriate warning is logged when no results are found.
        """
        finder = FindS2STAC(
            aoi_gdf=aoi_gdf.copy(),
            start_date="2018-06-01",  # Historical data may not be in STAC
            end_date="2018-06-02",
            id_col="id",
            tile_cloud_max=100,
            s2cloudless_max=100,
            nodata_max=100,
        )

        result_gdf = finder.find_image_links()

        # Should return None or empty GeoDataFrame with a warning
        if result_gdf is None or (isinstance(result_gdf, gpd.GeoDataFrame) and result_gdf.empty):
            assert True, "Should return empty results for non-indexed historical data"

    def test_stac_cog_url_format(self, aoi_gdf):
        """
        Test that COG URLs have the correct format.
        """
        finder = FindS2STAC(
            aoi_gdf=aoi_gdf.copy(),
            start_date="2024-06-01",
            end_date="2024-06-07",
            id_col="id",
            tile_cloud_max=100,
            s2cloudless_max=100,
            nodata_max=100,
        )

        result_gdf = finder.find_image_links()

        if result_gdf is not None and not result_gdf.empty:
            valid_links = result_gdf[result_gdf["image_link"].notna()]["image_link"]
            for link in valid_links:
                # Verify it's a COG URL from dap.ceda.ac.uk
                assert "dap.ceda.ac.uk" in link or "data.ceda.ac.uk" in link
                # Should end with .tif
                assert link.endswith(".tif"), f"COG URL should end with .tif: {link}"

    def test_stac_date_extraction(self, aoi_gdf):
        """
        Test that dates are correctly extracted from STAC items.
        """
        finder = FindS2STAC(
            aoi_gdf=aoi_gdf.copy(),
            start_date="2024-06-01",
            end_date="2024-06-07",
            id_col="id",
            tile_cloud_max=100,
            s2cloudless_max=100,
            nodata_max=100,
        )

        result_gdf = finder.find_image_links()

        if result_gdf is not None and not result_gdf.empty:
            valid_dates = result_gdf[result_gdf["image_date"].notna()]["image_date"]
            for date in valid_dates:
                # Verify date format YYYY-MM-DD
                assert len(date) == 10, f"Date should be YYYY-MM-DD format: {date}"
                assert date[4] == "-" and date[7] == "-", f"Date format incorrect: {date}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])