from gluon.scheduler import Scheduler
import stat
import shutil
from os import path
import os, os.path
import sys
import re
from paver.easy import sh
import logging
from pkg_resources import resource_string, resource_filename

import caliper
import requests, json, sys

from datetime import datetime

rslogger = logging.getLogger(settings.sched_logger)
rslogger.setLevel(settings.log_level)

scheduler = Scheduler(db, migrate='runestone_')

################
## This task will run as a scheduled task using the web2py scheduler.
## It's dispached from build() and build_custom() in controllers/designer.py
################
def run_sphinx(rvars=None, folder=None, application=None, http_host=None, base_course=None):
    # workingdir is the application folder
    workingdir = folder
    # sourcedir holds the all sources temporarily
    sourcedir = path.join(workingdir, 'build', rvars['projectname'])

    rslogger.debug("Starting to build {}".format(rvars['projectname']))

    # create the custom_courses dir if it doesn't already exist
    if not os.path.exists(path.join(workingdir, 'custom_courses')):
        os.mkdir(path.join(workingdir, 'custom_courses'))

    # confdir holds the conf and index files
    custom_dir = path.join(workingdir, 'custom_courses', rvars['projectname'])


    if not os.path.exists(custom_dir):
        os.mkdir(custom_dir)

    # ## check for base_course  if base_course == None
    ### read conf.py and look for How to Think to determine coursetype
    if base_course == None:
        base_course = 'thinkcspy'

    # copy all the sources into the temporary sourcedir
    if os.path.exists(sourcedir):
        shutil.rmtree(sourcedir)
    shutil.copytree(path.join(workingdir, 'books', base_course), sourcedir)

    makePavement(http_host, rvars, sourcedir, base_course)
    shutil.copy(path.join(sourcedir,'pavement.py'),custom_dir)

    #########
    # We're rebuilding a course
    #########
    if rvars['coursetype'] == 'rebuildcourse':

        try:
            # copy the index and conf files to the sourcedir
            shutil.copy(path.join(custom_dir, 'pavement.py'), path.join(sourcedir, 'pavement.py'))
        except OSError:
            # Either the sourcedir already exists (meaning this is probably devcourse, thinkcspy, etc,
            # or the conf.py or index.rst files are missing for some reason.
            raise OSError("missing paver, index, or assignments file")

    ########
    # we're just copying one of the pre-existing books
    ########
#    else:
        # Save copies of files that the instructor may customize
        # shutil.copy(path.join(sourcedir,'_sources', 'index.rst'),custom_dir)

    ###########
    # Set up and run Paver build
    ###########

    from paver.tasks import main as paver_main
    old_cwd = os.getcwd()
    os.chdir(sourcedir)
    paver_main(args=["build"])
    rslogger.debug("Finished build of {}".format(rvars['projectname']))
    try:
        shutil.copy('build_info',custom_dir)
    except IOError as copyfail:
        rslogger.debug("Failed to copy build_info_file")
        rslogger.debug(copyfail.message)
        idxname = 'index.rst'

    #
    # move the sourcedir/build/projectname folder into static
    #
    # todo check if dest is a symlink and remove it instead of calling rmtree
    if os.path.islink(os.path.join(workingdir,'static',rvars['projectname'])):
        os.remove(os.path.join(workingdir,'static',rvars['projectname']))
    else:
        shutil.rmtree(os.path.join(workingdir,'static',rvars['projectname']),ignore_errors=True)
    shutil.move(os.path.join(sourcedir,'build',rvars['projectname']),
                os.path.join(workingdir,'static',rvars['projectname']) )
    #
    # clean up
    #

    # This will remove a directory that's versioned by Git, which marks some of its files as read-only on Windows. This causes rmtree to fail. So, provide a workaround per `SO <https://stackoverflow.com/questions/21261132/shutil-rmtree-to-remove-readonly-files>`_.
    def del_rw(function, path, excinfo):
        os.chmod(path, stat.S_IWRITE)
        if os.path.isdir(path):
            os.rmdir(path)
        else:
            os.remove(path)
    # Change away from sourcedir, to avoid an error like ``WindowsError: [Error 32] The process cannot access the file because it is being used by another process: 'E:\\Runestone\\web2py\\applications\\runestone\\build\\test_book10'``.
    os.chdir(old_cwd)
    shutil.rmtree(sourcedir, onerror=del_rw)
    rslogger.debug("Completely done with {}".format(rvars['projectname']))


def makePavement(http_host, rvars, sourcedir, base_course):
    paver_stuff = resource_string('runestone', 'common/project_template/pavement.tmpl')
    opts = {'master_url': settings.server_type + http_host,
            'project_name': rvars['projectname'],
            'build_dir': 'build',
            'log_level': 10,
            'use_services': 'true',
            'dburl': settings.database_uri,
            'basecourse': base_course,
            'default_ac_lang': rvars.get('default_ac_lang') if rvars.get('default_ac_lang',False) else 'python',
            'downloads_enabled': rvars.get('downloads_enabled','false'),
            'enable_chatcodes': 'false',
            'allow_pairs': 'false'
            }
    if 'loginreq' in rvars:
        opts['login_req'] = 'true'
    else:
        opts['login_req'] = 'false'
    if 'python3' in rvars:
        opts['python3'] = 'true'
    else:
        opts['python3'] = 'false'

    opts['dest'] = '../../static'

    paver_stuff = paver_stuff % opts
    with open(path.join(sourcedir, 'pavement.py'), 'w') as fp:
        fp.write(paver_stuff)

