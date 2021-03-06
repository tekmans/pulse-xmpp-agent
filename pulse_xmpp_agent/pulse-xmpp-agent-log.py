#!/usr/bin/env python
# -*- coding: utf-8 -*-
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
# AGENT log
# pulse_xmpp_agent/pulse-xmpp-agent-log.py
# MA 02110-1301, USA.
import sys, os
import logging
import ConfigParser
import sleekxmpp
import netifaces
import random
from sleekxmpp.exceptions import IqError, IqTimeout
import json
import hashlib
import datetime
from sqlalchemy import create_engine
from sqlalchemy import Column, String, Integer, DateTime, Text
from optparse import OptionParser
from lib.utils import StreamToLogger
#from sqlalchemy.dialects.mysql import  TINYINT
import copy
#from mmc.database.database_helper import DBObj
#from sqlalchemy.orm import relationship
#import datetime
import traceback
from sqlalchemy.orm import sessionmaker

from sqlalchemy.ext.declarative import declarative_base
from lib.logcolor import  add_coloring_to_emit_ansi


Base = declarative_base()

VERSIONLOG = 1.0

#jfkjfk
class Logs(Base):
    # ====== Table name =========================
    __tablename__ = 'logs'
    # ====== Fields =============================
    # Here we define columns for the table machines.
    # Notice that each column is also a normal Python instance attribute.
    id = Column(Integer, primary_key=True)
    type = Column(String(6), nullable=False,default = "noset")
    date = Column(DateTime, default=datetime.datetime.now())
    text = Column(Text, nullable=False)
    sessionname = Column(String(20), nullable=False, default = "")
    priority = Column(Integer, default = 0)
    who = Column(String(45), nullable=False, default = "")
    how = Column(String(255), nullable=False, default = "")
    why = Column(String(255), nullable=False, default = "")
    module = Column(String(45), nullable=False, default = "")
    action = Column(String(45), nullable=False, default = "")
    touser = Column(String(45), nullable=False, default = "")
    fromuser = Column(String(45), nullable=False, default = "")


class Deploy(Base):
    # ====== Table name =========================
    __tablename__ = 'deploy'
    # ====== Fields =============================
    # Here we define columns for the table deploy.
    # Notice that each column is also a normal Python instance attribute.
    id = Column(Integer, primary_key=True)
    title=Column(String(255))
    inventoryuuid = Column(String(11), nullable=False)
    group_uuid = Column(String(11))
    pathpackage = Column(String(100), nullable=False)
    jid_relay = Column(String(45), nullable=False)
    jidmachine = Column(String(45), nullable=False)
    state = Column(String(45), nullable=False)
    sessionid = Column(String(45), nullable=False)
    start = Column(DateTime, default=datetime.datetime.now())
    startcmd = Column(DateTime, default=None)
    endcmd = Column(DateTime, default=None)
    result = Column(Text )
    host = Column(String(45), nullable=False)
    user = Column(String(45), nullable=False, default = "")
    login = Column(String(45), nullable=False)
    command = Column(Integer)
    macadress=Column(String(255))

class configuration:
    def __init__(self):
        Config = ConfigParser.ConfigParser()
        Configlocal= ConfigParser.ConfigParser()
        Config.read("/etc/mmc/plugins/xmppmaster.ini")
        Configlocal.read("/etc/mmc/plugins/xmppmaster.ini.local")

        if  Configlocal.has_option("connection", "password"):
            self.Password=Configlocal.get('connection', 'password')
        else:
            self.Password=Config.get('connection', 'password')

        if  Configlocal.has_option("connection", "port"):
            self.Port=Configlocal.get('connection', 'port')
        else:
            self.Port=Config.get('connection', 'port')

        if  Configlocal.has_option("connection", "Server"):
            self.Server=Configlocal.get('connection', 'Server')
        else:
            self.Server=Config.get('connection', 'Server')

        if  Configlocal.has_option("chat", "domain"):
            self.Chatadress=Configlocal.get('chat', 'domain')
        else:
            self.Chatadress=Config.get('chat', 'domain')
        self.Jid="log@%s/log"% self.Chatadress
        self.master="master@%s/MASTER"%self.Chatadress
