# ceda_sentinel
Search and download 

## Process overview
This repository is designed to use input features (shapefile or geopackage) to search for Sentinel 2 images over the UK from 
the analysis ready Sentinel 2 images available on 
the [CEDA archive](https://data.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_2). 

The Python package in this repository `src/ceda_s2` contains classes to search for images, to plot them for visual inspection 
and to download them as geotiff files. 

The CEDA images are [cloud optimised geotiffs](https://cogeo.org/) and this allows the processes created in 
this repository to download subsections of image tiles intersecting input features directly from their online storage, rather 
than downloading huge whole image tiles. This saves space and can be particularly useful if extracting images to prepare a training dataset for deep learning methods 
such as UNET.

The process initially extracts links to suitable images for each input feature. These links are recorded in a column in the 
input search shapefile or geopackage. The process checks the image is not mostly nodata or cloud covered to ensure only 
usable images are recorded against the search features. 

The image sections covering each feature can then be plotted (an interactive plot window allows 
to scroll through each search result as RGB true colour images) or downloaded as geotiffs.

## Setup
Either use Docker as described below or install packages from the requirements.txt:

```bash
pip install --requirement requirements.txt
```

## How to run
The easiest way to extract images  via `src/main.py`. For example with a geopackage of search features stored in the inputs 
directory of this repository:

```bash
python src/main.py --search-features inputs/test_search.gpkg \
--start-date 2024-04-01 --end-date 2024-05-31 --plot --download
```
The above will:
- Search for suitable cloud free images for each feature within the specified date range.
- Add the link to each suitable image as an attribute to the features and extract the image date.
- Pop-up a plot window so can scroll through each image/feature and view as RGB true colour image.
- Download the images to the outputs directory.
- Save a copy of the input shapefile or geopackage with a new field of image links and dates.

Note the search is one to many, so the number of features will often be greater in the output layer if the search finds 
multiple suitable images for a feature within the specified date range.

Various other arguments can be used to control the behaviour of `src/main.py` process. For example can just search 
initially (by omitting `--plot` and `--download` arguments) and then plot or download later by specifying the resulting search 
result shapefile (or geopackage) as input to the same process.

To see all the options:
```bash
python src/main.py -h
```
## Docker
Can use the docker image. In a terminal `cd` to the repository and then run:

```bash
docker build . --no-cache --file .devcontainer/Dockerfile -t ceda
```
The Docker image built from the `devcontainer/Dockerfile` includes tk for plotting from within the docker image using X11
forwarding. When start the container need to include this:
```bash
 docker run --rm -i -t -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix \
 -p 127.0.0.1:8888:8888 -w /app --mount type=bind,src="$(pwd)",target=/app ceda
```
