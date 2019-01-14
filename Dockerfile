FROM docker.io/python:2.7

RUN apt-get update

RUN apt-get --no-install-recommends install --yes \
    libfreetype6-dev postgresql-common postgresql postgresql-contrib \
    libpq-dev libxml2-dev libxslt1-dev unzip

WORKDIR /tmp/

COPY requirements.txt /tmp/
COPY rsmanage /tmp/rsmanage

RUN pip install -r requirements.txt

# Sets the local timezone of the docker image
ENV TZ=America/Detroit
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install npm and wait-port globally
# https://github.com/nodesource/distributions/blob/master/README.md
RUN curl -sL https://deb.nodesource.com/setup_10.x | bash - && \
    apt-get -y install npm && npm install -g wait-port@"~0.2.2"


ARG LOCALHOST_DEV
RUN mkdir -p /usr/src/app/

WORKDIR /usr/src/app/
# Install Web2Py
RUN curl -LO http://www.web2py.com/examples/static/web2py_src.zip && unzip web2py_src.zip && rm web2py_src.zip

# Copy the start script into the base

COPY ./scripts/dockerstart.sh /usr/src/app/
# Copy the rest into webpy
COPY . /usr/src/app/web2py/applications/runestone

# TODO: Expose some path for applications/runestone/books

EXPOSE 8000
CMD ./dockerstart.sh