# database
        if  Configlocal.has_option("database", "dbport"):
            self.dbport=Configlocal.get('database', 'dbport')
        else:
            self.dbport=Config.get('database', 'dbport')

        if  Configlocal.has_option("database", "dbdriver"):
            self.dbdriver=Configlocal.get('database', 'dbdriver')
        else:
            self.dbdriver=Config.get('database', 'dbdriver')

        if  Configlocal.has_option("database", "dbhost"):
            self.dbhost=Configlocal.get('database', 'dbhost')
        else:
            self.dbhost=Config.get('database', 'dbhost')

        if  Configlocal.has_option("database", "dbname"):
            self.dbname=Configlocal.get('database', 'dbname')
        else:
            self.dbname=Config.get('database', 'dbname')

        if  Configlocal.has_option("database", "dbuser"):
            self.dbuser=Configlocal.get('database', 'dbuser')
        else:
            self.dbuser=Config.get('database', 'dbuser')

        if  Configlocal.has_option("database", "dbpasswd"):
            self.dbpasswd=Configlocal.get('database', 'dbpasswd')
        else:
            self.dbpasswd=Config.get('database', 'dbpasswd')


        if  Configlocal.has_option("global", "log_level"):
            self.log_level=Configlocal.get('global', 'log_level')
        else:
            self.log_level=Config.get('global', 'log_level')

#global
        if self.log_level == "INFO":
            self.debug = logging.INFO
        elif self.log_level == "DEBUG":
            self.debug = logging.DEBUG
        elif self.log_level == "ERROR":
            self.debug = logging.ERROR
        else:
            self.debug = 5


    def getRandomName(self, nb, pref=""):
        a="abcdefghijklnmopqrstuvwxyz"
        d=pref
        for t in range(nb):
            d=d+a[random.randint(0,25)]
        return d

    def getRandomNameID(self, nb, pref=""):
        a="0123456789"
        d=pref
        for t in range(nb):
            d=d+a[random.randint(0,9)]
        return d

    def get_local_ip_adresses(self):
        ip_addresses = list()
        interfaces = netifaces.interfaces()
        for i in interfaces:
            if i == 'lo':
                continue
            iface = netifaces.ifaddresses(i).get(netifaces.AF_INET)
            if iface:
                for j in iface:
                    addr = j['addr']
                    if addr != '127.0.0.1':
                        ip_addresses.append(addr)
        return ip_addresses

    #def __str__(self):
        #return str(self.re)

    def jsonobj(self):
        return json.dumps(self.re)

def getRandomName(nb, pref=""):
    a="abcdefghijklnmopqrstuvwxyz0123456789"
    d=pref
    for t in range(nb):
        d=d+a[random.randint(0,35)]
    return d


def md5(fname):
    hash = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash.update(chunk)
    return hash.hexdigest()


if sys.version_info < (3, 0):
    reload(sys)
    sys.setdefaultencoding('utf8')
else:
    raw_input = input
    


