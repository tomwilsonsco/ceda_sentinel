import subprocess
import sys
import pickle
from pathlib import Path
from get_data_s1 import get_img_list, get_feature_links
import numpy as np
import pytest


@pytest.fixture
def generate_pickle_output(tmp_path):
    """
    Fixture to run s1_search.py and return the generated pickle paths.
    """
    tests_dir = Path(__file__).parent
    aoi_filepath = tests_dir / "test_inputs" / "s1_search_features.gpkg"
    assert aoi_filepath.exists()

    output_dir = tmp_path / "outputs"
    output_dir.mkdir()

    src_script = tests_dir.parent / "src" / "s1_search.py"
    assert src_script.exists()

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

    features_path = output_dir / features_filename
    imgs_path = output_dir / imgs_filename

    assert features_path.exists()
    assert imgs_path.exists()

    return {
        "features_path": features_path,
        "imgs_path": imgs_path,
        "output_dir": output_dir,
    }


def test_s1_search_integration(generate_pickle_output):
    """
    Validates pickle content from s1_search.py against expected values.
    """
    features_path = generate_pickle_output["features_path"]
    imgs_path = generate_pickle_output["imgs_path"]

    expected_features_content = get_feature_links()
    expected_imgs_content = get_img_list()

    with features_path.open("rb") as f:
        output_features_content = pickle.load(f)
    with imgs_path.open("rb") as f:
        output_imgs_content = pickle.load(f)

    assert output_features_content == expected_features_content
    assert output_imgs_content == expected_imgs_content


def load_npz_as_dict(path: Path) -> dict:
    with np.load(path, allow_pickle=True) as data:
        return dict(data)


def compare_npz_files(expected_path: Path, output_path: Path):
    expected = load_npz_as_dict(expected_path)
    output = load_npz_as_dict(output_path)

    assert set(expected.keys()) == set(output.keys())
    for key in expected:
        np.testing.assert_array_equal(expected[key], output[key])


def test_s1_search_integration_feature_image_npz(generate_pickle_output):
    """
    Uses the pickle output from previous fixture to generate NPZ files and compare to expected.
    """
    tests_dir = Path(__file__).parent

    aoi_filepath = tests_dir / "test_inputs" / "s1_search_features.gpkg"
    assert aoi_filepath.exists()

    feature_image_pkl = generate_pickle_output["features_path"]
    output_dir = generate_pickle_output["output_dir"]

    src_script = tests_dir.parent / "src" / "s1_search.py"
    assert src_script.exists()

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
    assert feature_dir.exists()

    npz_file1 = feature_dir / "s1_search_features_1.npz"
    npz_file2 = feature_dir / "s1_search_features_2.npz"
    assert npz_file1.exists()
    assert npz_file2.exists()

    expected_npz1 = tests_dir / "expected" / "s1_search_features_1.npz"
    expected_npz2 = tests_dir / "expected" / "s1_search_features_2.npz"
    assert expected_npz1.exists()
    assert expected_npz2.exists()

    compare_npz_files(expected_npz1, npz_file1)
    compare_npz_files(expected_npz2, npz_file2)
