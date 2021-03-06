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

import sys
import os
import logging
import sleekxmpp
import platform
import base64
import json
import time
import socket
import select
import threading
from lib.agentconffile import conffilename
from lib.update_remote_agent import Update_Remote_Agent
from lib.xmppiq import dispach_iq_command
from sleekxmpp.xmlstream import handler, matcher

import subprocess
from sleekxmpp.exceptions import IqError, IqTimeout
from sleekxmpp import jid
from lib.networkinfo import networkagentinfo, organizationbymachine, organizationbyuser
from lib.configuration import confParameter, nextalternativeclusterconnection, changeconnection
from lib.managesession import session

from lib.managefifo import fifodeploy
from lib.managedeployscheduler import manageschedulerdeploy
from lib.utils import   DEBUGPULSE, getIpXmppInterface, refreshfingerprint,\
                        getRandomName, load_back_to_deploy, cleanbacktodeploy,\
                        call_plugin, searchippublic, subnetnetwork,\
                        protoandport, createfingerprintnetwork, isWinUserAdmin,\
                        isMacOsUserAdmin, check_exist_ip_port, ipfromdns,\
                        shutdown_command, reboot_command, vnc_set_permission,\
                        save_count_start, test_kiosk_presence, file_get_contents,\
                        isBase64, connection_established
from lib.manage_xmppbrowsing import xmppbrowsing
from lib.manage_event import manage_event
from lib.manage_process import mannageprocess, process_on_end_send_message_xmpp
import traceback
from optparse import OptionParser

from multiprocessing import Queue
from multiprocessing.managers import SyncManager
from lib.manage_scheduler import manage_scheduler
from lib.logcolor import  add_coloring_to_emit_ansi, add_coloring_to_emit_windows
from lib.manageRSAsigned import MsgsignedRSA, installpublickey
import psutil

if sys.platform.startswith('win'):
    import win32api
    import win32con
else:
    import signal

sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib"))


logger = logging.getLogger()
global restart
signalint = False

if sys.version_info < (3, 0):
    reload(sys)
    sys.setdefaultencoding('utf8')
else:
    raw_input = input

class QueueManager(SyncManager):
    pass

