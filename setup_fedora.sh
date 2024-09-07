#!/bin/sh -e

# Fedora packages

sudo dnf install -y \
	freetype \
	freetype-devel \
	geos \
	geos-devel \
	libpng \
	libpng-devel \
	spatialindex \
	spatialindex-devel \
	python3-devel \
	python3-gdal \
	python3-pip \
	python3-pyqt6 \
	python3-simplejson \
	python3-tkinter
	# python3-pyqt6.qtopengl \
	# qt5-style-plugins \


# ################################
# Python packages

pip install --upgrade \
	pip \
	numpy \
	shapely \
	rtree \
	tk \
	lxml \
	cycler \
	python-dateutil \
	kiwisolver \
	dill \
	vispy \
	pyopengl \
	setuptools \
	svg.path \
	freetype-py \
	fontTools \
	rasterio \
	ezdxf \
	matplotlib \
	qrcode \
	pyqt6 \
	reportlab \
	svglib \
	pyserial \
	pikepdf \
	foronoi \
	ortools \
	pyqtdarktheme \
	darkdetect \
	svgtrace
# OR-TOOLS package is now optional
# ################################
