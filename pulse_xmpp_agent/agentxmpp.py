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
import logging
import ConfigParser
import sleekxmpp
import platform
import netifaces
import random
import base64
import json
from sleekxmpp.exceptions import IqError, IqTimeout
from sleekxmpp import jid
import hashlib
import errno
from lib.networkinfo import networkagentinfo
from lib.configuration import confParameter
from lib.managesession import session
from lib.utils import *
from lib.manage_event import manage_event
from lib.manage_process import mannageprocess,process_on_end_send_message_xmpp
import traceback
import pluginsmachine
from optparse import OptionParser
import time
import pprint
from datetime import datetime
from multiprocessing import Process, Queue, TimeoutError
import threading
from lib.manage_scheduler import manage_scheduler
from lib.logcolor import  add_coloring_to_emit_ansi, add_coloring_to_emit_windows
from lib.manageRSAsigned import MsgsignedRSA, installpublickey
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib"))


logger = logging.getLogger()
global restart


if sys.version_info < (3, 0):
    reload(sys)
    sys.setdefaultencoding('utf8')
else:
    raw_input = input


class MUCBot(sleekxmpp.ClientXMPP):
    def __init__(self, conf):#jid, password, room, nick):
        logging.log(DEBUGPULSE, "start machine1  %s Type %s" %(conf.jidagent, conf.agenttype))
        logger.info("start machine1  %s Type %s" %(conf.jidagent, conf.agenttype))
        sleekxmpp.ClientXMPP.__init__(self, jid.JID(conf.jidagent), conf.passwordconnection)
        laps_time_update_plugin = 3600
        laps_time_networkMonitor = 300
        laps_time_handlemanagesession = 15
        self.config = conf
        self.manage_scheduler  = manage_scheduler(self)

        self.nicklistchatroomcommand = {}
        self.jidchatroomcommand = jid.JID(self.config.jidchatroomcommand)
        self.agentcommand = jid.JID(self.config.agentcommand)
        self.agentsiveo = jid.JID(self.config.jidagentsiveo)
        self.agentmaster = jid.JID("master@pulse")
        self.session = session(self.config.agenttype)

        self.signalinfo = {}
        self.queue_read_event_from_command = Queue()
        self.eventmanage = manage_event(self.queue_read_event_from_command, self)
        self.mannageprocess = mannageprocess(self.queue_read_event_from_command)
        self.process_on_end_send_message_xmpp = process_on_end_send_message_xmpp(self.queue_read_event_from_command)
        try:
            self.ippublic = searchippublic()
        except:
            self.ippublic = None
        if self.ippublic == "":
            self.ippublic == None
        self.md5reseau = refreshfingerprint()

        self.schedule('schedulerfunction', 10 , self.schedulerfunction, repeat=True)

        self.schedule('update plugin', laps_time_update_plugin, self.update_plugin, repeat=True)
        self.schedule('check network', laps_time_networkMonitor, self.networkMonitor, repeat=True)
        self.schedule('manage session', laps_time_handlemanagesession, self.handlemanagesession, repeat=True)
        self.schedule('manage session', self.config.inventory_interval, self.handleinventory, repeat=True)
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

    def schedulerfunction(self):
        self.manage_scheduler.process_on_event()

    def changed_status(self, message):
        print "%s %s"%(message['from'], message['type'])
        if message['from'].user == 'master' and message['type'] == 'available':
            self.update_plugin()

    def start(self, event):
        self.get_roster()
        self.send_presence()
        logging.log(DEBUGPULSE,"subscribe xmppmaster")
        self.send_presence ( pto = self.agentmaster , ptype = 'subscribe' )
        try :
            if self.config.public_ip != "":
                logging.log(DEBUGPULSE,"Attribution ip public by configuration : [%s]"%self.config.public_ip)
                self.config.ipxmpp = self.config.public_ip
            else:
                logging.warning("Attribution ip public by configuration : [%s]"%self.config.public_ip)
                raise AttributeError
        except AttributeError:
            self.config.ipxmpp = getIpXmppInterface(self.config.Server,self.config.Port)
        self.agentrelayserverrefdeploy = self.config.jidchatroomcommand.split('@')[0][3:]
        #self.config.ipxmpp = getIpXmppInterface(self.config.Server, self.config.Port)
        #self.loginfotomaster("agent %s ready"%self.config.jidagent)
        #self.update_plugin()
        logging.log(DEBUGPULSE,"Roster agent \n%s"%self.client_roster)
        self.logtopulse("Start Agent", who =  self.boundjid.bare)
        try:
            self.back_to_deploy = load_back_to_deploy()
        except IOError:
            self.back_to_deploy = {}

        cleanbacktodeploy(self)

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
        self.send_message(mto=jid.JID("log@pulse"),
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
        call_plugin("inventory",
                    self,
                    "inventory",
                    getRandomName(6, "inventory"),
                    {},
                    msg,
                    dataerreur)

    def update_plugin(self):
        # Send plugin and machine informations to Master
        dataobj=self.seachInfoMachine()
        logging.log(DEBUGPULSE,"SEND REGISTRATION XMPP to %s \n%s"%(self.agentmaster, json.dumps(dataobj, indent=4, sort_keys=True)))
        self.send_message(  mto = self.agentmaster,
                            mbody = json.dumps(dataobj),
                            mtype = 'chat')

    def reloadsesssion(self):
        #recupere les sessions existantes
        self.session.loadsessions()
        #if  not self.config.agenttype in ['relayserver']:
            #executer seulement par machine
        for i in self.session.sessiondata:
            logging.log(DEBUGPULSE,"REPRISE DE DEPLOIEMENT AFTER RESTART OU RESTART BOT")
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
                        {})

    def loginfotomaster(self, msgdata):
        # ne sont traite par master seulement action loginfos
        logstruct={
                    "action": "infolog",
                    "sessionid" : getRandomName(6, "xmpplog"),
                    "ret" : 0,
                    "base64" : False,
                    "msg" : msgdata }
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
            if self.md5reseau != md5ctl:
                refreshfingerprint()
                logging.log(DEBUGPULSE,"network changed for %s!\n RESTART AGENT" % self.boundjid.user)
                self.restartBot()
        except Exception as e:
            logging.error(" %s " %(str(e)))
            traceback.print_exc(file=sys.stdout)

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

    #def ischatroomdeploy(self, jidmessage ):
        #return jidmessage in self.nicklistchatroomcommand

    def message(self, msg):
        possibleclient = ['master', self.agentcommand.user, self.agentsiveo.user, self.boundjid.user,'log',self.jidchatroomcommand.user]
        if not msg['type'] == "chat":
            return
        try :
            dataobj = json.loads(msg['body'])
        except Exception as e:
            logging.error("bad struct Message %s %s " %(msg, str(e)))
            dataerreur['data']['msg'] = "ERROR : Message structure"
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
            if sys.platform.startswith('linux'):
                logging.debug("actionrestartmachine  shutdown machine linux")
                os.system("shutdown -r now")
            elif sys.platform.startswith('win'):
                logging.debug("actionrestartmachine  shutdown machine windows")
                os.system("shutdown /r")
            elif sys.platform.startswith('darwin'):
                logging.debug("actionrestartmachine  shutdown machine MacOS")
                os.system("shutdown -r now")
            return

        if dataobj['action'] == "shutdownfrommaster":
            if sys.platform.startswith('linux'):
                logging.debug("shutdown -P -f -t 3  \"restart from administrator\"")
                os.system("shutdown -P -f -t 3  \"restart from administrator\"")
            elif sys.platform.startswith('win'):
                logging.debug("shutdown -s -t 1 -f \"stop from administrator in 60 secondes\"")
                os.system("shutdown -s -t 1 -f \"stop from administrator in 60 secondes\"")
            elif sys.platform.startswith('darwin'):
                logging.debug("actionrestartmachine  shutdown machine MacOS")
                os.system("shutdown -s now \"restart from administrator\"")
            return

        if dataobj['action'] == "installkeymaster":
            # note install publickeymaster
            self.masterpublickey = installpublickey("master", dataobj['keypublicbase64'] )
            return

        if dataobj['action'] ==  "resultmsginfoerror":
            logging.warning("filtre message from %s for action %s" % (msg['from'].bare,dataobj['action']))
            return
        try :
            #if dataobj['action'] == "resultmsginfoerror":
                #logging.warning("filtre message from %s for action %s" % (msg['from'].bare,dataobj['action']))
                #return
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
                ipconnection = self.config.Server
                portconnection =self.config.Port
                break;

        try:
            subnetreseauxmpp =  subnetnetwork(self.config.ipxmpp, xmppmask)
        except Exception:
            logreception = """
Imposible calculate subnetnetwork verify the configuration of %s [%s]

Check if ip [%s] is correct:
If parameter of agent_type is relayserver and the parameter request_type is public,
you must set public_ip in type with an address that exists on the machine.
Otherwise the ip server parameter in the connection session is false
It must be expressed in ip notation.
It seems that mask for this ip [%s] does not exist
AGENT %s ERROR TERMINATE"""%( self.boundjid.bare,
                             er.messagejson['info']['hostname'],
                             self.config.ipxmpp,
                             self.config.ipxmpp,
                             self.boundjid.bare)
            self.loginfotomaster(logreception)
            sys.exit(0)
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
            'ipconnection':ipconnection,
            'portconnection':portconnection,
            'classutil' : self.config.classutil,
            'ippublic' : self.ippublic,
            'remoteservice' : protoandport(),
        }
        sys.path.append(self.config.pathplugins)
        for element in os.listdir(self.config.pathplugins):
            if element.endswith('.py') and element.startswith('plugin_'):
                mod = __import__(element[:-3])
                reload(mod)
                module = __import__(element[:-3]).plugin
                dataobj['plugin'][module['NAME']] = module['VERSION']
        return dataobj

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
            #doTask(optstypemachine, optsconsoledebug, optsdeamon, tglevellog, tglogfile)
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