class MUCBot(sleekxmpp.ClientXMPP):
    def __init__(self, conf):#jid, password, room, nick):
        logging.log(DEBUGPULSE, "start machine1  %s Type %s" %(conf.jidagent, conf.agenttype))
        logger.info("start machine1  %s Type %s" %(conf.jidagent, conf.agenttype))
        sleekxmpp.ClientXMPP.__init__(self, jid.JID(conf.jidagent), conf.passwordconnection)
        laps_time_update_plugin = 3600
        laps_time_handlemanagesession = 20
        laps_time_check_established_connection = 900
        logging.warning("check connexion xmpp %ss"%laps_time_check_established_connection)
        self.back_to_deploy = {}
        self.config = conf
        self.quitserverkiosk = False
        laps_time_networkMonitor = self.config.detectiontime
        logging.warning("laps time network changing %s"%laps_time_networkMonitor)
        ###################Update agent from MAster#############################
        self.pathagent = os.path.join(os.path.dirname(os.path.realpath(__file__)))
        self.img_agent = os.path.join(os.path.dirname(os.path.realpath(__file__)), "img_agent")
        self.Update_Remote_Agentlist = Update_Remote_Agent(self.pathagent, True )
        self.descriptorimage = Update_Remote_Agent(self.img_agent)
        if len(self.descriptorimage.get_md5_descriptor_agent()['program_agent']) == 0:
            #copy agent vers remote agent.
            if sys.platform.startswith('win'):
                for fichier in self.Update_Remote_Agentlist.get_md5_descriptor_agent()['program_agent']:
                    if not os.path.isfile(os.path.join(self.img_agent, fichier)):
                        os.system('copy  %s %s'%(os.path.join(self.pathagent, fichier), os.path.join(self.img_agent, fichier)))
                if not os.path.isfile(os.path.join(self.img_agent,'agentversion' )):
                    os.system('copy  %s %s'%(os.path.join(self.pathagent, 'agentversion'), os.path.join(self.img_agent, 'agentversion')))
                for fichier in self.Update_Remote_Agentlist.get_md5_descriptor_agent()['lib_agent']:
                    if not os.path.isfile(os.path.join(self.img_agent,"lib", fichier)):
                        os.system('copy  %s %s'%(os.path.join(self.pathagent, "lib", fichier), os.path.join(self.img_agent,"lib", fichier)))
                for fichier in self.Update_Remote_Agentlist.get_md5_descriptor_agent()['script_agent']:
                    if not os.path.isfile(os.path.join(self.img_agent, "script", fichier)):
                        os.system('copy  %s %s'%(os.path.join(self.pathagent, "script", fichier), os.path.join(self.img_agent,"script", 'lib_agent')))
            elif sys.platform.startswith('linux') or sys.platform.startswith('darwin'):
                print "copy file"
                os.system('cp -u %s/*.py %s'%(self.pathagent,self.img_agent))
                os.system('cp -u %s/script/* %s/script/'%(self.pathagent,self.img_agent))
                os.system('cp -u %s/lib/*.py %s/lib/'%(self.pathagent,self.img_agent))
                os.system('cp -u %s/agentversion %s/agentversion'%(self.pathagent,self.img_agent))
            else:
                logger.error("command copy for os")
        self.descriptorimage = Update_Remote_Agent(self.img_agent)
        if self.config.updating != 1:
            logging.warning("remote updating disable")
        if self.descriptorimage.get_fingerprint_agent_base() != self.Update_Remote_Agentlist.get_fingerprint_agent_base():
            self.agentupdating=True
            logging.warning("Agent installed is different from agent on master.")
        ###################END Update agent from MAster#############################
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Bind the socket to the port
        server_address = ('localhost',  self.config.am_local_port)
        logging.log(DEBUGPULSE,  'starting server tcp kiosk on %s port %s' % server_address)
        self.sock.bind(server_address)
        # Listen for incoming connections
        self.sock.listen(5)
        #using event eventkill for signal stop thread
        self.eventkill = threading.Event()
        client_handlertcp = threading.Thread(target=self.tcpserver)
        # run server tcpserver for kiosk
        client_handlertcp.start()
        self.manage_scheduler  = manage_scheduler(self)
        self.session = session(self.config.agenttype)

        # initialise charge relay server
        if self.config.agenttype in ['relayserver']:
            self.managefifo = fifodeploy()
            self.session.resources = set(list(self.managefifo.SESSIONdeploy))
            self.levelcharge = self.managefifo.getcount()
        self.jidclusterlistrelayservers = {}
        self.machinerelayserver = []
        self.nicklistchatroomcommand = {}
        self.jidchatroomcommand = jid.JID(self.config.jidchatroomcommand)
        self.agentcommand = jid.JID(self.config.agentcommand)
        self.agentsiveo = jid.JID(self.config.jidagentsiveo)

        self.agentmaster = jid.JID("master@pulse")
        if self.config.sub_inventory == "":
            self.sub_inventory = self.agentmaster
        else:
            self.sub_inventory = jid.JID(self.config.sub_inventory)

        if self.config.sub_registration == "":
            self.sub_registration = self.agentmaster
        else:
            self.sub_registration = jid.JID(self.config.sub_registration)

        if self.config.agenttype in ['relayserver']:
            # supp file session start agent.
            # tant que l'agent RS n'est pas started les files de session dont le deploiement a echoue ne sont pas efface.
            self.session.clearallfilesession()
        self.reversessh = None
        self.reversesshmanage = {}
        self.signalinfo = {}
        self.queue_read_event_from_command = Queue()
        if self.config.agenttype in ['machine']:
            self.xmppbrowsingpath = xmppbrowsing(defaultdir = self.config.defaultdir, rootfilesystem = self.config.rootfilesystem, objectxmpp = self)
        self.ban_deploy_sessionid_list = set() # List id sessions that are banned
        self.lapstimebansessionid = 900     # ban session id 900 secondes
        self.banterminate = { } # used for clear id session banned
        self.schedule('removeban', 30, self.remove_sessionid_in_ban_deploy_sessionid_list, repeat=True)
        self.Deploybasesched = manageschedulerdeploy()
        self.eventmanage = manage_event(self.queue_read_event_from_command, self)
        self.mannageprocess = mannageprocess(self.queue_read_event_from_command)
        self.process_on_end_send_message_xmpp = process_on_end_send_message_xmpp(self.queue_read_event_from_command)
        self.schedule('check established connection',
                      laps_time_check_established_connection,
                      self.established_connection,
                      repeat=True)

        # use public_ip for localisation
        if self.config.public_ip == "":
            try:
                self.config.public_ip = searchippublic()
            except Exception:
                pass
        if self.config.public_ip == "" or self.config.public_ip == None:
            self.config.public_ip = None

        self.md5reseau = refreshfingerprint()
        self.schedule('schedulerfunction', 10 , self.schedulerfunction, repeat=True)
        self.schedule('update plugin', laps_time_update_plugin, self.update_plugin, repeat=True)
        if self.config.netchanging == 1:
            logging.warning("Network Changing enable")
            self.schedule('check network', laps_time_networkMonitor, self.networkMonitor, repeat=True)
        else:
            logging.warning("Network Changing disable")
        self.schedule('check AGENT INSTALL', 350, self.checkinstallagent, repeat=True)
        self.schedule('manage session', laps_time_handlemanagesession, self.handlemanagesession, repeat=True)
        if self.config.agenttype in ['relayserver']:
            self.schedule('reloaddeploy', 15, self.reloaddeploy, repeat=True)

            # ######################Update remote agent#########################
            self.diragentbase = os.path.join('/', 'var', 'lib', 'pulse2', 'xmpp_baseremoteagent')
            self.Update_Remote_Agentlist = Update_Remote_Agent(
                self.diragentbase, True)
            # ######################Update remote agent#########################

        # we make sure that the temp for the inventories is greater than or equal to 1 hour.
        # if the time for the inventories is 0, it is left at 0.
        # this deactive cycle inventory
        if self.config.inventory_interval != 0:
            if self.config.inventory_interval < 3600:
                self.config.inventory_interval = 3600
                logging.warning("chang minimun time cyclic inventory : 3600")
                logging.warning("we make sure that the time for the inventories is greater than or equal to 1 hour.")
            self.schedule('event inventory', self.config.inventory_interval, self.handleinventory, repeat=True)
        else:
            logging.warning("not enable cyclic inventory")

        #self.schedule('queueinfo', 10 , self.queueinfo, repeat=True)
        if  not self.config.agenttype in ['relayserver']:
            self.schedule('session reload', 15, self.reloadsesssion, repeat=False)

        self.schedule('reprise_evenement', 10, self.handlereprise_evenement, repeat=True)

        self.add_event_handler("register", self.register, threaded=True)
        self.add_event_handler("session_start", self.start)
        self.add_event_handler('message', self.message, threaded=True)
        self.add_event_handler("signalsessioneventrestart", self.signalsessioneventrestart)
        self.add_event_handler("loginfotomaster", self.loginfotomaster)
        self.add_event_handler('changed_status', self.changed_status)

        self.RSA = MsgsignedRSA(self.config.agenttype)

        #### manage information extern for Agent RS(relayserver only dont working on windows.)
        ##################
        if  self.config.agenttype in ['relayserver']:
            from lib.manage_info_command import manage_infoconsole
            self.qin = Queue(10)
            self.qoutARS = Queue(10)
            QueueManager.register('json_to_ARS' , self.setinARS)
            QueueManager.register('json_from_ARS', self.getoutARS)
            QueueManager.register('size_nb_msg_ARS' , self.sizeoutARS)
            #queue_in, queue_out, objectxmpp
            self.commandinfoconsole = manage_infoconsole(self.qin, self.qoutARS, self)
            self.managerQueue = QueueManager(("", self.config.parametersscriptconnection['port']),
                                            authkey = self.config.passwordconnection)
            self.managerQueue.start()

        if sys.platform.startswith('win'):
            result = win32api.SetConsoleCtrlHandler(self._CtrlHandler, 1)
            if result == 0:
                logging.log(DEBUGPULSE,'Could not SetConsoleCtrlHandler (error %r)' %
                             win32api.GetLastError())
            else:
                logging.log(DEBUGPULSE,'Set handler for console events.')
                self.is_set = True
        elif sys.platform.startswith('linux') :
            signal.signal(signal.SIGINT, self.signal_handler)
        elif sys.platform.startswith('darwin'):
            signal.signal(signal.SIGINT, self.signal_handler)

        self.register_handler(handler.Callback(
                                    'CustomXEP Handler',
                                    matcher.MatchXPath('{%s}iq/{%s}query' % (self.default_ns,"custom_xep")),
                                    self._handle_custom_iq))

    def handle_client_connection(self, client_socket):
        """
        this function handles the message received from kiosk
        the function must provide a response to an acknowledgment kiosk or a result
        Args:
            client_socket: socket for exchanges between AM and Kiosk

        Returns:
            no return value
        """
        try:
            # request the recv message
            recv_msg_from_kiosk = client_socket.recv(1024)
            if len(recv_msg_from_kiosk) != 0:
                print 'Received {}'.format(recv_msg_from_kiosk)
                datasend = { 'action' : "resultkiosk",
                            "sessionid" : getRandomName(6, "kioskGrub"),
                            "ret" : 0,
                            "base64" : False,
                            'data': {}}
                msg = str(recv_msg_from_kiosk.decode("utf-8", 'ignore'))
                result = json.loads(msg)
                if 'uuid' in result:
                    datasend['data']['uuid'] = result['uuid']
                if 'utcdatetime' in result:
                    datasend['data']['utcdatetime'] = result['utcdatetime']
                if 'action' in result:
                    if result['action'] == "kioskinterface":
                        #start kiosk ask initialization
                        datasend['data']['subaction'] =  result['subaction']
                        datasend['data']['userlist'] = list(set([users[0]  for users in psutil.users()]))
                        datasend['data']['ouuser'] = organizationbyuser(datasend['data']['userlist'])
                        datasend['data']['oumachine'] = organizationbymachine()
                    elif result['action'] == 'kioskinterfaceInstall':
                        datasend['data']['subaction'] =  'install'
                    elif result['action'] == 'kioskinterfaceLaunch':
                        datasend['data']['subaction'] =  'launch'
                    elif result['action'] == 'kioskinterfaceDelete':
                        datasend['data']['subaction'] =  'delete'
                    elif result['action'] == 'kioskinterfaceUpdate':
                        datasend['data']['subaction'] =  'update'

                    elif result['action'] == 'kioskLog':
                        if 'message' in result and result['message'] != "":
                            self.xmpplog(
                                        result['message'],
                                        type = 'noset',
                                        sessionname = '',
                                        priority = 0,
                                        action = "",
                                        who = self.boundjid.bare,
                                        how = "Planned",
                                        why = "",
                                        module = "Kiosk | Notify",
                                        fromuser = "",
                                        touser = "")
                            if 'type' in result:
                                if result['type'] == "info":
                                    logging.getLogger().info(result['message'])
                                elif result['type'] == "warning":
                                    logging.getLogger().warning(result['message'])
                    self.send_message_to_master(datasend)

            ### Received {'uuid': 45d4-3124c21-3123, 'action': 'kioskinterfaceInstall', 'subaction': 'Install'}
            # send result or acquit
            ###client_socket.send(recv_msg_from_kiosk)
        finally:
            client_socket.close()

    def established_connection(self):
        """ check connection xmppmaster """
        if not connection_established(self.config.Port):
            #restart restartBot
            logger.info("RESTART AGENT lost Connection")
            self.restartBot()

    def tcpserver(self):
        """
            this function is the listening function of the tcp server of the machine agent, to serve the request of the kiosk
            Args:
                no arguments

            Returns:
                no return value
        """
        logging.debug("Server Kiosk Start")

        while not self.eventkill.wait(1):
            try:
                rr,rw,err = select.select([self.sock],[],[self.sock], 20)
            except Exception as e:
                logging.error("kiosk server : %s" % str(e))
                self.sock.close()
                # connection error event here, maybe reconnect
                logging.error('Quit connection kiosk')
                break
            if rr:
                clientsocket, client_address = self.sock.accept()
                logging.debug('connection kiosk')
                client_handler = threading.Thread(
                                                    target=self.handle_client_connection,
                                                    args=(clientsocket,)).start()
            if err:
                self.sock.close()
                logging.error('Quit connection kiosk')
                break;
        self.quitserverkiosk = True
        logging.debug("Stopping Kiosk")

    def reloaddeploy(self):
        for sessionidban in self.ban_deploy_sessionid_list:
            self.managefifo.delsessionfifo(sessionidban)
            self.session.currentresource.discard(sessionidban)
        while (self.managefifo.getcount() != 0 and\
            len(self.session.currentresource) < self.config.concurrentdeployments):

            data = self.managefifo.getfifo()
            logging.debug("GET fifo %s"%self.session.resource)

            datasend = { "action": data['action'],
                        "sessionid" : data['sessionid'],
                        "ret" : 0,
                        "base64" : False
                    }
            self.session.currentresource.add(data['sessionid'])
            del data['action']
            del data['sessionid']
            self.levelcharge = self.levelcharge - 1
            datasend['data'] = data
            self.send_message(  mto = self.boundjid.bare,
                                mbody = json.dumps(datasend),
                                mtype = 'chat')

    def _handle_custom_iq(self, iq):
        if iq['type'] == 'get':
            for child in iq.xml:
                if child.tag.endswith('query'):
                    for z in child:
                        data = z.tag[1:-5]
                        try:
                            data = base64.b64decode(data)
                        except Exception as e:
                            logging.error("_handle_custom_iq : decode base64 : %s"%str(e))
                            traceback.print_exc(file=sys.stdout)
                            return
                        try:
                            # traitement de la function
                            # result json str
                            result = dispach_iq_command(self, data)
                            try:
                                result = result.encode("base64")
                            except Exception as e:
                                logging.error("_handle_custom_iq : encode base64 : %s"%str(e))
                                traceback.print_exc(file=sys.stdout)
                                return ""
                        except Exception as e:
                            logging.error("_handle_custom_iq : error function : %s"%str(e))
                            traceback.print_exc(file=sys.stdout)
                            return
            #retourn result iq get
            for child in iq.xml:
                if child.tag.endswith('query'):
                    for z in child:
                        z.tag = '{%s}data' % result
            iq['to'] = iq['from']
            iq.reply(clear=False)
            iq.send()
        elif iq['type'] == 'set':
            pass
        else:
            pass

    def checklevelcharge(self, ressource = 0):
        self.levelcharge = self.levelcharge + ressource
        if self.levelcharge < 0 :
            self.levelcharge = 0
        return self.levelcharge

    def signal_handler(self, signal, frame):
        logging.log(DEBUGPULSE, "CTRL-C EVENT")
        global signalint
        signalint = True
        msgevt={
                    "action": "evtfrommachine",
                    "sessionid" : getRandomName(6, "eventwin"),
                    "ret" : 0,
                    "base64" : False,
                    'data' : { 'machine' : self.boundjid.jid ,
                               'event'   : "CTRL_C_EVENT" }
                    }
        self.send_message_to_master(msgevt)
        sys.exit(0)

    def send_message_to_master(self , msg):
        self.send_message(  mbody = json.dumps(msg),
                            mto = '%s/MASTER'%self.agentmaster,
                            mtype ='chat')

    def _CtrlHandler(self, evt):
        """## todo intercep message in console program
        win32con.WM_QUERYENDSESSION win32con.WM_POWERBROADCAS(PBT_APMSUSPEND
        """
        global signalint
        if sys.platform.startswith('win'):
            msgevt={
                    "action": "evtfrommachine",
                    "sessionid" : getRandomName(6, "eventwin"),
                    "ret" : 0,
                    "base64" : False,
                    'data' : { 'machine' : self.boundjid.jid }
                    }
            if evt == win32con.CTRL_SHUTDOWN_EVENT:
                msgevt['data']['event'] = "SHUTDOWN_EVENT"
                self.send_message_to_master(msgevt)
                logging.log(DEBUGPULSE, "CTRL_SHUTDOWN EVENT")
                signalint = True
                return True
            elif evt == win32con.CTRL_LOGOFF_EVENT:
                msgevt['data']['event'] = "LOGOFF_EVENT"
                self.send_message_to_master(msgevt)
                logging.log(DEBUGPULSE, "CTRL_LOGOFF EVENT")
                return True
            elif evt == win32con.CTRL_BREAK_EVENT:
                msgevt['data']['event'] = "BREAK_EVENT"
                self.send_message_to_master(msgevt)
                logging.log(DEBUGPULSE, "CTRL_BREAK EVENT")
                return True
            elif evt == win32con.CTRL_CLOSE_EVENT:
                msgevt['data']['event'] = "CLOSE_EVENT"
                self.send_message_to_master(msgevt)
                logging.log(DEBUGPULSE, "CTRL_CLOSE EVENT")
                return True
            elif evt == win32con.CTRL_C_EVENT:
                msgevt['data']['event'] = "CTRL_C_EVENT"
                self.send_message_to_master(msgevt)
                logging.log(DEBUGPULSE, "CTRL-C EVENT")
                signalint = True
                sys.exit(0)
                return True
            else:
                return False
        else:
            pass


    def __sizeout(self, q):
        return q.qsize()

    def sizeoutARS(self):
        return self.__sizeout(self.qoutARS)

    def __setin(self, data , q):
        self.qin.put(data)

    def setinARS(self, data):
        self.__setin(data , self.qoutARS)

    def __getout(self, timeq, q):
        try:
            valeur = q.get(True, timeq)
        except Exception:
            valeur=""
        return valeur

    def getoutARS(self, timeq=10):
        return self.__getout(timeq, self.qoutARS)

    def gestioneventconsole(self, event, q):
        try:
            dataobj = json.loads(event)
        except Exception as e:
            logging.error("bad struct jsopn Message console %s : %s " %(event, str(e)))
            q.put("bad struct jsopn Message console %s : %s " %(event, str(e)))
        listaction = [] # cette liste contient les function directement appelable depuis console.
        #check action in message
        if 'action' in dataobj:
            if not 'sessionid' in dataobj:
                dataobj['sessionid'] = getRandomName(6, dataobj["action"])
            if dataobj["action"] in listaction:
                #call fubnction agent direct
                func = getattr(self, dataobj["action"])
                if "params_by_val" in dataobj and not "params_by_name" in dataobj:
                    func(*dataobj["params_by_val"])
                elif "params_by_val" in dataobj and "params_by_name" in dataobj:
                    func(*dataobj["params_by_val"], **dataobj["params_by_name"])
                elif "params_by_name" in dataobj and not "params_by_val" in dataobj:
                    func( **dataobj["params_by_name"])
                else :
                    func()
            else:
                #call plugin
                dataerreur = { "action" : "result" + dataobj["action"],
                               "data" : { "msg" : "error plugin : "+ dataobj["action"]
                               },
                               'sessionid' : dataobj['sessionid'],
                               'ret' : 255,
                               'base64' : False
                }
                msg = {'from' : 'console', "to" : self.boundjid.bare, 'type' : 'chat' }
                if not 'data' in dataobj:
                    dataobj['data'] = {}
                call_plugin(dataobj["action"],
                    self,
                    dataobj["action"],
                    dataobj['sessionid'],
                    dataobj['data'],
                    msg,
                    dataerreur)
        else:
            logging.error("action missing in json Message console %s" %(dataobj))
            q.put("action missing in jsopn Message console %s" %(dataobj))
            return
    ##################

    def remove_sessionid_in_ban_deploy_sessionid_list(self):
        """
            this function remove sessionid banned
        """
        # renove if timestamp is 10000 millis seconds.
        d = time.time()
        for sessionidban, timeban in self.banterminate.items():
            if (d - self.banterminate[sessionidban]) > 60:
                del self.banterminate[sessionidban]
                try:
                    self.ban_deploy_sessionid_list.remove(sessionidban)
                except Exception as e:
                    logger.warning(str(e))

    def schedulerfunction(self):
        self.manage_scheduler.process_on_event()

    def changed_status(self, message):
        #print "%s %s"%(message['from'], message['type'])
        if message['from'].user == 'master':
            if message['type'] == 'available':
                self.update_plugin()
        else:
            if self.config.agenttype in ['machine']:
                if self.boundjid.bare != message['from'].bare :
                    try:
                        if message['type'] == 'available':
                            self.machinerelayserver.append(message['from'].bare)
                        elif message['type'] == 'unavailable':
                            self.machinerelayserver.remove(message['from'].bare)
                    except Exception:
                        pass

    def start(self, event):
        self.get_roster()
        self.send_presence()
        logging.log(DEBUGPULSE,"subscribe xmppmaster")
        self.send_presence ( pto = self.agentmaster , ptype = 'subscribe' )
        self.ipconnection = self.config.Server

        if  self.config.agenttype in ['relayserver']:
            try:
                if self.config.public_ip_relayserver != "":
                    logging.log(DEBUGPULSE,"Attribution ip public by configuration for ipconnexion: [%s]"%self.config.public_ip_relayserver)
                    self.ipconnection = self.config.public_ip_relayserver
            except Exception:
                pass

        self.config.ipxmpp = getIpXmppInterface(self.config.Server, self.config.Port)

        self.agentrelayserverrefdeploy = self.config.jidchatroomcommand.split('@')[0][3:]
        logging.log(DEBUGPULSE,"Roster agent \n%s"%self.client_roster)

        self.xmpplog("Start Agent",
                    type = 'info',
                    sessionname = "",
                    priority = -1,
                    action = "",
                    who = self.boundjid.bare,
                    how = "",
                    why = "",
                    module = "AM",
                    date = None ,
                    fromuser = "MASTER",
                    touser = "")
        #notify master conf error in AM
        dataerrornotify = {
                            'to' : self.boundjid.bare,
                            'action': "notify",
                            "sessionid" : getRandomName(6, "notify"),
                            'data' : { 'msg' : "",
                                       'type': 'error'
                                      },
                            'ret' : 0,
                            'base64' : False
                    }

        if not os.path.isdir(self.config.defaultdir):
            dataerrornotify['data']['msg'] =  "Configurateur error browserfile on machine %s: defaultdir %s does not exit\n"%(self.boundjid.bare, self.config.defaultdir)
            self.send_message(  mto = self.agentmaster,
                                mbody = json.dumps(dataerrornotify),
                                mtype = 'chat')

        if not os.path.isdir(self.config.rootfilesystem):
            dataerrornotify['data']['msg'] += "Configurateur error browserfile on machine %s: rootfilesystem %s does not exit"%(self.boundjid.bare, self.config.rootfilesystem)
        #send notify
        if dataerrornotify['data']['msg'] !="":
            self.send_message(  mto = self.agentmaster,
                                    mbody = json.dumps(dataerrornotify),
                                    mtype = 'chat')
        #call plugin start
        startparameter={
            "action": "start",
            "sessionid" : getRandomName(6, "start"),
            "ret" : 0,
            "base64" : False,
            "data" : {}}
        dataerreur={ "action" : "result" + startparameter["action"],
                     "data" : { "msg" : "error plugin : "+ startparameter["action"]},
                     'sessionid' : startparameter['sessionid'],
                     'ret' : 255,
                     'base64' : False}
        msg = {'from' : self.boundjid.bare, "to" : self.boundjid.bare, 'type' : 'chat' }
        if not 'data' in startparameter:
            startparameter['data'] = {}
        call_plugin(startparameter["action"],
            self,
            startparameter["action"],
            startparameter['sessionid'],
            startparameter['data'],
            msg,
            dataerreur)


    def send_message_agent( self,
                            mto,
                            mbody,
                            msubject=None,
                            mtype=None,
                            mhtml=None,
                            mfrom=None,
                            mnick=None):
        if mto != "console":
            print "send command %s"%json.dumps(mbody)
            self.send_message(
                                mto,
                                json.dumps(mbody),
                                msubject,
                                mtype,
                                mhtml,
                                mfrom,
                                mnick)
        else :
            if self.config.agenttype in ['relayserver']:
                q = self.qoutARS
            else:
                q = self.qoutAM
            if q.full():
                #vide queue
                while not q.empty():
                    q.get()
            else:
                try :
                    q.put(json.dumps(mbody), True, 10)
                except Exception:
                    print "put in queue impossible"

    def logtopulse(self, text, type = 'noset', sessionname = '', priority = 0, who =""):
        if who == "":
            who = self.boundjid.bare
        msgbody = {
                    'text' : text,
                    'type':type,
                    'session':sessionname,
                    'priority':priority,
                    'who':who
                    }
        self.send_message(  mto = jid.JID("log@pulse"),
                            mbody=json.dumps(msgbody),
                            mtype='chat')

    def xmpplog(self,
                text,
                type = 'noset',
                sessionname = '',
                priority = 0,
                action = "",
                who = "",
                how = "",
                why = "",
                module = "",
                date = None ,
                fromuser = "",
                touser = ""):
        if who == "":
            who = self.boundjid.bare
        msgbody = { 'log' : 'xmpplog',
                    'text' : text,
                    'type': type,
                    'session' : sessionname,
                    'priority': priority,
                    'action' : action ,
                    'who': who,
                    'how' : how,
                    'why' : why,
                    'module': module,
                    'date' : None ,
                    'fromuser' : fromuser,
                    'touser' : touser
                    }
        self.send_message(  mto = jid.JID("log@pulse"),
                            mbody=json.dumps(msgbody),
                            mtype='chat')

    def handleinventory(self):
        msg={ 'from' : "master@pulse/MASTER",
              'to': self.boundjid.bare
            }
        sessionid = getRandomName(6, "inventory")
        dataerreur = {}
        dataerreur['action']= "resultinventory"
        dataerreur['data']={}
        dataerreur['data']['msg'] = "ERROR : inventory"
        dataerreur['sessionid'] = sessionid
        dataerreur['ret'] = 255
        dataerreur['base64'] = False

        self.xmpplog("Sent Inventory from agent"\
                     " %s (Interval : %s)"%( self.boundjid.bare,
                                            self.config.inventory_interval),
                                            type = 'noset',
                                            sessionname = '',
                                            priority = 0,
                                            action = "",
                                            who = self.boundjid.bare,
                                            how = "Planned",
                                            why = "",
                                            module = "Inventory | Inventory reception | Planned",
                                            fromuser = "",
                                            touser = "")

        call_plugin("inventory",
                    self,
                    "inventory",
                    getRandomName(6, "inventory"),
                    {},
                    msg,
                    dataerreur)

    def update_plugin(self):
        # Send plugin and machine informations to Master
        dataobj  = self.seachInfoMachine()
        logging.log(DEBUGPULSE,"SEND REGISTRATION XMPP to %s \n%s"%(self.sub_registration,
                                                                    json.dumps(dataobj,
                                                                               indent=4)))

        self.send_message(  mto=self.sub_registration,
                            mbody = json.dumps(dataobj),
                            mtype = 'chat')


    def reloadsesssion(self):
        # reloadsesssion only for machine
        # retrieve existing sessions
        if not self.session.loadsessions():
            return
        logging.log(DEBUGPULSE,"RELOAD SESSION DEPLOY")
        try:
            # load back to deploy after read session
            self.back_to_deploy = load_back_to_deploy()
            logging.log(DEBUGPULSE,"RELOAD DEPENDENCY MANAGER")
        except IOError:
            self.back_to_deploy = {}
        cleanbacktodeploy(self)
        for i in self.session.sessiondata:
            logging.log(DEBUGPULSE,"DEPLOYMENT AFTER RESTART OU RESTART BOT")
            msg={
                'from' : self.boundjid.bare,
                'to': self.boundjid.bare
            }
            call_plugin( i.datasession['action'],
                        self,
                        i.datasession['action'],
                        i.datasession['sessionid'],
                        i.datasession['data'],
                        msg,
                        {}
            )

    def loginfotomaster(self, msgdata):
        logstruct={
                    "action": "infolog",
                    "sessionid" : getRandomName(6, "xmpplog"),
                    "ret" : 0,
                    "base64" : False,
                    "msg":  msgdata }
        try:
            self.send_message(  mbody = json.dumps(logstruct),
                                mto = '%s/MASTER'%self.agentmaster,
                                mtype ='chat')
        except Exception as e:
            logging.error("message log to '%s/MASTER' : %s " %  ( self.agentmaster,str(e)))
            traceback.print_exc(file=sys.stdout)
            return

    def handlereprise_evenement(self):
        #self.eventTEVENT = [i for i in self.eventTEVENT if self.session.isexist(i['sessionid'])]
        #appelle plugins en local sur un evenement
        self.eventmanage.manage_event_loop()

    def signalsessioneventrestart(self,result):
        pass

    def handlemanagesession(self):
        self.session.decrementesessiondatainfo()

    def networkMonitor(self):
        try:
            logging.log(DEBUGPULSE,"network monitor time 180s %s!" % self.boundjid.user)
            md5ctl = createfingerprintnetwork()
            force_reconfiguration = os.path.join(os.path.dirname(os.path.realpath(__file__)), "action_force_reconfiguration")
            if self.md5reseau != md5ctl or os.path.isfile(force_reconfiguration):
                if not os.path.isfile(force_reconfiguration):
                    refreshfingerprint()
                    logging.log(DEBUGPULSE,"by network changed. The reconfiguration of the agent [%s] will be executed." % self.boundjid.user)
                else:
                    logging.log(DEBUGPULSE,"by request. The reconfiguration of the agent [%s] will be executed." % self.boundjid.user)
                    os.remove(force_reconfiguration)
                #### execution de convigurateur.
                #### timeout 5 minutes.
                namefilebool = os.path.join(os.path.dirname(os.path.realpath(__file__)), "BOOLCONNECTOR")
                nameprogconnection = os.path.join(os.path.dirname(os.path.realpath(__file__)), "connectionagent.py")
                if os.path.isfile(namefilebool):
                    os.remove(namefilebool)

                args = ['python', nameprogconnection, '-t', 'machine']
                subprocess.call(args)

                for i in range(15):
                    if os.path.isfile(namefilebool):
                        break
                    time.sleep(2)
                logging.log(DEBUGPULSE,"RESTART AGENT [%s] for new configuration" % self.boundjid.user)
                self.restartBot()
        except Exception as e:
            logging.error(" %s " %(str(e)))
            traceback.print_exc(file=sys.stdout)

    def checkinstallagent(self):
        # verify si boollean existe.
        if self.config.updating == 1:
            if os.path.isfile(os.path.join(self.pathagent, "BOOL_UPDATE_AGENT")):
                Update_Remote_Agenttest = Update_Remote_Agent(self.pathagent, True )
                Update_Remote_Img   = Update_Remote_Agent(self.img_agent, True )
                if Update_Remote_Agenttest.get_fingerprint_agent_base() != Update_Remote_Img.get_fingerprint_agent_base():
                    os.remove(os.path.join(self.pathagent, "BOOL_UPDATE_AGENT"))
                    #reinstall agent from img_agent
                    if sys.platform.startswith('win'):
                        import _winreg
                        for fichier in Update_Remote_Img.get_md5_descriptor_agent()['program_agent']:
                            os.system('copy  %s %s'%(os.path.join(self.img_agent, fichier),
                                                    os.path.join(self.pathagent, fichier)))
                            logger.debug('install program agent  %s to %s'%(os.path.join(self.img_agent, fichier),
                                                                            os.path.join(self.pathagent)))
                        os.system('copy  %s %s'%(os.path.join(self.img_agent, "agentversion"),
                                                os.path.join(self.pathagent, "agentversion")))
                        key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,
                                             "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Pulse Agent\\",
                                             0 ,
                                             _winreg.KEY_SET_VALUE | _winreg.KEY_WOW64_64KEY)
                        _winreg.SetValueEx ( key,
                                           'DisplayVersion'  ,
                                           0,
                                           _winreg.REG_SZ,
                                           file_get_contents(os.path.join(self.pathagent, "agentversion")).strip())
                        _winreg.CloseKey(key)

                        for fichier in Update_Remote_Img.get_md5_descriptor_agent()['lib_agent']:
                            os.system('copy  %s %s'%(os.path.join(self.img_agent, "lib", fichier),
                                                    os.path.join(self.pathagent, "lib", fichier)))
                            logger.debug('install lib agent  %s to %s'%(os.path.join(self.img_agent, "lib", fichier),
                                                                        os.path.join(self.pathagent, "lib", fichier)))
                        for fichier in Update_Remote_Img.get_md5_descriptor_agent()['script_agent']:
                            os.system('copy  %s %s'%(os.path.join(self.img_agent, "script", fichier),
                                                    os.path.join(self.pathagent, "script", fichier)))
                            logger.debug('install script agent %s to %s'%(os.path.join(self.img_agent, "script", fichier),
                                                                        os.path.join(self.pathagent, "script", fichier)))

                    elif sys.platform.startswith('linux') or sys.platform.startswith('darwin'):
                        os.system('cp  %s/*.py %s'%(self.img_agent, self.pathagent))
                        os.system('cp  %s/script/* %s/script/'%(self.img_agent, self.pathagent))
                        os.system('cp  %s/lib/*.py %s/lib/'%(self.img_agent, self.pathagent))
                        os.system('cp  %s/agentversion %s/agentversion'%(self.img_agent, self.pathagent))
                        logger.debug('cp  %s/*.py %s'%(self.img_agent, self.pathagent))
                        logger.debug('cp  %s/script/* %s/script/'%(self.img_agent, self.pathagent))
                        logger.debug('cp  %s/lib/*.py %s/lib/'%(self.img_agent, self.pathagent))
                        logger.debug('cp  %s/agentversion %s/agentversion'%(self.img_agent, self.pathagent))
                    else:
                        logger.error("reinstall agent copy file error os missing")

    def restartBot(self):
        global restart
        restart = True
        logging.log(DEBUGPULSE,"restart xmpp agent %s!" % self.boundjid.user)
        self.disconnect(wait=10)

    def register(self, iq):
        """ This function is called for automatic registation """
        resp = self.Iq()
        resp['type'] = 'set'
        resp['register']['username'] = self.boundjid.user
        resp['register']['password'] = self.password
        try:
            resp.send(now=True)
            logging.info("Account created for %s!" % self.boundjid)
        except IqError as e:
            logging.error("Could not register account: %s" %\
                    e.iq['error']['text'])
        except IqTimeout:
            logging.error("No response from server.")
            traceback.print_exc(file=sys.stdout)
            self.disconnect()

    def filtre_message(self, msg):
        pass

    def message(self, msg):
        possibleclient = ['master', self.agentcommand.user, self.agentsiveo.user, self.boundjid.user,'log',self.jidchatroomcommand.user]
        if not msg['type'] == "chat":
            return
        try :
            dataobj = json.loads(msg['body'])

        except Exception as e:
            logging.error("bad struct Message %s %s " %(msg, str(e)))
            dataerreur={
                    "action": "resultmsginfoerror",
                    "sessionid" : "",
                    "ret" : 255,
                    "base64" : False,
                    "data": {"msg" : "ERROR : Message structure"}
        }
            self.send_message(  mto=msg['from'],
                                        mbody=json.dumps(dataerreur),
                                        mtype='chat')
            traceback.print_exc(file=sys.stdout)
            return

        if not msg['from'].user in possibleclient:
            if not('sessionid' in  dataobj and self.session.isexist(dataobj['sessionid'])):
                #les messages venant d'une machine sont filtré sauf si une session message existe dans le gestionnaire de session.
                if  self.config.ordreallagent:
                    logging.warning("filtre message from %s " % (msg['from'].bare))
                    return

        dataerreur={
                    "action": "resultmsginfoerror",
                    "sessionid" : "",
                    "ret" : 255,
                    "base64" : False,
                    "data": {"msg" : ""}
        }

        if not 'action' in dataobj:
            logging.error("warning message action missing %s"%(msg))
            return

        if dataobj['action'] == "restarfrommaster":
            reboot_command()

        if dataobj['action'] == "shutdownfrommaster":
            msg = "\"Shutdown from administrator\""
            time = 15 # default 15 seconde
            if 'time' in dataobj['data'] and dataobj['data']['time'] != 0:
                time = dataobj['data']['time']
            if 'msg' in dataobj['data'] and dataobj['data']['msg'] != "":
                msg = '"' + dataobj['data']['msg'] + '"'

            shutdown_command(time, msg)

        if dataobj['action'] == "vncchangepermsfrommaster":
            askpermission = 1
            if 'askpermission' in dataobj['data'] and dataobj['data']['askpermission'] == '0':
                askpermission = 0

            vnc_set_permission(askpermission)

        if dataobj['action'] == "installkeymaster":
            # note install publickeymaster
            self.masterpublickey = installpublickey("master", dataobj['keypublicbase64'] )
            return

        if dataobj['action'] ==  "resultmsginfoerror":
            logging.warning("filtre message from %s for action %s" % (msg['from'].bare,dataobj['action']))
            return
        try :
            if dataobj.has_key('action') and dataobj['action'] != "" and dataobj.has_key('data'):
                if dataobj.has_key('base64') and \
                    ((isinstance(dataobj['base64'],bool) and dataobj['base64'] == True) or
                    (isinstance(dataobj['base64'],str) and dataobj['base64'].lower()=='true')):
                        #data in base 64
                        mydata = json.loads(base64.b64decode(dataobj['data']))
                else:
                    mydata = dataobj['data']

                if not dataobj.has_key('sessionid'):
                    dataobj['sessionid']= getRandomName(6, "xmpp")
                    logging.warning("sessionid missing in message from %s : attributed sessionid %s " % (msg['from'],dataobj['sessionid']))
                else:
                    if dataobj['sessionid'] in self.ban_deploy_sessionid_list:
                        ## abort deploy if msg session id is banny
                        logging.info("DEPLOYMENT ABORT Sesion %s"%dataobj['sessionid'])
                        self.xmpplog("<span  style='color:red;'>DEPLOYMENT ABORT</span>",
                                    type = 'deploy',
                                    sessionname = dataobj['sessionid'],
                                    priority = -1,
                                    action = "",
                                    who = self.boundjid.bare,
                                    how = "",
                                    why = "",
                                    module = "Deployment | Banned",
                                    date = None ,
                                    fromuser = "MASTER",
                                    touser = "")
                        return

                del dataobj['data']
                # traitement TEVENT
                # TEVENT event sended by remote machine ou RS
                # message adresse au gestionnaire evenement
                if 'Dtypequery' in mydata and mydata['Dtypequery'] == 'TEVENT' and self.session.isexist(dataobj['sessionid']):
                    mydata['Dtypequery'] = 'TR'
                    datacontinue = {
                            'to' : self.boundjid.bare,
                            'action': dataobj['action'],
                            'sessionid': dataobj['sessionid'],
                            'data' : dict(self.session.sessionfromsessiondata(dataobj['sessionid']).datasession.items() + mydata.items()),
                            'ret' : 0,
                            'base64' : False
                    }
                    #add Tevent gestion event
                    self.eventmanage.addevent(datacontinue)
                    return
                try:
                    msg['body'] = dataobj
                    logging.info("call plugin %s from %s" % (dataobj['action'],msg['from'].user))
                    call_plugin(dataobj['action'],
                                self,
                                dataobj['action'],
                                dataobj['sessionid'],
                                mydata,
                                msg,
                                dataerreur
                                )
                except TypeError:
                    if dataobj['action'] != "resultmsginfoerror":
                        dataerreur['data']['msg'] = "ERROR : plugin %s Missing"%dataobj['action']
                        dataerreur['action'] = "result%s"%dataobj['action']
                        self.send_message(  mto=msg['from'],
                                            mbody=json.dumps(dataerreur),
                                            mtype='chat')
                    logging.error("TypeError execution plugin %s : [ERROR : plugin Missing] %s" %(dataobj['action'],sys.exc_info()[0]))
                    traceback.print_exc(file=sys.stdout)

                except Exception as e:
                    logging.error("execution plugin [%s]  : %s " % (dataobj['action'],str(e)))
                    if dataobj['action'].startswith('result'):
                        return
                    if dataobj['action'] != "resultmsginfoerror":
                        dataerreur['data']['msg'] = "ERROR : plugin execution %s"%dataobj['action']
                        dataerreur['action'] = "result%s"%dataobj['action']
                        self.send_message(  mto=msg['from'],
                                            mbody=json.dumps(dataerreur),
                                            mtype='chat')
                    traceback.print_exc(file=sys.stdout)
            else:
                dataerreur['data']['msg'] = "ERROR : Action ignored"
                self.send_message(  mto=msg['from'],
                                        mbody=json.dumps(dataerreur),
                                        mtype='chat')
        except Exception as e:
            logging.error("bad struct Message %s %s " %(msg, str(e)))
            dataerreur['data']['msg'] = "ERROR : Message structure"
            self.send_message(  mto=msg['from'],
                                        mbody=json.dumps(dataerreur),
                                        mtype='chat')
            traceback.print_exc(file=sys.stdout)

    def seachInfoMachine(self):
        er = networkagentinfo("master", "infomachine")
        er.messagejson['info'] = self.config.information
        #send key public agent
        er.messagejson['publickey'] =  self.RSA.loadkeypublictobase64()
        #send if master public key public is missing
        er.messagejson['is_masterpublickey'] = self.RSA.isPublicKey("master")
        for t in er.messagejson['listipinfo']:
            # search network info used for xmpp
            if t['ipaddress'] == self.config.ipxmpp:
                xmppmask = t['mask']
                try:
                    xmppbroadcast = t['broadcast']
                except :
                    xmppbroadcast = ""
                xmppdhcp = t['dhcp']
                xmppdhcpserver = t['dhcpserver']
                xmppgateway = t['gateway']
                xmppmacaddress = t['macaddress']
                xmppmacnotshortened = t['macnotshortened']
                portconnection = self.config.Port
                break
        try:
            subnetreseauxmpp =  subnetnetwork(self.config.ipxmpp, xmppmask)
        except Exception:
            logreception = """
Imposible calculate subnetnetwork verify the configuration of %s [%s]
Check if ip [%s] is correct:
check if interface exist with ip %s

Warning Configuration machine %s
[connection]
server = It must be expressed in ip notation.

server = 127.0.0.1  correct
server = localhost in not correct
AGENT %s ERROR TERMINATE"""%(self.boundjid.bare,
                             er.messagejson['info']['hostname'],
                             self.config.ipxmpp,
                             self.config.ipxmpp,
                             er.messagejson['info']['hostname'],
                             self.boundjid.bare)
            self.loginfotomaster(logreception)
            sys.exit(0)

        if self.config.public_ip == None:
            self.config.public_ip = self.config.ipxmpp
        dataobj = {
            'action' : 'infomachine',
            'from' : self.config.jidagent,
            'compress' : False,
            'deployment' : self.config.jidchatroomcommand,
            'who'    : "%s/%s"%(self.config.jidchatroomcommand,self.config.NickName),
            'machine': self.config.NickName,
            'platform' : platform.platform(),
            'completedatamachine' : base64.b64encode(json.dumps(er.messagejson)),
            'plugin' : {},
            'pluginscheduled' : {},
            'portxmpp' : self.config.Port,
            'serverxmpp' : self.config.Server,
            'agenttype' : self.config.agenttype,
            'baseurlguacamole': self.config.baseurlguacamole,
            'subnetxmpp':subnetreseauxmpp,
            'xmppip' : self.config.ipxmpp,
            'xmppmask': xmppmask,
            'xmppbroadcast' : xmppbroadcast,
            'xmppdhcp' : xmppdhcp,
            'xmppdhcpserver' : xmppdhcpserver,
            'xmppgateway' : xmppgateway,
            'xmppmacaddress' : xmppmacaddress,
            'xmppmacnotshortened' : xmppmacnotshortened,
            'ipconnection':self.ipconnection,
            'portconnection':portconnection,
            'classutil' : self.config.classutil,
            'ippublic' : self.config.public_ip,
            'remoteservice' : protoandport(),
            'packageserver' : self.config.packageserver,
            'adorgbymachine' : base64.b64encode(organizationbymachine()),
            'adorgbyuser' : '',
            'kiosk_presence' : test_kiosk_presence(),
            'countstart' : save_count_start()
        }
        try:
            if  self.config.agenttype in ['relayserver']:
                dataobj["moderelayserver"] = self.config.moderelayserver
                if dataobj['moderelayserver'] == "dynamic":
                    dataobj['packageserver']['public_ip'] = self.config.ipxmpp
        except Exception:
            dataobj["moderelayserver"] = "static"
        ###################Update agent from MAster#############################
        if self.config.updating == 1:
            dataobj['md5agent'] = self.descriptorimage.get_fingerprint_agent_base()
        ###################End Update agent from MAster#############################
        #todo determination lastusersession to review
        lastusersession = ""
        userlist = list(set([users[0]  for users in psutil.users()]))
        if len(userlist) > 0:
            lastusersession = userlist[0]

        if lastusersession != "":
            dataobj['adorgbyuser'] = base64.b64encode(organizationbyuser(lastusersession))

        dataobj['lastusersession'] = lastusersession
        sys.path.append(self.config.pathplugins)
        for element in os.listdir(self.config.pathplugins):
            if element.endswith('.py') and element.startswith('plugin_'):
                mod = __import__(element[:-3])
                reload(mod)
                module = __import__(element[:-3]).plugin
                dataobj['plugin'][module['NAME']] = module['VERSION']
        #add list scheduler plugins
        dataobj['pluginscheduled'] = self.loadPluginschedulerList()
        #persistance info machine
        self.infomain = dataobj
        return dataobj

    def loadPluginschedulerList(self):
        logger.debug("Verify base plugin scheduler")
        plugindataseach = {}
        for element in os.listdir(self.config.pathpluginsscheduled):
            if element.endswith('.py') and element.startswith('scheduling_'):
                f = open(os.path.join(self.config.pathpluginsscheduled,element),'r')
                lignes  = f.readlines()
                f.close()
                for ligne in lignes:
                    if 'VERSION' in ligne and 'NAME' in ligne:
                        l=ligne.split("=")
                        plugin = eval(l[1])
                        plugindataseach[plugin['NAME']] = plugin['VERSION']
                        break
        return plugindataseach

    def muc_onlineMaster(self, presence):
        if presence['muc']['nick'] == self.config.NickName:
            return
        if presence['muc']['nick'] == "MASTER":
            self.update_plugin()

