#!/bin/bash

. venv/bin/activate

while true; do
    ./process_pages.py
    inotifywait -e create -e move -e delete -e modify -r assets data content static templates
    sleep 1
done