def doTask( optstypemachine, optsconsoledebug, optsdeamon, tglevellog, tglogfile):
    global restart
    if platform.system()=='Windows':
        # Windows does not support ANSI escapes and we are using API calls to set the console color
        logging.StreamHandler.emit = add_coloring_to_emit_windows(logging.StreamHandler.emit)
    else:
        # all non-Windows platforms are supporting ANSI escapes so we use them
        logging.StreamHandler.emit = add_coloring_to_emit_ansi(logging.StreamHandler.emit)
    if not optsdeamon :
        if optsconsoledebug :
            logging.basicConfig(level = logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
        else:
            stdout_logger = logging.getLogger('STDOUT')
            sl = StreamToLogger(stdout_logger, tglevellog)
            sys.stdout = sl
            stderr_logger = logging.getLogger('STDERR')
            sl = StreamToLogger(stderr_logger, tglevellog)
            sys.stderr = sl
            logging.basicConfig(level = tglevellog,
                        format ='[%(name)s.%(funcName)s:%(lineno)d] %(message)s',
                        filename = tglogfile,
                        filemode = 'a')
    else:
        stdout_logger = logging.getLogger('STDOUT')
        sl = StreamToLogger(stdout_logger, tglevellog)
        sys.stdout = sl
        stderr_logger = logging.getLogger('STDERR')
        sl = StreamToLogger(stderr_logger, tglevellog)
        sys.stderr = sl
        logging.basicConfig(level = tglevellog,
                    format ='[%(name)s.%(funcName)s:%(lineno)d] %(message)s',
                    filename = tglogfile,
                    filemode = 'a')
    if optstypemachine.lower() in ["machine"]:
        sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "pluginsmachine"))
    else:
        sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "pluginsrelay"))
    # Setup the command line arguments.
    tg = confParameter(optstypemachine)

    if optstypemachine.lower() in ["machine"]:
        tg.pathplugins = os.path.join(os.path.dirname(os.path.realpath(__file__)), "pluginsmachine")
    else:
        tg.pathplugins = os.path.join(os.path.dirname(os.path.realpath(__file__)), "pluginsrelay")

    while True:
        restart = False
        xmpp = MUCBot(tg)
        xmpp.register_plugin('xep_0030') # Service Discovery
        xmpp.register_plugin('xep_0045') # Multi-User Chat
        xmpp.register_plugin('xep_0004') # Data Forms
        xmpp.register_plugin('xep_0050') # Adhoc Commands
        xmpp.register_plugin('xep_0199', {'keepalive': True, 'frequency':15})
        xmpp.register_plugin('xep_0077') # In-band Registration
        xmpp['xep_0077'].force_registration = True
        print "connect"
        # Connect to the XMPP server and start processing XMPP stanzas.address=(args.host, args.port)
        if xmpp.connect(address=(tg.Server,tg.Port)):
            xmpp.process(block=True)
            xmpp.queue_read_event_from_command.put("quit")
            logging.error("wait 2s end thread event loop")
            time.sleep(2)
            xmpp.scheduler.quit()
            logging.log(DEBUGPULSE,"bye bye Agent")
        else:
            logging.log(DEBUGPULSE,"Unable to connect.")
            restart = False
        if not restart: break

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
