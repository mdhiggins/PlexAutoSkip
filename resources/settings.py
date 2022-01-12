import configparser
import os
import logging
import sys

from resources.customEntries import CustomEntries


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
    CONFIG_DEFAULT = "config.ini"
    CUSTOM_DEFAULT = "custom.json"
    CONFIG_DIRECTORY = "./config"
    RESOURCE_DIRECTORY = "./resources"
    RELATIVE_TO_ROOT = "../"
    ENV_CONFIG_VAR = "PAS_CONFIG"
    customEntries = None

    @property
    def CONFIG_RELATIVEPATH(self):
        return os.path.join(self.CONFIG_DIRECTORY, self.CONFIG_DEFAULT)

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
        }
    }

    def __init__(self, configFile=None, logger=None,):
        self.log = logger or logging.getLogger(__name__)

        self.log.info(sys.executable)
        if sys.version_info.major == 2:
            self.log.warning("Python 2 is not officially supported, use with caution")

        rootpath = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), self.RELATIVE_TO_ROOT))

        defaultConfigFile = os.path.normpath(os.path.join(rootpath, self.CONFIG_RELATIVEPATH))
        envConfigFile = os.environ.get(self.ENV_CONFIG_VAR)

        if envConfigFile and os.path.exists(os.path.realpath(envConfigFile)):
            configFile = os.path.realpath(envConfigFile)
            self.log.debug("%s environment variable override found." % (self.ENV_CONFIG_VAR))
        elif not configFile:
            configFile = defaultConfigFile
            self.log.debug("Loading default config file.")

        if os.path.isdir(configFile):
            configFile = os.path.realpath(os.path.join(configFile, self.CONFIG_RELATIVEPATH))
            self.log.debug("Configuration file specified is a directory, joining with %s." % (self.CONFIG_DEFAULT))

        self.log.info("Loading config file %s." % configFile)

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

        customFile = os.path.join(os.path.dirname(configFile), self.CUSTOM_DEFAULT)
        if os.path.exists(customFile):
            try:
                self.customEntries = CustomEntries(customFile, self.log)
                self.log.debug("Custom file found, loading %s" % customFile)
            except:
                self.log.exception("Found custom file %s but failed to load" % (customFile))

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
        for prefix in ['http://', 'https://']:
            if self.address.startswith(prefix):
                self.address = self.address[len(prefix):]
        while self.address.endswith("/"):
            self.address = self.address[:1]
        self.ssl = config.getboolean("Server", "ssl")
        self.port = config.getint("Server", "port")

        self.ignore_certs = config.getboolean("Security", "ignore-certs")

        self.leftoffset = config.getint("Offsets", "start")
        self.rightoffset = config.getint("Offsets", "end")
