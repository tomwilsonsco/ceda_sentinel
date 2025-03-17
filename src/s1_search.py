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
            If specified, images will be checked within this AOI.",
    )
    parser.add_argument(
        "--aoi-id",
        type=str,
        default="OBJECTID",
        help="The name of the field containing unique ids for aoi features. \
            Defaults to OBJECTID.",
    )
    parser.add_argument(
        "--image-links-pkl",
        type=str,
        help="The file path to pickle file containing dict of image links per aoi feature.\
            If not specified will search for images.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="The base directory to save the outputs. Defaults to 'outputs/<aoi_file_name>'. \
            A subdirectory with results is created for each polygon feauture in the AOI file.",
    )

    parser.add_argument(
        "--download-all",
        action="store_true",
        help="If specified, all S1 images in date range for aoi window are downloaded to tif.",
    )
    parser.add_argument(
        "--download-tifs",
        action="store_true",
        help="If specified, images downloaded as separate tif files, \
            otherwise one npz file created per feature with dict of image name \
            image array",
    )
    parser.add_argument(
        "--no-ratio",
        action="store_false",
        help="If specified, no VV - VH ratio band is calculated before downloading images.",
    )
    parser.add_argument(
        "--feature-ids",
        type=int,
        nargs="+",
        help="Optional list of ids to download images for if wish to test subset \
            without long download times. Should be space separated.",
    )

    args = parser.parse_args()

    if not args.image_links_pkl:
        if not (args.start_date and args.end_date and args.aoi_filepath):
            parser.error(
                "--start-date, --end-date, \
                         and --aoi-filepath must be specified if --image-links-pkl is not provided."
            )

        finder = FindS1(
            start_date=args.start_date,
            end_date=args.end_date,
            orbit_numbers=args.orbit_numbers,
            aoi_filepath=args.aoi_filepath,
            aoi_id=args.aoi_id,
        )
        img_dict = finder.get_img_feature_dict()

        # Create output directory if it doesn't exist
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate output file name
        aoi_file_name = Path(args.aoi_filepath).stem
        output_file_name = (
            f"s1_links_{aoi_file_name}_{args.start_date}_{args.end_date}.pkl"
        )
        output_file_path = output_dir / output_file_name

        # Save img_list to pickle file
        with open(output_file_path, "wb") as f:
            pickle.dump(img_dict, f)

        logging.info(f"Image link dict saved to {output_file_path}")

    if args.image_links_pkl:
        if not args.download_all:
            parser.error(
                "--download-all must be specified if --image-links-pkl is provided."
            )
        try:
            with open(args.image_links_pkl, "rb") as f:
                img_dict = pickle.load(f)
        except FileNotFoundError:
            logging.error(f"File {args.image_links_pkl} not found.")
            return

    if args.download_all and img_dict:

        download_all = args.download_all if args.download_all else False

        download_tifs = args.download_tifs if args.download_tifs else False

        downloader = S1Downloader(
            image_links=img_dict,
            aoi_filepath=args.aoi_filepath,
            output_dir=args.output_dir,
            tif_output=download_tifs,
            aoi_id=args.aoi_id,
            feature_ids=args.feature_ids,
            ratio_band=args.no_ratio,
            download_all=download_all,
        )
        downloader.download_images()


if __name__ == "__main__":
    main()
