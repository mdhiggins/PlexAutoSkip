import configparser
import os
import logging


class FancyConfigParser(configparser.ConfigParser, object):
    def getlist(self, section, option, vars=None, separator=",", default=[], lower=True, replace=[' '], modifier=None):
        value = self.get(section, option, vars=vars)

        if not isinstance(value, str) and isinstance(value, list):
            return value

        if value == '':
            return list(default)

        value = value.split(separator)

        for r in replace:
            value = [x.replace(r, '') for x in value]
        if lower:
            value = [x.lower() for x in value]

        value = [x.strip() for x in value]

        if modifier:
            value = [modifier(x) for x in value]
        return value


class Settings:
    defaults = {
        "Plex.tv": {
            "username": "",
            "password": "",
            "token": "",
            "servername": "",
        },
        "Server": {
            "address": "",
            "ssl": True,
            "port": 32400,
        },
        "Security": {
            "ignore-certs": False
        },
        "Offsets": {
            "start": 2000,
            "end": 1000
        },
        "Allowed": {
            "keys": '',
            "seasons": '',
            "shows": ''
        },
        "Blocked": {
            "keys": '',
            "seasons": '',
            "shows": ''
        }
    }

    def __init__(self, log=None):
        self.log = log or logging.getLogger(__name__)
        configFile = os.environ.get("SKIP_CONFIG", "config.ini")
        configFile = os.path.realpath(configFile)
        config = FancyConfigParser()
        if os.path.isfile(configFile):
            config.read(configFile)

        write = False
        # Make sure all sections and all keys for each section are present
        for s in self.defaults:
            if not config.has_section(s):
                config.add_section(s)
                write = True
            for k in self.defaults[s]:
                if not config.has_option(s, k):
                    config.set(s, k, str(self.defaults[s][k]))
                    write = True
        if write:
            self.writeConfig(config, configFile)

        self.readConfig(config)

    def writeConfig(self, config, cfgfile):
        if not os.path.isdir(os.path.dirname(cfgfile)):
            os.makedirs(os.path.dirname(cfgfile))
        try:
            fp = open(cfgfile, "w")
            config.write(fp)
            fp.close()
        except PermissionError:
            self.log.exception("Error writing to autoProcess.ini due to permissions.")
        except IOError:
            self.log.exception("Error writing to autoProcess.ini.")

    def readConfig(self, config):
        self.username = config.get("Plex.tv", "username")
        self.password = config.get("Plex.tv", "password", raw=True)
        self.servername = config.get("Plex.tv", "servername")
        self.token = config.get("Plex.tv", "token", raw=True)

        self.address = config.get("Server", "address")
        self.ssl = config.getboolean("Server", "ssl")
        self.port = config.getint("Server", "port")

        self.ignore_certs = config.getboolean("Security", "ignore-certs")

        self.leftoffset = config.getint("Offsets", "start")
        self.rightoffset = config.getint("Offsets", "end")

        self.allowed = {}
        self.allowed["keys"] = config.getlist("Allowed", "keys", modifier=int)
        self.allowed["parents"] = config.getlist("Allowed", "seasons", modifier=int)
        self.allowed["grandparents"] = config.getlist("Allowed", "shows", modifier=int)

        self.blocked = {}
        self.blocked["keys"] = config.getlist("Blocked", "keys", modifier=int)
        self.blocked["parents"] = config.getlist("Blocked", "seasons", modifier=int)
        self.blocked["grandparents"] = config.getlist("Blocked", "shows", modifier=int)