class MUCBot(sleekxmpp.ClientXMPP):
    def __init__(self,conf):#jid, password, room, nick):
        sleekxmpp.ClientXMPP.__init__(self, conf.Jid, conf.Password)
        self.engine = None
        self.config = conf
        self.dbpoolrecycle = 60
        self.dbpoolsize = 5
        self.add_event_handler("register", self.register, threaded=True)
        self.add_event_handler("session_start", self.start)
        self.add_event_handler('message', self.message)
        self.engine = create_engine('%s://%s:%s@%s/%s'%( self.config.dbdriver,
                                                                self.config.dbuser,
                                                                self.config.dbpasswd,
                                                                self.config.dbhost,
                                                                self.config.dbname),
                                    pool_recycle = self.dbpoolrecycle, 
                                    pool_size = self.dbpoolsize
        )
        self.Session = sessionmaker(bind=self.engine)


    def start(self, event):
        self.get_roster()
        self.send_presence()
        print self.boundjid

    def register(self, iq):
        """ This function is called for automatic registration """
        resp = self.Iq()
        resp['type'] = 'set'
        resp['register']['username'] = self.boundjid.user
        resp['register']['password'] = self.password

        try:
            resp.send(now=True)
            logging.info("Account created for %s!" % self.boundjid)
        except IqError as e:
            logging.error("Could not register account: %s" %
                    e.iq['error']['text'])
            #self.disconnect()
        except IqTimeout:
            logging.error("No response from server.")
            self.disconnect()


    def updatedeployresultandstate(self, sessionid, state, result ):
        #engine = create_engine('%s://%s:%s@%s/%s'%( self.config.dbdriver,
                                                                #self.config.dbuser,
                                                                #self.config.dbpasswd,
                                                                #self.config.dbhost,
                                                                #self.config.dbname))
        #Session = sessionmaker(bind=engine)
        session = self.Session()
        jsonresult = json.loads(result)
        jsonautre = copy.deepcopy(jsonresult)
        del (jsonautre['descriptor'])
        del (jsonautre['packagefile'])
        #DEPLOYMENT START
        try:
            dede = session.query(Deploy).filter(Deploy.sessionid == sessionid).one()
            if dede:
                if dede.result is None:
                    jsonbase = {
                                "infoslist": [jsonresult['descriptor']['info']],
                                "descriptorslist": [jsonresult['descriptor']['sequence']],
                                "otherinfos" : [jsonautre],
                                "title" : dede.title,
                                "session" : dede.sessionid,
                                "macadress" : dede.macadress,
                                "user" : dede.login
                    }
                else:
                    jsonbase = json.loads(dede.result)
                    jsonbase['infoslist'].append(jsonresult['descriptor']['info'])
                    jsonbase['descriptorslist'].append(jsonresult['descriptor']['sequence'])
                    jsonbase['otherinfos'].append(jsonautre)
                dede.result = json.dumps(jsonbase, indent=3)
                dede.state = state
            session.commit()
            session.flush()
            session.close()
            return 1
        except Exception, e:
            logging.getLogger().error(str(e))
            return -1

    def createlog(self, dataobj):
        """
            this function creating log in base from body message xmpp
        """
        try:
            if 'text' in dataobj :
                text = dataobj['text']
            else:
                return
            type = dataobj['type'] if 'type' in dataobj else ""
            sessionname = dataobj['session'] if 'session' in dataobj else ""
            priority = dataobj['priority'] if 'priority' in dataobj else ""
            who = dataobj['who'] if 'who' in dataobj else  ""
            how = dataobj['how'] if 'how' in dataobj else ""
            why = dataobj['why'] if 'why' in dataobj else ""
            module = dataobj['module'] if 'module' in dataobj else ""
            action = dataobj['action'] if 'action' in dataobj else ""
            fromuser = dataobj['fromuser'] if 'fromuser' in dataobj else ""
            touser = dataobj['touser'] if 'touser' in dataobj else ""
            self.registerlogxmpp(   text,
                                    type = type,
                                    sessionname = sessionname,
                                    priority = priority,
                                    who = who ,
                                    how  = how,
                                    why  = why,
                                    module = module,
                                    action = action,
                                    fromuser  = fromuser,
                                    touser  = touser)
        except Exception as e:
            logging.error("Message deploy error  %s %s" %(dataobj, str(e)))
            traceback.print_exc(file=sys.stdout)

    def registerlogxmpp(self,
                        text,
                        type = 'noset',
                        sessionname = '',
                        priority = 0,
                        who = '' ,
                        how  = '',
                        why  = '',
                        module = '',
                        fromuser  = '',
                        touser  = '',
                        action = ''
                        ):
        """
            this function for creating log in base
        """
        #mysql+mysqlconnector://<user>:<password>@<host>[:<port>]/<dbname>
        #engine = create_engine('%s://%s:%s@%s/%s'%( self.config.dbdriver,
                                                    #self.config.dbuser,
                                                    #self.config.dbpasswd,
                                                    #self.config.dbhost,
                                                    #self.config.dbname
                                                        #))
        #Session = sessionmaker(bind=engine)
        session = self.Session()
        log = Logs(text = text,
                   type = type,
                   sessionname = sessionname,
                   priority = priority,
                   who = who,
                   how = how,
                   why = why,
                   module = module,
                   action = action,
                   touser = touser,
                   fromuser = fromuser)
        session.add(log)
        session.commit()
        session.flush()
        session.close()

    def xmpplogdeploy(self, dataobj):
        """
            this function manage msg deploy log
        """
        try:
            if 'text' in dataobj and 'type' in dataobj and 'session' in dataobj and  'priority' in dataobj and  'who' in dataobj:
                self.registerlogxmpp(dataobj['text'],
                                     type = dataobj['type'],
                                     sessionname = dataobj['session'],
                                     priority = dataobj['priority'],
                                     who = dataobj['who'])
            elif 'action' in dataobj :
                if dataobj['action'] == 'resultapplicationdeploymentjson':
                    #log dans base resultat
                    if dataobj['ret'] == 0:
                        self.updatedeployresultandstate( dataobj['sessionid'], "DEPLOYMENT SUCCESS", json.dumps(dataobj['data'], indent=4, sort_keys=True) )
                    else:
                        self.updatedeployresultandstate( dataobj['sessionid'], "DEPLOYMENT ERROR", json.dumps(dataobj['data'], indent=4, sort_keys=True) )
        except Exception as e:
            logging.error("obj Message deploy error  %s %s" %(dataobj, str(e)))
            traceback.print_exc(file=sys.stdout)

    def message(self, msg):
        #save log message
        try :
            dataobj = json.loads(msg['body'])
        except Exception as e:
            logging.error("bad struct Message %s %s " %(msg, str(e)))
            traceback.print_exc(file=sys.stdout)

        if 'log' in dataobj:
            if dataobj['log'] == 'xmpplog':
                self.createlog(dataobj)
            else:
                # other typê message
                pass
        else:
            self.xmpplogdeploy(dataobj)

