import configparser
import os
import logging


class Settings:
    defaults = {
        "Plex": {
            "username": "",
            "password": "",
        },
        "Server": {
            "address": "",
            "token": "",
            "ssl": True,
            "port": 32400,
        },
        "Security": {
            "ignore-certs": False
        }
    }

    def __init__(self, log=None):
        self.log = log or logging.getLogger(__name__)
        configFile = os.environ.get("SKIP_CONFIG", "config.ini")
        configFile = os.path.realpath(configFile)
        config = configparser.ConfigParser()
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
        self.username = config.get("Plex", "username")
        self.password = config.get("Plex", "password")

        self.address = config.get("Server", "address")
        self.token = config.get("Server", "token")
        self.ssl = config.getboolean("Server", "ssl")
        self.port = config.getint("Server", "port")

        self.ignore_certs = config.getboolean("Security", "ignore-certs")