def createDaemon(optstypemachine, optsconsoledebug, optsdeamon, tglevellog, tglogfile):
    """
        This function create a service/Daemon that will execute a det. task
    """
    try:
        if sys.platform.startswith('win'):
            import multiprocessing
            p = multiprocessing.Process(name='xmppagent',target=doTask, args=(optstypemachine, optsconsoledebug, optsdeamon, tglevellog, tglogfile,))
            p.daemon = True
            p.start()
            p.join()
        else:
            # Store the Fork PID
            pid = os.fork()
            if pid > 0:
                print 'PID: %d' % pid
                os._exit(0)
            doTask(optstypemachine, optsconsoledebug, optsdeamon, tglevellog, tglogfile)
    except OSError, error:
        logging.error("Unable to fork. Error: %d (%s)" % (error.errno, error.strerror))
        traceback.print_exc(file=sys.stdout)
        os._exit(1)

def tgconf(optstypemachine):
    tg = confParameter(optstypemachine)

    if optstypemachine.lower() in ["machine"]:
        tg.pathplugins = os.path.join(os.path.dirname(os.path.realpath(__file__)), "pluginsmachine")
        tg.pathpluginsscheduled = os.path.join(os.path.dirname(os.path.realpath(__file__)), "descriptor_scheduler_machine")
    else:
        tg.pathplugins = os.path.join(os.path.dirname(os.path.realpath(__file__)), "pluginsrelay")
        tg.pathpluginsscheduled = os.path.join(os.path.dirname(os.path.realpath(__file__)), "descriptor_scheduler_relay")

    while True:
        if tg.Server == "" or tg.Port == "":
            logger.error("Error config ; Parameter Connection missing")
            sys.exit(1)
        if ipfromdns(tg.Server) != "" and   check_exist_ip_port(ipfromdns(tg.Server), tg.Port): break
        logging.log(DEBUGPULSE,"Unable to connect. (%s : %s) on xmpp server."\
            " Check that %s can be resolved"%(tg.Server,
                                              tg.Port,
                                              tg.Server))
        logging.log(DEBUGPULSE,"verify a information ip or dns for connection AM")
        if ipfromdns(tg.Server) == "" :
            logging.log(DEBUGPULSE, "not resolution adresse : %s "%tg.Server)
        time.sleep(2)
    return tg

