#!/usr/bin/env python
# -*- coding: utf-8; -*-
#
# (c) 2016 siveo, http://www.siveo.net
#
# This file is part of Pulse 2, http://www.siveo.net
#
# Pulse 2 is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Pulse 2 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Pulse 2; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA.

import sys,os
import os.path

import logging
import time
from datetime import datetime
import croniter
#from lib.utils import

logger = logging.getLogger()

class manage_scheduler:
    """
    This class manages events and it executes the scheduler plugins that are contained in
     The / descriptor_scheduler_relay or descriptor_scheduler_machine
     Scheduled plugins are files prefixed by scheduling_

     These files must have a function schedule_main
     Def schedule_main (objectxmpp):
         Contained function

     These files also need to have a dict with its crontab descriptor.
     # Nb -1 infinite
     SCHEDULE = {"schedule": "* / 1 * * * *", "nb": -1}
     Nb makes it possible to limit the operation a n times.
    """
    def __init__(self, objectxmpp):
        #creation repertoire si non exist.
        self.taches = []

        self.now = datetime.now()

        self.objectxmpp = objectxmpp

        #addition path to sys
        if  self.objectxmpp.config.agenttype in ['relayserver']:
            descriptor_scheduler = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "descriptor_scheduler_relay")
        elif self.objectxmpp.config.agenttype in ['machine']:
            descriptor_scheduler = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "descriptor_scheduler_machine")
        self.directoryschedule =  os.path.abspath(descriptor_scheduler)
        print "directory to descriptor scheduler (%s : %s)"%(self.objectxmpp.config.agenttype, self.directoryschedule )
        sys.path.append(self.directoryschedule)
        #creation repertoire si non exist
        if not os.path.exists(self.directoryschedule):
            logging.getLogger().debug("create directory scheduler %s"%self.directoryschedule)
            os.makedirs(self.directoryschedule, 0700 )
        print self.directoryschedule
        namefile = os.path.join(self.directoryschedule,"__init__.py")
        print namefile
        if not os.path.exists(namefile):
            fichier = open(namefile, "w")
            fichier.write("###WARNING : never delete this file")
            fichier.close()

        for x in os.listdir(self.directoryschedule):
            if x.endswith(".pyc") or not x.startswith("scheduling"):
                continue
            #recupere SCHEDULERDATA
            name = x[11:-3]
            try:
                datascheduler = self.litschedule(name)
                self.add_event(name, datascheduler)
            except Exception:
                pass


    def add_event(self, name, datascheduler):
        tabcron = datascheduler['schedule']
        cron = croniter.croniter(tabcron, self.now)
        nextd = cron.get_next(datetime)
        if 'nb' in datascheduler:
            nbcount = datascheduler['nb']
        else:
            nbcount = -1
        obj=  {"name": name, "exectime" : time.mktime(nextd.timetuple()) , "tabcron" : tabcron , "timestart" : str(self.now), "nbcount" : nbcount, "count" : 0 }
        self.taches.append(obj)

    def process_on_event(self):
        now = datetime.now()
        secondeunix = time.mktime(now.timetuple())
        deleted=[]
        for t in self.taches:
            if (secondeunix - t["exectime"])  > 0:
                #replace exectime
                t["count"] = t["count"] + 1
                if "nbcount" in t and t["nbcount"] != -1 and  t["count"] > t["nbcount"]:
                    deleted.append(t)
                    logging.getLogger().debug("terminate plugin %s"%t)
                    continue
                cron = croniter.croniter(t["tabcron"], now)
                nextd = cron.get_next(datetime)
                t["exectime"] = time.mktime(nextd.timetuple())
                self.call_scheduling_main(t["name"], self.objectxmpp)
        for y in deleted:
            self.taches.remove(y)

    def call_scheduling_main(self, name, *args, **kwargs):
        mod = __import__("scheduling_%s"%name)
        logging.getLogger().debug("exec plugin scheduling_%s"%name)
        mod.schedule_main(*args, **kwargs)

    def call_scheduling_mainspe(self, name, *args, **kwargs):
        mod = __import__("scheduling_%s"%name)

        return mod.schedule_main

    def litschedule(self, name):
        mod = __import__("scheduling_%s"%name)
        return mod.SCHEDULE
