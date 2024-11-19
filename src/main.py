import argparse
from pathlib import Path
import geopandas as gpd
import datetime
from ceda_s2 import FindS2, ImagePlotter
import matplotlib

matplotlib.use("TkAgg")


def valid_date(date_string):
    try:
        datetime.datetime.strptime(date_string, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date: '{date_string}'. Expected format: YYYY-MM-DD."
        )


def get_images(
    features_path, start_date, end_date, plot_images, download_images, download_path
):
    search_features = gpd.read_file(features_path)
    print(f"Searching for Sentinel 2 images for {search_features.shape[0]} features...")
    s2_finder = FindS2(search_features, start_date, end_date)
    image_features = s2_finder.find_image_links()
    image_count = image_features[image_features["image_links"].notna()].shape[0]
    if image_count > 0:
        if plot_images:
            ImagePlotter(image_features)
    else:
        print(f"{image_count} images found")


def main():
    """
    Parse command-line arguments and start model training.

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
        help="Path to gpkg or shp containing features to search",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="Start date to search for images in YYYY-MM-DD format",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
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
        "--download-path",
        type=str,
        default="outputs",
        help="Path to where to save downloaded images if download flag specified.",
    )

    args = parser.parse_args()

    # Convert paths to Pathlib objects
    features_path = Path(args.search_features)

    # Verify that paths exist
    if not features_path.exists():
        raise FileNotFoundError("Search features path does not exist.")

    valid_date(args.start_date)

    valid_date(args.end_date)

    get_images(
        features_path,
        args.start_date,
        args.end_date,
        args.plot,
        args.download,
        args.download_path,
    )


if __name__ == "__main__":
    main()
