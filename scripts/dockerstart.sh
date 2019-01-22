#!/usr/bin/env bash

echo $DJANGO_SETTINGS_MODULE

set -x

export BASEDIR=/usr/src/app/web2py
cd ${BASEDIR}

cp applications/runestone/scripts/run_scheduler.py .

echo "Waiting for DB"
wait-port ${DBHOST}:${DBPORT} -t 15000

# Touch the database log
mkdir -p applications/runestone/databases
touch applications/runestone/databases/sql.log

# Step 9 in README, init the db
rsmanage initdb

# Step 10 build the books (These should be defined in Dockerfile)
cd ${BASEDIR}/applications/runestone/books/

if [ -d pythonds ]; then
    cd pythonds && pip install -r requirements.txt && runestone deploy
else
    echo "Python DS book not found"
fi

cd ${BASEDIR}


#TODO: Setup a password?
python web2py.py --ip=0.0.0.0 --port=8000 --password='<recycle>' -K runestone --nogui -X