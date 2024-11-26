# ceda_sentinel

## Setup
Either use Docker as described below or install packages from the requirements.txt:

```bash
pip install --requirement requirements.txt
```

## Docker
Can use the docker image:

```bash
docker build . --no-cache --file .devcontainer/Dockerfile -t ceda
```
Docker image includes tk for plotting from within docker image using X11 forwarding. Therefore to run:
```bash
 docker run --rm -i -t -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix -p 127.0.0.1:8888:8888 -w /app --mount type=bind,src="$(pwd)",target=/app ceda
```
# How to run
This repository is designed to search for Sentinel 2 images over the UK from the analysis ready data available on the CEDA 
archive. 

A python package in this repository `src/ceda_s2` contains classes to search for images, to plot them and to download them as 
tif files.

The easiest way to run them is via `src/main.py`. For example with a shapefile of features wish to find and download images 
for stored in the inputs directory of this repository:

```bash
python src/main.py --search-features inputs/test_search.gpkg --start-date 2024-04-01 --end-date 2024-05-31 --plot --download
```
The above will:
- Search for suitable cloud free images for each feature within the specified date range.
- Add the link to each suitable image as an attribute to the features and extract the image date.
- Pop-up a plot window so can scroll through each image/feature and view as RGB true colour image.
- Download the images to the outputs directory.
- Save a copy of the input shapefile or geopackage with a new field of image links and dates.

Note the search is one to many, so the number of features will likely be greater in the output layer if the search finds 
multiple images for a feature.

Various other arguments can be used to control the behaviour of `src/main.py` process. For example can search initially and 
then download or plot later by specifying the resulting search result shapefile (or geopackage) as input.

To see the options:
```bash
python src/main.py -h
```