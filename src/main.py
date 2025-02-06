import logging
import argparse
from pathlib import Path
import geopandas as gpd
import datetime
import matplotlib

from ceda_s2 import FindS2, ImagePlotter, ImageDownloader

logging.basicConfig(
    level=logging.INFO,
    format="\n%(asctime)s.%(msecs)03d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler("image_search.log"), logging.StreamHandler()],
)

# docker needs to use tkinter
try:
    matplotlib.use("TkAgg")
except (ImportError, RuntimeError):
    matplotlib.use("Agg")


def valid_date(date_string):
    """
    Validate a date string in the format YYYY-MM-DD.

    Args:
        date_string (str): The date string to validate.

    Raises:
        argparse.ArgumentTypeError: If the date string is not in the expected format.
    """
    try:
        datetime.datetime.strptime(date_string, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date: '{date_string}'. Expected format: YYYY-MM-DD."
        )


def compare_date(d1, d2):
    """
    Compare two date strings to ensure the start date is before the end date.

    Args:
        d1 (str): The start date in YYYY-MM-DD format.
        d2 (str): The end date in YYYY-MM-DD format.

    Raises:
        ValueError: If the start date is not before the end date.
    """
    d1 = datetime.datetime.strptime(d1, "%Y-%m-%d").date()
    d2 = datetime.datetime.strptime(d2, "%Y-%m-%d").date()
    if d2 <= d1:
        raise ValueError("start date must be before end date")


def _save_features_path(features_path, start_date, end_date):
    """
    Generate a new file path for saving search features results.

    Args:
        features_path (Path): The original file path as a `pathlib.Path` object.
        start_date (str): The start date of the search (e.g., "2023-01-01").
        end_date (str): The end date of the search (e.g., "2023-12-31").

    Returns:
        Path: A new file path with a modified name including the start and end dates.
    """
    extn = features_path.suffix
    stem_name = features_path.stem
    output_name = f"{stem_name}_s2_search_{start_date}_{end_date}{extn}"
    return features_path.parent / output_name

def get_images(
    features_path,
    new_search,
    start_date,
    end_date,
    plot_images,
    download_images,
    download_path,
    band_indices,
    tile_cloud_percent,
    feature_cloud_percent,
    min_cloud_only,
):
    """
    Search for Sentinel 2 images based on provided geographical features and date range.

    Args:
        features_path (Path): Path to the file containing geographical features (GeoPackage or Shapefile).
        new_search (bool): Whether a new search or using image links in existing image_link column.
        start_date (str): Start date for the image search in YYYY-MM-DD format.
        end_date (str): End date for the image search in YYYY-MM-DD format.
        plot_images (bool): Whether to plot the images found.
        download_images (bool): Whether to download the images found.
        download_path (str): Path to save downloaded images.
        band_indices (tuple): Tuple of band indices to write when downloading. 
        NOTE: This is rasterio 1-indexed order, not 0 indexed.
        tile_cloud_percent (int): Maximum allowed cloud cover percentage for the entire tile.
        feature_cloud_percent (int): Maximum allowed cloud cover percentage for the specific feature.
        min_cloud_only (bool): If True, only the image with the minimum cloud cover percentage is kept for each feature.

    Returns:
        None
    """
    search_features = gpd.read_file(features_path)
    if new_search:
        if "image_link" in search_features.columns:
            search_features = search_features.drop(columns=["image_link", "image_date"])
            search_features = search_features[~search_features.geometry.duplicated()]
        logging.info(
            f"Searching for Sentinel 2 images for {search_features.shape[0]} features..."
        )
        s2_finder = FindS2(
            search_features,
            start_date,
            end_date,
            check_img_cloud=tile_cloud_percent < 100,
            tile_cloud_max=tile_cloud_percent,
            s2cloudless_max=feature_cloud_percent,
            min_cloud_only=min_cloud_only,
        )
        image_features = s2_finder.find_image_links()
    else:
        logging.info(
            "Search features have existing 'image_link' column values, so using these..."
        )
        if not plot_images and not download_images:
            raise ValueError(
                "Need to specify 'plot' or 'download' arguments to use existing image links."
            )
        image_features = search_features

    image_count = image_features[image_features["image_link"].notna()].shape[0]
    if image_count > 0:
        if new_search:
            save_path = _save_features_path(features_path, start_date, end_date)
            image_features.to_file(save_path)
            logging.info(f"saved search results to {save_path}")
        if plot_images:
            ImagePlotter(image_features)
        if download_images:
            downloader = ImageDownloader(
                image_features, download_path, band_indices=band_indices
            )
            downloader.download_from_gdf()

    else:
        logging.info(f"{image_count} images found")


