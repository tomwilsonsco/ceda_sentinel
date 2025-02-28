import argparse
import logging
from ceda_s1 import FindS1
from pathlib import Path
import pickle
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="\n%(asctime)s.%(msecs)03d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler("image_search.log"), logging.StreamHandler()],
)


def validate_date(date_str):
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        if date < datetime(2018, 1, 1):
            raise argparse.ArgumentTypeError("Date cannot be earlier than 2018-01-01.")
        return date_str
    except ValueError:
        raise argparse.ArgumentTypeError("Invalid date format. Use 'YYYY-MM-DD'.")


def main():
    parser = argparse.ArgumentParser(
        description="Search for Sentinel-1 data within a \
                                     specified date range from CEDA archive."
    )
    parser.add_argument(
        "--start_date",
        type=validate_date,
        help="The start date for the search in the format 'YYYY-MM-DD'.",
    )
    parser.add_argument(
        "--end_date",
        type=validate_date,
        help="The end date for the search in the format 'YYYY-MM-DD'.",
    )
    parser.add_argument(
        "--orbit_numbers",
        type=int,
        nargs="+",
        default=[30, 52, 103, 125, 132],
        help="A list of relative orbit numbers to filter results by. \
                            Should be space separated. Defaults to 30 52 103 125 132.",
    )
    parser.add_argument(
        "--aoi_filepath",
        type=str,
        help="The file path to the area of interest (AOI) shapefile. \
            If specified, images will be checked within this AOI \
                unless --no_orbit_filter is also specified.",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="outputs",
        help="The directory to save the output pickle file. Defaults to 'outputs'.",
    )
    parser.add_argument(
        "--no_orbit_filter",
        action="store_false",
        help="If specified, orbits will not be filtered to one orbit number \
            for descending and ascending only.",
    )

    args = parser.parse_args()

    finder = FindS1(
        args.start_date,
        args.end_date,
        args.aoi_filepath,
        args.orbit_numbers,
        args.no_orbit_filter,
    )
    img_list = finder.get_img_list()
    logging.info(f"Found {len(img_list)} images in the date range.")
    logging.info(f"First 5 records: {img_list[:5]}")

    # Create output directory if it doesn't exist
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate output file name
    orbit_numbers_str = "_".join(map(str, args.orbit_numbers))
    output_file_name = (
        f"s1_links_{orbit_numbers_str}_{args.start_date}_{args.end_date}.pkl"
    )
    output_file_path = output_dir / output_file_name

    # Save img_list to pickle file
    with open(output_file_path, "wb") as f:
        pickle.dump(img_list, f)

    logging.info(f"Image links saved to {output_file_path}")


if __name__ == "__main__":
    main()
