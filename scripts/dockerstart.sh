#!/usr/bin/env bash

echo $DJANGO_SETTINGS_MODULE

set -x

cd web2py

cp applications/runestone/scripts/run_scheduler.py .

echo "Waiting for DB"
wait-port ${DBHOST}:${DBPORT} -t 15000

#TODO: Setup a password?
python web2py.py --ip=0.0.0.0 --port=8000 --password='<recycle>' -K runestone --nogui -X 

echo "starting scheduler"
python run_scheduler.py & 