def main():
    """
    Parse command-line arguments and search for Sentinel images.

    Args:
        None

    Returns:
        None
    """
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Find Sentinel 2 images intersecting search features from the CEDA analysis-ready archive."
    )
    parser.add_argument(
        "--search-features",
        type=str,
        required=True,
        help="Path to gpkg or shp containing features to search. If input already includes image_link field \
             then need to specify `overwrite-search` argument to run a new search, or can plot or download \
             the existing image links depending on arguments specified.",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date to search for images in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        help="End date to search for images in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--plot",
        action="store_true",
        help="Create a plot window to view images found.",
    )

    parser.add_argument(
        "--download",
        action="store_true",
        help="Download the images found as geotiffs.",
    )

    parser.add_argument(
        "--overwrite-search",
        action="store_true",
        help="If existing image_link column in search features ignore, search again and overwrite.",
    )

    parser.add_argument(
        "--download-path",
        type=str,
        default="outputs",
        help="Path to where to save downloaded images if download flag specified. Defaults to outputs.",
    )

    parser.add_argument(
        "--download-band-indices",
        nargs="+",
        type=int,
        default=[1, 2, 3, 7],
        help="Indices of the bands wish to download from Sentinel 2 image. \
                        Uses 1-indexed Rasterio values and defaults to B,G,R,NiR using [1,2,3,7].\
                        Specify as space separated numbers e.g. '--download-band-indices 1 2 3'",
    )

    parser.add_argument(
        "--tile-cloud-percent",
        type=float,
        default=100.0,
        help="Percentage of cloud cover to filter images by using image metadata. \
            Default is 100.0 (percent, no filter).",
    )

    parser.add_argument(
        "--feature-cloud-percent",
        type=float,
        default=10.0,
        help="Percentage of cloud cover to filter feature image windows by using s2cloudless mask.\
              Default is 10.0 (percent).",
    )

    parser.add_argument(
        "--min-cloud-only",
        action="store_true",
        help="Only the least cloudy image for each feature is retained.",
    )

    args = parser.parse_args()

    # Convert paths to Pathlib objects
    features_path = Path(args.search_features)

    # Verify that paths exist
    if not features_path.exists():
        raise FileNotFoundError("Search features path does not exist.")

    search_features = gpd.read_file(features_path)
    new_search = (
        "image_link" not in search_features.columns
        or search_features["image_link"].isna().all()
        or args.overwrite_search
    )
    if new_search:
        if args.start_date is None or args.end_date is None:
            raise ValueError(
                "For a new search must specify start-date and end-date arguments."
            )

        valid_date(args.start_date)

        valid_date(args.end_date)

        compare_date(args.start_date, args.end_date)

    band_indices = tuple(args.download_band_indices)
    if band_indices:
        if not all(0 < x <= 10 for x in band_indices):
            raise ValueError("Band index values must be in the range 1-10.")

    tile_cloud = float(args.tile_cloud_percent)
    if tile_cloud > 100 or tile_cloud < 0:
        raise ValueError("Tile cloud percentage must be between 0 and 100.")

    feature_cloud = float(args.feature_cloud_percent)
    if feature_cloud > 100 or feature_cloud < 0:
        raise ValueError("Feature cloud percentage must be between 0 and 100.")

    get_images(
        features_path,
        new_search,
        args.start_date,
        args.end_date,
        args.plot,
        args.download,
        args.download_path,
        band_indices,
        tile_cloud,
        feature_cloud,
        args.min_cloud_only,
    )


if __name__ == "__main__":
    main()