def doTask( optstypemachine, optsconsoledebug, optsdeamon, tglevellog, tglogfile):
    global restart, signalint
    if platform.system()=='Windows':
        # Windows does not support ANSI escapes and we are using API calls to set the console color
        logging.StreamHandler.emit = add_coloring_to_emit_windows(logging.StreamHandler.emit)
    else:
        # all non-Windows platforms are supporting ANSI escapes so we use them
        logging.StreamHandler.emit = add_coloring_to_emit_ansi(logging.StreamHandler.emit)
    # format log more informations
    format = '%(asctime)s - %(levelname)s - %(message)s'
    # more information log
    # format ='[%(name)s : %(funcName)s : %(lineno)d] - %(levelname)s - %(message)s'
    if not optsdeamon :
        if optsconsoledebug :
            logging.basicConfig(level = logging.DEBUG, format=format)
        else:
            logging.basicConfig( level = tglevellog,
                                 format = format,
                                 filename = tglogfile,
                                 filemode = 'a')
    else:
        logging.basicConfig( level = tglevellog,
                             format = format,
                             filename = tglogfile,
                             filemode = 'a')
    if optstypemachine.lower() in ["machine"]:
        sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "pluginsmachine"))
    else:
        sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "pluginsrelay"))
    while True:
        restart = False
        tg = tgconf(optstypemachine)
        xmpp = MUCBot(tg)
        xmpp.auto_reconnect = False
        xmpp.register_plugin('xep_0030') # Service Discovery
        xmpp.register_plugin('xep_0045') # Multi-User Chat
        xmpp.register_plugin('xep_0004') # Data Forms
        xmpp.register_plugin('xep_0050') # Adhoc Commands
        xmpp.register_plugin('xep_0199', {'keepalive': True,
                                            'frequency':600,
                                            'interval' : 600,
                                            'timeout' : 500  })
        xmpp.register_plugin('xep_0077') # In-band Registration
        xmpp['xep_0077'].force_registration = True
        if xmpp.config.agenttype in ['relayserver']:
            attempt = True
        else:
            attempt = False
        if xmpp.connect(address=(ipfromdns(tg.Server),tg.Port), reattempt=attempt):
            xmpp.process(block=True)
            logging.log(DEBUGPULSE,"terminate infocommand")
            logging.log(DEBUGPULSE,"event for quit loop server tcpserver for kiosk")
        else:
            logging.log(DEBUGPULSE,"Unable to connect. search alternative")
            restart = False
        if signalint:
            logging.log(DEBUGPULSE,"bye bye Agent CTRL-C")
            terminateserver(xmpp)
            break
        logging.log(DEBUGPULSE,"analyse alternative")
        if not restart:
            logging.log(DEBUGPULSE,"not restart")
            # verify if signal stop
            # verify if alternative connection
            logging.log(DEBUGPULSE,"alternative connection")
            logging.log(DEBUGPULSE,"file %s"%conffilename("cluster"))
            if os.path.isfile(conffilename("cluster")):
                # il y a une configuration alternative
                logging.log(DEBUGPULSE, "alternative configuration")
                newparametersconnect = nextalternativeclusterconnection(conffilename("cluster"))
                changeconnection( conffilename(xmpp.config.agenttype),
                                newparametersconnect[2],
                                newparametersconnect[1],
                                newparametersconnect[0],
                                newparametersconnect[3])
        terminateserver(xmpp)


