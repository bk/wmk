# After container creation with "docker build -t wmk ." do this:
#
#   docker run --rm --volume $(pwd):/data --user $(id -u):$(id -g) wmk
#
# followed by the normal parameters, e.g. "build .".
#
# For serve|watch|watch-serve you should add "-i -t" after "--rm"
# so as to be able to stop the process with Ctrl-C, as well as a
# port mapping, e.g. "-p 8008:7007"

# Base image
FROM python:3.10.6-slim-buster

# Preliminaries
WORKDIR /
RUN apt-get -q update \
  && DEBIAN_FRONTEND=noninteractive \
    apt-get install -y rsync git inotify-tools wget

# Install pandoc.
# This may be omitted if you are not planning to use wmk's Pandoc options
RUN wget --quiet \
    https://github.com/jgm/pandoc/releases/download/2.19.2/pandoc-2.19.2-1-amd64.deb \
  && dpkg -i pandoc-2.19.2-1-amd64.deb \
  && rm -f pandoc-2.19.2-1-amd64.deb

# Install wmk
RUN git clone https://github.com/bk/wmk
WORKDIR /wmk
RUN python -m venv venv
RUN . venv/bin/activate \
  && pip install --upgrade pip \
  && pip install -r requirements.txt

# This will be used as a moint point for the wmk workdir
RUN mkdir /data
WORKDIR /data

# Assumes the default port for serve|watch-serve.
# Map it with -p 7007:7007 or similar.
EXPOSE 7007

ENTRYPOINT ["/wmk/bin/wmk"]
