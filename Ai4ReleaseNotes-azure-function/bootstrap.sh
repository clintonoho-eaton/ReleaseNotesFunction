#!/bin/sh
export FLASK_APP=./run.py
python -m flask run --debug -h 0.0.0.0