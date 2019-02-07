# -*- coding: utf-8 -*-
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
# file pulse_xmpp_master_subtitute/pluginsmastersubtitute/plugin_loadpluginschedulerlistversion.py

import base64
import json
import sys, os
import logging
import platform
from lib.utils import file_get_contents, getRandomName, data_struct_message
import traceback
from sleekxmpp import jid
import types
import ConfigParser
logger = logging.getLogger()
DEBUGPULSEPLUGIN = 25

# this plugin calling to starting agent

plugin = {"VERSION" : "1.0", "NAME" : "loadpluginschedulerlistversion", "TYPE" : "subtitute"}

def action( objectxmpp, action, sessionid, data, msg, dataerreur):
    logger.debug("=====================================================")
    logger.debug("call %s from %s"%(plugin, msg['from']))
    logger.debug("=====================================================")

    compteurcallplugin = getattr(objectxmpp, "num_call%s"%action)
    if compteurcallplugin == 0:
        read_conf_load_plugin_scheduler_list_version(objectxmpp)
        objectxmpp.schedule('updatelistpluginscheduler', 1000, objectxmpp.loadPluginschedulerList, repeat=True)
    objectxmpp.loadPluginschedulerList()

def read_conf_load_plugin_scheduler_list_version(objectxmpp):
    """
        lit la configuration du plugin
        le repertoire ou doit se trouver le fichier de configuration est dans la variable objectxmpp.config.pathdirconffile
    """
    namefichierconf = plugin['NAME'] + ".ini"
    pathfileconf = os.path.join( objectxmpp.config.pathdirconffile, namefichierconf )
    if not os.path.isfile(pathfileconf):
        logger.error("plugin %s\nConfiguration file missing\n  %s\neg conf:" \
            "\n[plugins]\ndirpluginlistscheduled = /var/lib/pulse2/xmpp_basepluginscheduler/"%(plugin['NAME'], pathfileconf))
        logger.warning("default value for dirplugins is /var/lib/pulse2/xmpp_basepluginscheduler")
        objectxmpp.dirpluginlistscheduled = "/var/lib/pulse2/xmpp_basepluginscheduler"
    else:
        Config = ConfigParser.ConfigParser()
        Config.read(pathfileconf)
        if os.path.exists(pathfileconf + ".local"):
            Config.read(pathfileconf + ".local")
        objectxmpp.dirpluginlistscheduled = "/var/lib/pulse2/xmpp_basepluginscheduler"
        if Config.has_option("plugins", "dirpluginlistscheduled"):
            objectxmpp.dirpluginlistscheduled = Config.get('plugins', 'dirpluginlistscheduled')
    # function definie dynamiquement
    objectxmpp.plugin_loadpluginschedulerlistversion = types.MethodType(plugin_loadpluginschedulerlistversion, objectxmpp)
    objectxmpp.deployPluginscheduled = types.MethodType(deployPluginscheduled, objectxmpp)
    objectxmpp.loadPluginschedulerList = types.MethodType(loadPluginschedulerList, objectxmpp)

def plugin_loadpluginschedulerlistversion(self, msg, data):
    if 'pluginscheduled' in data:
        for k, v in self.plugindatascheduler.iteritems():
            if k in data['pluginscheduled']:
                if v != data['pluginscheduled'][k]:
                    # deploy on version changes
                    logger.debug ("update plugin %s on agent %s"%(k, msg['from']))
                    self.deployPluginscheduled(msg, k)
                    self.restartAgent(msg['from'])
                    break
                else:
                    logger.debug("No version change for %s on agent %s"%(k, msg['from']))
                    pass
            else:
                # The k plugin is not in the agent plugins list
                if k in self.plugintypescheduler:
                    if self.plugintypescheduler[k] == 'all':
                        self.deployPluginscheduled(msg, k)
                        self.restartAgent(msg['from'])
                        break
                    if self.plugintypescheduler[k] == 'relayserver' and data['agenttype'] == "relayserver":
                        self.deployPluginscheduled(msg, k)
                        self.restartAgent(msg['from'])
                        break
                    if self.plugintypescheduler[k] == 'machine' and data['agenttype'] == "machine":
                        self.deployPluginscheduled(msg, k)
                        self.restartAgent(msg['from'])
                        break

def deployPluginscheduled(self, msg, plugin):
    data = ''
    fichierdata = {}
    namefile = os.path.join(self.config.dirschedulerplugins, "%s.py" % plugin)
    if os.path.isfile(namefile):
        logger.debug("File plugin scheduled found %s" % namefile)
    else:
        logger.error("File plugin scheduled not found %s" % namefile)
        return
    try:
        fileplugin = open(namefile, "rb")
        data = fileplugin.read()
        fileplugin.close()
    except:
        logger.error("File read error\n%s"%(traceback.format_exc()))
        return
    fichierdata['action'] = 'installpluginscheduled'
    fichierdata['data'] = {}
    dd = {}
    dd['datafile'] = data
    dd['pluginname'] = "%s.py" % plugin
    fichierdata['data'] = base64.b64encode(json.dumps(dd))
    fichierdata['sessionid'] = "sans"
    fichierdata['base64'] = True
    try:
        self.send_message(mto=msg['from'],
                            mbody=json.dumps(fichierdata),
                            mtype='chat')
    except:
        logger.error("\n%s"%(traceback.format_exc()))

def loadPluginschedulerList(self):
    logger.debug("Verify base plugin scheduler")
    self.plugindatascheduler = {}
    self.plugintypescheduler = {}
    for element in os.listdir(self.dirpluginlistscheduled):
        if element.endswith('.py') and element.startswith('scheduling_'):
            f = open(os.path.join(self.dirpluginlistscheduled, element), 'r')
            lignes = f.readlines()
            f.close()
            for ligne in lignes:
                if 'VERSION' in ligne and 'NAME' in ligne:
                    line = ligne.split("=")
                    plugin = eval(line[1])
                    self.plugindatascheduler[plugin['NAME']] = plugin['VERSION']
                    try:
                        self.plugintypescheduler[plugin['NAME']] = plugin['TYPE']
                    except:
                        self.plugintypescheduler[plugin['NAME']] = "machine"
                    break