# This task is scheduled here to run every 5 minutes
def send_events_to_caliper():
    rslogger.info("Starting to process events")
    # Number of events processed

    ecount = 0
    # Get last runtime of this method 
    # We can't use the last_run_time of the value in schedule_task as that's updated while this is running
    # So instead get the start time from the scheduler_run for the last run
    try: 
        completed_runs = db(
            (db.scheduler_run.task_id == db.scheduler_task.id) & 
            (db.scheduler_run.status == 'COMPLETED') & 
            (db.scheduler_task.task_name == 'send_events_to_caliper')
            ).select(db.scheduler_run.start_time, orderby=~db.scheduler_run.id).first()
        # If completed_runs is stil none, this was first run ever, just don't do anything but exit so this run gets a timestamp
        # db((db.scheduler_task.status == 'RUNNING') & (db.scheduler_task.task_name == 'send_events_to_caliper')
        #     ).select(db.scheduler_task.last_run_time, orderby=db.scheduler_task.last_run_time).last()

        if completed_runs is None:
            return "No runs found yet, returning"
        # Reschedule this job to run again
        # Now that we have the latest run, Get all events from db.useinfo since last runtime based on timestamp
        rslogger.info("completed_runs {}".format(completed_runs.start_time))

        events = db(
            (db.useinfo.timestamp > completed_runs.start_time)
        ).select()

        # Loop though and process the events that we can and send them to caliper, also count the number of records we process
        for event in events:
            # Only send navigation events
            if event.event == "page":
                nav_path = event.div_id.split('/')
                actor = caliper.entities.Person(id=event.sid)
                edApp = caliper.entities.SoftwareApplication(id="test_app_id", name="runestone")
                organization = caliper.entities.Organization(id="test_org_id", name="test_org_name")
                time = event.timestamp

                try:
                    # If resource is Page
                    resource = caliper.entities.Page(
                        id = event.div_id,
                        name = nav_path[5],
                        isPartOf = caliper.entities.Chapter(
                            id = nav_path[:5].join('/') + '/', # Use path as id
                            name = nav_path[4],
                            isPartOf = caliper.entities.Document(
                                id = '/'.join(nav_path[:4]) + '/',
                                name = nav_path[3],
                            )
                        )
                    )
                except:
                    # If resoure is Chapter
                    resource = caliper.entities.Chapter(
                        id = '/'.join(nav_path[:5]) + '/',
                        name = nav_path[4],
                        isPartOf = caliper.entities.Document(
                            id = '/'.join(nav_path[:4]) + '/',
                            name = nav_path[3],
                        )
                    )
                
                
                caliper_sender(
                    actor, 
                    organization, 
                    edApp, 
                    resource,
                    time)
        # Loop though and process the events that we can and send them to caliper, also count the number of records we process
        
        return "Event processing completed, processed {} events".format(ecount)
    except:
        rslogger.exception("Exception running send_events_to_caliper job")
        raise


def caliper_sender(actor, organization, edApp, resource, time):
    # TODO: lrw_server should come from environment variable
    lrw_server = "http://lti.tools"
    # TODO: Endpoint should probably also come from environment variable
    lrw_endpoint = lrw_server + "/caliper/event?key=python-caliper"

    # TODO: token should come from enviornment variable
    token = "python-caliper"

    the_config = caliper.HttpOptions(
        host="{0}".format(lrw_endpoint),
        auth_scheme='Bearer',
        api_key=token)

# Here you build your sensor; it will have one client in its registry,
    # with the key 'default'.
    the_sensor = caliper.build_sensor_from_config(
            sensor_id = "{0}/test_caliper".format(lrw_server),
            config_options = the_config )

    # Here, you will have caliper entity representations of the various
    # learning objects and entities in your wider system, and you provide
    # them into the constructor for the event that has just happened.
    #
    # Note that you don't have to pass an action into the constructor because
    # the NavigationEvent only supports one action, part of the
    # Caliper base profile: caliper.constants.BASE_PROFILE_ACTIONS['NAVIGATED_TO']
    #

    the_event = caliper.events.NavigationEvent(
            actor = actor,
            edApp = edApp,
            group = organization,
            object = resource,
            eventTime = time.isoformat(),
            action = "NavigatedTo"
            )

    # Once built, you can use your sensor to describe one or more often used
    # entities; suppose for example, you'll be sending a number of events
    # that all have the same actor

    ret = the_sensor.describe(the_event.actor)

    # The return structure from the sensor will be a dictionary of lists: each
    # item in the dictionary has a key corresponding to a client key,
    # so ret['default'] fetches back the list of URIs of all the @ids of
    # the fully described Caliper objects you have sent with that describe call.
    #
    # Now you can use this list with event sendings to send only the identifiers
    # of already-described entities, and not their full forms:
    #print(the_sensor.send(the_event, described_objects=ret['default'])

    # You can also just send the event in its full form, with all fleshed out
    # entities:
    the_sensor.send(the_event)

    rslogger.info("Event sent!")

# Check if we already have a task on the queue
try:
    queued_caliper_task = db((db.scheduler_task.task_name == 'send_events_to_caliper') & (db.scheduler_task.status == 'QUEUED'))

    if queued_caliper_task.isempty():
        # Queue up a new task
        rslogger.info("QUEUING up a send_events_to_caliper task")
        scheduler.queue_task("send_events_to_caliper", period=30, repeats=0)
    else:
        rslogger.info("send_events_to_caliper task already QUEUED")
except Exception:
    rslogger.info("Exception queuing up task, if there is no database table yet this is expected")