def terminateserver(xmpp):
    #event for quit loop server tcpserver for kiosk
    xmpp.eventkill.set()
    xmpp.sock.close()
    if  xmpp.config.agenttype in ['relayserver']:
        xmpp.qin.put("quit")
    xmpp.queue_read_event_from_command.put("quit")
    logging.log(DEBUGPULSE,"wait 2s end thread event loop")
    logging.log(DEBUGPULSE,"terminate manage data sharing")
    if  xmpp.config.agenttype in ['relayserver']:
        xmpp.managerQueue.shutdown()
    time.sleep(2)
    logging.log(DEBUGPULSE,"terminate scheduler")
    xmpp.scheduler.quit()
    logging.log(DEBUGPULSE,"waitting stop server kiosk")
    while not xmpp.quitserverkiosk:
        time.sleep(1)
    logging.log(DEBUGPULSE,"bye bye Agent")


if __name__ == '__main__':
    if sys.platform.startswith('linux') and  os.getuid() != 0:
        print "Agent must be running as root"
        sys.exit(0)
    elif sys.platform.startswith('win') and isWinUserAdmin() ==0 :
        print "Pulse agent must be running as Administrator"
        sys.exit(0)
    elif sys.platform.startswith('darwin') and not isMacOsUserAdmin():
        print "Pulse agent must be running as root"
        sys.exit(0)
    optp = OptionParser()
    optp.add_option("-d", "--deamon",action="store_true",
                 dest="deamon", default=False,
                  help="deamonize process")
    optp.add_option("-t", "--type",
                dest="typemachine", default=False,
                help="Type machine : machine or relayserver")
    optp.add_option("-c", "--consoledebug",action="store_true",
                dest="consoledebug", default = False,
                  help="console debug")

    opts, args = optp.parse_args()
    tg = confParameter(opts.typemachine)
    if not opts.deamon :
        doTask(opts.typemachine, opts.consoledebug, opts.deamon, tg.levellog, tg.logfile)
    else:
        createDaemon(opts.typemachine, opts.consoledebug, opts.deamon, tg.levellog, tg.logfile)
