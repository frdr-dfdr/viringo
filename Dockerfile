FROM python:3.7

# Update installed APT packages
RUN apt-get update && apt-get upgrade -y -o Dpkg::Options::="--force-confold" && \
    apt-get install -y ntp pandoc

# Cleanup
RUN apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

## Viringo setup
WORKDIR /usr/src/app/viringo

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

ENV FLASK_APP=__init__.py

# install dependencies
RUN pip install --upgrade pip
COPY ./viringo/requirements.txt /usr/src/app/viringo/requirements.txt
RUN pip install -r requirements.txt

# Copy webapp folder
COPY . /viringo /usr/src/app/viringo/

# Copy wsgi.py outside of app module
COPY ./viringo/wsgi.py /usr/src/app/wsgi.py

WORKDIR /usr/src/app

# Expose web
EXPOSE 5000

CMD ["gunicorn","-b", "0.0.0.0", "wsgi:application"]

