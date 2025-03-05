import argparse
import logging
from ceda_s1 import FindS1, S1Downloader
from pathlib import Path
import pickle
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="\n%(asctime)s.%(msecs)03d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
                logging.FileHandler("s1_image_search.log", mode="w"),
                logging.StreamHandler(),
            ],
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
        "--start-date",
        type=validate_date,
        help="The start date for the search in the format 'YYYY-MM-DD'.",
    )
    parser.add_argument(
        "--end-date",
        type=validate_date,
        help="The end date for the search in the format 'YYYY-MM-DD'.",
    )
    parser.add_argument(
        "--orbit-numbers",
        type=int,
        nargs="+",
        default=[30, 52, 103, 125, 132],
        help="A list of relative orbit numbers to filter results by. \
                            Should be space separated. Defaults to 30 52 103 125 132.",
    )
    parser.add_argument(
        "--aoi-filepath",
        type=str,
        help="The file path to the area of interest (AOI) shapefile. \
            If specified, images will be checked within this AOI \
                unless --no_orbit_filter is also specified. \
            NOTE: Currently designed to process one AOI polygon per file",
    )
    parser.add_argument(
        "--image-links-pkl",
        type=str,
        help="The file path to pickle file containing list of image links.\
            If not specified will search for images.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="The directory to save the output pickle file. Defaults to 'outputs'.",
    )
    parser.add_argument(
        "--no-orbit-filter",
        action="store_false",
        help="If specified, orbits will not be filtered to one orbit number \
            for descending and ascending only.",
    )

    parser.add_argument(
        "--download-all",
        action="store_true",
        help="If specified, all S1 images in date range for aoi window are downloaded to tif.",
    )
    parser.add_argument(
        "--download-median",
        action="store_true",
        help="If specified, median composite for ascending, descending orbits downloaded to tif.",
    )

    parser.add_argument(
        "--no-ratio",
        action="store_false",
        help="If specified, no VV - VH ratio band is calculated before downloading images.",
    )

    args = parser.parse_args()

    if not args.image_links_pkl:
        if not (args.start_date and args.end_date and args.aoi_filepath):
            parser.error(
                "--start-date, --end-date, \
                         and --aoi-filepath must be specified if --image-links-pkl is not provided."
            )

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

    if args.image_links_pkl:
        if not (args.download_all or args.download_median):
            parser.error("--download-all or --download-median must be specified.")
        try:
            with open(args.image_links_pkl, "rb") as f:
                img_list = pickle.load(f)
        except FileNotFoundError:
            logging.error(f"File {args.image_links_pkl} not found.")
            return


    if (args.download_all or args.download_median) and img_list:
        
        download_median = args.download_median if args.download_median else False

        dowload_all = args.download_all if args.download_all else False

        if args.start_date and args.end_date:
            median_name = f"s1_median_{args.start_date}_{args.end_date}_{Path(args.aoi_filepath).stem}"
        else:
            median_name = f"s1_median_{Path(args.aoi_filepath).stem}"
        
        downloader = S1Downloader(
            img_list,
            args.aoi_filepath,
            args.output_dir,
            args.no_ratio,
            download_all=dowload_all,
            median_composite=download_median,
            median_name=median_name,
        )
        downloader.download_images()


if __name__ == "__main__":
    main()
