#!/bin/bash

htdir="$(dirname $0)/htdocs"

python3 -m http.server 7007 --bind 127.0.0.1 --directory $htdir
