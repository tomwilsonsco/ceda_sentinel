import argparse
from pathlib import Path
import geopandas as gpd
import datetime
import matplotlib

from ceda_s2 import FindS2, ImagePlotter, ImageDownloader

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

    Returns:
        None
    """
    search_features = gpd.read_file(features_path)
    if new_search:
        if "image_link" in search_features.columns:
            search_features = search_features.drop(columns=["image_link", "image_date"])
            search_features = search_features[~search_features.geometry.duplicated()]
        print(
            f"Searching for Sentinel 2 images for {search_features.shape[0]} features..."
        )
        s2_finder = FindS2(search_features, start_date, end_date)
        image_features = s2_finder.find_image_links()
    else:
        print(
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
            print(f"saved search results to {save_path}")
        if plot_images:
            ImagePlotter(image_features)
        if download_images:
            downloader = ImageDownloader(image_features, download_path)
            downloader.download_from_gdf()

    else:
        print(f"{image_count} images found")


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
        description="Find Sentinel images from CEDA analysis-ready archive."
    )
    parser.add_argument(
        "--search-features",
        type=str,
        required=True,
        help="Path to gpkg or shp containing features to search. If already includes image_link field\
             then will not run new search but can plot or download these image links depending on arguments specified",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date to search for images in YYYY-MM-DD format",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        help="End date to search for images in YYYY-MM-DD format",
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
        help="If existing image_link column in search features don't use it and search again.",
    )

    parser.add_argument(
        "--download-path",
        type=str,
        default="outputs",
        help="Path to where to save downloaded images if download flag specified. Defaults to outputs.",
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

    get_images(
        features_path,
        new_search,
        args.start_date,
        args.end_date,
        args.plot,
        args.download,
        args.download_path,
    )


if __name__ == "__main__":
    main()
