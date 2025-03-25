import subprocess
import sys
import pickle
from pathlib import Path
from get_data_s1 import get_img_list, get_feature_links
import numpy as np
import pytest


def test_s1_search_integration(tmp_path):
    """
    Integration test for running the s1_search.py script.

    Tests the command:
      python src/s1_search.py --start-date 2018-06-01 --end-date 2018-06-02
            --aoi-filepath inputs/s1_search_features.gpkg --output-dir outputs --aoi-id id

    It uses a temporary directory for inputs and outputs (under tmp_path) and then compares the
    generated pickle files with the expected ones stored under tests/expected.
    """

    tests_dir = Path(__file__).parent

    aoi_filepath = tests_dir / "test_inputs" / "s1_search_features.gpkg"
    assert aoi_filepath.exists(), f"Input file {aoi_filepath} does not exist."

    output_dir = tmp_path / "outputs"
    output_dir.mkdir()

    src_script = tests_dir.parent / "src" / "s1_search.py"
    assert src_script.exists(), f"Script {src_script} does not exist."

    cmd = [
        sys.executable,
        str(src_script),
        "--start-date",
        "2018-06-01",
        "--end-date",
        "2018-06-02",
        "--aoi-filepath",
        str(aoi_filepath),
        "--output-dir",
        str(output_dir),
        "--aoi-id",
        "id",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Script failed with error: {result.stderr}"

    features_filename = "s1_links_s1_search_features_2018-06-01_2018-06-02.pkl"
    imgs_filename = "s1_links_all_2018-06-01_2018-06-02.pkl"

    output_features_path = output_dir / features_filename
    output_imgs_path = output_dir / imgs_filename

    assert (
        output_features_path.exists()
    ), f"Expected file {output_features_path} was not created."
    assert (
        output_imgs_path.exists()
    ), f"Expected file {output_imgs_path} was not created."

    expected_features_content = get_feature_links()
    expected_imgs_content = get_img_list()

    with output_features_path.open("rb") as f:
        output_features_content = pickle.load(f)
    with output_imgs_path.open("rb") as f:
        output_imgs_content = pickle.load(f)

    assert (
        output_features_content == expected_features_content
    ), "Features pickle file content does not match expected."
    assert (
        output_imgs_content == expected_imgs_content
    ), "All image links pickle file content does not match expected."


def load_npz_as_dict(path: Path) -> dict:
    """Load an npz file and return its contents as a dictionary."""
    with np.load(path, allow_pickle=True) as data:
        return dict(data)


def compare_npz_files(expected_path: Path, output_path: Path):
    """Compare two npz files by checking that all keys and their arrays match."""
    expected = load_npz_as_dict(expected_path)
    output = load_npz_as_dict(output_path)

    assert set(expected.keys()) == set(
        output.keys()
    ), f"Key mismatch: expected {expected.keys()}, got {output.keys()}"

    for key in expected:
        np.testing.assert_array_equal(
            expected[key], output[key], err_msg=f"Mismatch for key: {key}"
        )


def test_s1_search_integration_feature_image_npz(tmp_path):
    """
    Running s1_search.py with feature-image pickle input.

    Tests the following command:
      python src/s1_search.py --aoi-filepath tests/test_inputs/s1_search_features.gpkg
          --aoi-id id --download-all
          --feature-image-pkl tests/test_inputs/s1_links_s1_search_features_2018-06-01_2018-06-02.pkl
          --output-dir <tmp_path>/outputs
    """
    tests_dir = Path(__file__).parent

    aoi_filepath = tests_dir / "test_inputs" / "s1_search_features.gpkg"
    assert aoi_filepath.exists(), f"Input AOI file {aoi_filepath} does not exist."

    feature_image_pkl = (
        tests_dir
        / "test_inputs"
        / "s1_links_s1_search_features_2018-06-01_2018-06-02.pkl"
    )
    assert (
        feature_image_pkl.exists()
    ), f"Feature-image pickle file {feature_image_pkl} does not exist."

    output_dir = tmp_path / "outputs"
    output_dir.mkdir()

    src_script = tests_dir.parent / "src" / "s1_search.py"
    assert src_script.exists(), f"Script {src_script} does not exist."

    cmd = [
        sys.executable,
        str(src_script),
        "--aoi-filepath",
        str(aoi_filepath),
        "--aoi-id",
        "id",
        "--download-all",
        "--feature-image-pkl",
        str(feature_image_pkl),
        "--output-dir",
        str(output_dir),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Script failed with error: {result.stderr}"

    feature_dir = output_dir / "s1_search_features"
    assert feature_dir.exists(), f"Expected directory {feature_dir} was not created."

    npz_file1 = feature_dir / "s1_search_features_1.npz"
    npz_file2 = feature_dir / "s1_search_features_2.npz"
    assert npz_file1.exists(), f"Expected NPZ file {npz_file1} was not created."
    assert npz_file2.exists(), f"Expected NPZ file {npz_file2} was not created."

    expected_npz1 = tests_dir / "expected" / "s1_search_features_1.npz"
    expected_npz2 = tests_dir / "expected" / "s1_search_features_2.npz"
    assert expected_npz1.exists(), f"Expected NPZ file {expected_npz1} is missing."
    assert expected_npz2.exists(), f"Expected NPZ file {expected_npz2} is missing."

    compare_npz_files(expected_npz1, npz_file1)
    compare_npz_files(expected_npz2, npz_file2)
