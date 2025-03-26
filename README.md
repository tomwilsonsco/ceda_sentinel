# CEDA Sentinel
## Process overview
Extract Sentinel 1 SAR GRD or Sentinel 2 Optical imagery over the UK from the analysis ready images available on the CEDA Archive. See:
- [Defra and JNCC Sentinel-1 Analysis Ready Data (ARD)](https://catalogue.ceda.ac.uk/uuid/05cea0662aa54aa2b7e2c5811e09431f/)
- [Defra and JNCC Sentinel-2 Analysis Ready Data (ARD)](https://catalogue.ceda.ac.uk/uuid/bf9568b558204b81803eeebcc7f529ef/)
- [Simple ARD Service Information for Users](https://data.jncc.gov.uk/data/dcb14a5e-301f-40ae-94c3-22b73fb4ec57/simple-ard-service-user-guide.pdf)  

The Python packages in this repository `src/ceda_s1` and `src/ceda_s2` contain classes to search for images, to download them as geotiff files, and optionally for Sentinel 2, to plot them to check cloud cover visually.

The CEDA images are [cloud optimised geotiffs](https://cogeo.org/) and this allows the processes created in 
this repository to download subsections of image tiles intersecting input features directly from their online storage, rather 
than downloading large whole image tiles. This saves space and can be particularly useful if extracting images to prepare a 
training dataset for deep learning methods such as UNET.

## Sentinel 2 Process
The process initially extracts links to suitable Sentinel 2 images for each input feature. These links are recorded in a column in the 
in a copy of the input search shapefile or geopackage. The process checks the image is not mostly nodata or cloud covered to 
ensure only usable images are recorded against the search features. 

Once the search is complete, images covering each feature can be plotted (an interactive plot window allows 
to scroll through each search result as RGB true colour images), and/or downloaded as geotiffs.

### How to run Sentinel 2 process
The easiest way to extract images is by running `src/s2_search.py`.  
For example with a geopackage of search features stored in the inputs directory of this repository:

```bash
python src/s2_search.py --search-features inputs/test_search.gpkg \
--start-date 2024-04-01 --end-date 2024-05-31 --plot --download
```
The above will:
- Search for suitable cloud free images for each feature within the specified date range. By default the s2cloudless mask included with the CEDA ARD imagery is used to check no more than 10 percent of input shape area is cloud covered. This can be adjusted and the full image cloud cover metadata can also be used to filter.
- Add the link to each suitable image as an attribute to the features and extract the image date.
- Pop-up a plot window so can scroll through each image/feature and view as RGB true colour image.
- Download the images to the outputs directory.
- Save a copy of the input shapefile or geopackage with a new field of image links and dates.

Note the search is one to many, so the number of features will often be greater in the output layer if the search finds 
multiple suitable images for a feature within the specified date range.

Various other arguments can be used to control the behaviour of the `src/s2_search.py` process. For example, you can just search 
initially without any plotting or downloading (by including `--start-date`, `--end-date`, but not `--plot` and 
`--download` arguments). You can then plot or download later by specifying the search result shapefile (or 
geopackage) as `--search-features` (and this time can omit the start and end dates as it will use existing image links found by default).

To see all the options:
```bash
python src/s2_search.py -h
```
## Sentinel 1 Process
Many aspects are the same as the Sentinel 2 search, but there is no cloud cover to consider. Currently plotting is not available as part of the Sentinel 1 search. The process aims to find the ascending and descending orbit images that cover area of interest polygons. A time series of images can be downloaded as arrays or geotiffs. 

Initially can search for suitable image links for each input aoi feature. The initial search does not read image arrays from CEDA, it just checks the image extents:

```bash
python src/s1_search.py --start-date 2018-06-01 --end-date 2018-06-10 --aoi-filepath inputs/s1_search_features.gpkg --aoi-id id
```
The output of the initial search is two pickle files:

1. `outputs/s1_links_<aoi-file-name>_<start-date>_<end_date>.pkl` is a dictionary where keys are image ids (the column specified by `aoi-id`) and values of lists of direct links to Sentinel 1 images within the specified date range, that the feature falls within.

2. `outputs/s1_links_all_<start-date>_<end-date>.pkl` is a list of all the images (of the specified orbit numbers) within the date range. This is a helper file to speed up subsequent searches using the same date range and is useful if searching over a long time frame for a variety of aoi collections.

Once the initial search is complete, input the first of the two pickle files and specify `--download-all` to download the images. By default the Sentinel 1 images are read as arrays and written into zipped numpy npz files in `<image file name>: array` format. If want tif files instead specify `download-tifs` too.

```bash
python src/s1_search.py --aoi-filepath inputs/s1_search_features.gpkg --aoi-id id --download-all --feature-image-pkl outputs/s1_links_s1_search_features_2018-06-01_2018-06-10.pkl
```

It is recommended to review all options by specifying:

```bash
python src/s1_search.py -h
```
## Docker
Recommended to use the docker image. Alternatively install the packages in the requirements.txt. To start Docker, in a terminal `cd` to the repository and then run:

```bash
docker build . --no-cache --file .devcontainer/Dockerfile -t ceda
```
The Docker image built from the `devcontainer/Dockerfile` includes tk for plotting from within the docker image using X11
forwarding. Currently plotting images is an optional for the Sentinel 2 search only. If want to use this, when start the container need to include this:
```bash
 docker run --rm -i -t -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix \
 -p 127.0.0.1:8888:8888 -w /app --mount type=bind,src="$(pwd)",target=/app ceda
```

## Test script
An integration test that downloads S1 images for two small features from CEDA and compares with pre-existing outputs was created under `tests/`. To run just cd to the repo in a terminal and run:
```bash
pytest
```