def createDaemon(opts,conf):
    """
        This function create a service/Daemon that will execute a det. task
    """
    try:
        pid = os.fork()
        if pid > 0:
            print 'PID: %d' % pid
            os._exit(0)
        doTask(opts,conf)
    except OSError, error:
        logging.error("Unable to fork. Error: %d (%s)" % (error.errno, error.strerror))
        traceback.print_exc(file=sys.stdout)
        os._exit(1)


def doTask(opts, conf):
    logging.StreamHandler.emit = add_coloring_to_emit_ansi(logging.StreamHandler.emit)
    #logging.basicConfig(level = logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


    if opts.consoledebug :
            logging.basicConfig(level = logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    else:
        stdout_logger = logging.getLogger('STDOUT')
        sl = StreamToLogger(stdout_logger, logging.INFO)
        sys.stdout = sl
        stderr_logger = logging.getLogger('STDERR')
        sl = StreamToLogger(stderr_logger, logging.INFO)
        sys.stderr = sl
        logging.basicConfig(level = logging.INFO,
                            format ='[%(name)s.%(funcName)s:%(lineno)d] %(message)s',
                            filename = "/var/log/pulse/xmpp-agent-log.log",
                            filemode = 'a')
    xmpp = MUCBot(conf)
    xmpp.register_plugin('xep_0030') # Service Discovery
    xmpp.register_plugin('xep_0045') # Multi-User Chat
    xmpp.register_plugin('xep_0199', {'keepalive': True, 'frequency':600, 'interval' : 600, 'timeout' : 500  })
    xmpp.register_plugin('xep_0077') # In-band Registration
    xmpp['xep_0077'].force_registration = True

    # Connect to the XMPP server and start processing XMPP stanzas.address=(args.host, args.port)
    if xmpp.connect(address=(conf.Server,conf.Port)):
        # If you do not have the dnspython library installed, you will need
        # to manually specify the name of the server if it does not match
        # the one in the JID. For example, to use Google Talk you would
        # need to use:
        #
        # if xmpp.connect(('talk.google.com', 5222)):
        xmpp.process(block=True)
        print("Done")
    else:
        print("Unable to connect.")

if __name__ == '__main__':
    if not sys.platform.startswith('linux'):
        print "Agent log on systeme linux only"


    if os.getuid() != 0:
        print "Agent must be running as root"
        sys.exit(0)

    optp = OptionParser()
    optp.add_option("-d",
                    "--deamon",
                    action = "store_true",
                    dest = "deamon",
                    default = False,
                    help = "deamonize process")

    optp.add_option("-c",
                    "--consoledebug",
                    action = "store_true",
                    dest = "consoledebug",
                    default = False,
                    help = "console debug")

    optp.add_option("-v",
                    "--version",
                    action = "store_true",
                    dest = "version",
                    default = False,
                    help = "version programme")

    opts, args = optp.parse_args()

    if opts.version == True:
        print VERSIONLOG
        sys.exit(0)
    # Setup the command line arguments.
    conf  = configuration()
    if not opts.deamon :
        doTask(opts, conf)
    else:
        createDaemon(opts, conf)
