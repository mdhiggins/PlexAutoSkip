import configparser
import os
import logging
import sys
import json
from resources.customEntries import CustomEntries
from resources.log import getLogger
from enum import Enum
from plexapi.server import PlexServer


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

    @property
    def CONFIG_RELATIVEPATH(self) -> str:
        return os.path.join(self.CONFIG_DIRECTORY, self.CONFIG_DEFAULT)

    DEFAULTS = {
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
        "Skip": {
            "mode": "skip",
            "tags": "intro, commercial, advertisement, credits",
            "types": "movie, episode",
            "ignored-libraries": "",
            "last-chapter": 0.0,
            "unwatched": True,
            "first-episode-series": "Watched",
            "first-episode-season": "Always",
            "next": False
        },
        "Offsets": {
            "start": 3000,
            "end": 1000,
            "command": 500,
            "tags": "intro"
        },
        "Volume": {
            "low": 0,
            "high": 100
        }
    }

    CUSTOM_DEFAULTS = {
        "markers": {},
        "offsets": {},
        "tags": {},
        "allowed": {
            'users': [],
            'clients': [],
            'keys': [],
            'skip-next': []
        },
        "blocked": {
            'users': [],
            'clients': [],
            'keys': [],
            'skip-next': []
        },
        "clients": {},
        "mode": {}
    }

    class MODE_TYPES(Enum):
        SKIP = 0
        VOLUME = 1

    MODE_MATCHER = {
        "skip": MODE_TYPES.SKIP,
        "volume": MODE_TYPES.VOLUME,
        "mute": MODE_TYPES.VOLUME
    }

    class SKIP_TYPES(Enum):
        NEVER = 0
        WATCHED = 1
        ALWAYS = 2

    SKIP_MATCHER = {
        "never": SKIP_TYPES.NEVER,
        "watched": SKIP_TYPES.WATCHED,
        "played": SKIP_TYPES.WATCHED,
        "always": SKIP_TYPES.ALWAYS,
        "all": SKIP_TYPES.ALWAYS,
        "true": SKIP_TYPES.ALWAYS,
        "false": SKIP_TYPES.NEVER,
        True: SKIP_TYPES.ALWAYS,
        False: SKIP_TYPES.NEVER
    }

    def __init__(self, configFile: str = None, loadCustom: bool = True, logger: logging.Logger = None) -> None:
        self.log: logging.Logger = logger or logging.getLogger(__name__)

        self.username: str = None
        self.password: str = None
        self.servername: str = None
        self.token: str = None
        self.address: str = None
        self.ssl: bool = False
        self.port: int = 32400
        self.ignore_certs: bool = False
        self.tags: list = []
        self.skiplastchapter: float = 0.0
        self.skipunwatched: bool = False
        self.skipE01: Settings.SKIP_TYPES = Settings.SKIP_TYPES.ALWAYS
        self.skipS01E01: Settings.SKIP_TYPES = Settings.SKIP_TYPES.ALWAYS
        self.skipnext: bool = False
        self.leftOffset: int = 0
        self.rightOffset: int = 0
        self.offsetTags: list = []
        self.commandDelay: int = 0
        self.customEntries: CustomEntries = None

        self._configFile: str = None

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

        config: FancyConfigParser = FancyConfigParser()
        if os.path.isfile(configFile):
            config.read(configFile)

        write = False
        # Make sure all sections and all keys for each section are present
        for s in self.DEFAULTS:
            if not config.has_section(s):
                config.add_section(s)
                write = True
            for k in self.DEFAULTS[s]:
                if not config.has_option(s, k):
                    config.set(s, k, str(self.DEFAULTS[s][k]))
                    write = True
        if write:
            Settings.writeConfig(config, configFile, self.log)
        self._configFile = configFile

        self.readConfig(config)

        if loadCustom:
            data = {}
            _, ext = os.path.splitext(self.CUSTOM_DEFAULT)
            for root, _, files in os.walk(os.path.dirname(configFile)):
                for filename in files:
                    fullpath = os.path.join(root, filename)
                    if os.path.isfile(fullpath) and os.path.splitext(filename)[1] == ext:
                        Settings.merge(data, Settings.loadCustom(fullpath, self.log))
                    else:
                        continue
            if not data:
                Settings.merge(data, Settings.loadCustom(os.path.join(os.path.dirname(configFile), self.CUSTOM_DEFAULT), self.log))

            self.customEntries = CustomEntries(data, self.log)

    @staticmethod
    def loadCustom(customFile: str, logger: logging.Logger = None) -> dict:
        log = logger or getLogger(__name__)
        data = dict(Settings.CUSTOM_DEFAULTS)
        if not os.path.exists(customFile):
            Settings.writeCustom(Settings.CUSTOM_DEFAULTS, customFile, log)
        elif os.path.exists(customFile):
            try:
                with open(customFile, encoding='utf-8') as f:
                    data = json.load(f)
            except:
                log.exception("Found custom file %s but failed to load, using defaults" % (customFile))

            write = False
            # Make sure default entries are present to prevent exceptions
            for k in Settings.CUSTOM_DEFAULTS:
                if k not in data:
                    data[k] = {}
                    write = True
                for sk in Settings.CUSTOM_DEFAULTS[k]:
                    if sk not in data[k]:
                        data[k][sk] = []
                        write = True
            if write:
                Settings.writeCustom(data, customFile, log)
        log.info("Loading custom JSON file %s" % customFile)
        return data

    @staticmethod
    def merge(d1: dict, d2: dict) -> None:
        for k in d2:
            if k in d1 and isinstance(d1[k], dict) and isinstance(d2[k], dict):
                Settings.merge(d1[k], d2[k])
            elif k in d1 and isinstance(d1[k], list) and isinstance(d2[k], list):
                d1[k].extend(d2[k])
            else:
                d1[k] = d2[k]

    @staticmethod
    def writeConfig(config: configparser.ConfigParser, cfgfile: str, logger: logging.Logger = None) -> None:
        log = logger or getLogger(__name__)
        if not os.path.isdir(os.path.dirname(cfgfile)):
            os.makedirs(os.path.dirname(cfgfile))
        try:
            fp = open(cfgfile, "w")
            config.write(fp)
            fp.close()
        except PermissionError:
            log.exception("Error writing to %s due to permissions" % (cfgfile))
        except IOError:
            log.exception("Error writing to %s" % (cfgfile))

    @staticmethod
    def writeCustom(data: dict, cfgfile: str, logger: logging.Logger = None) -> None:
        log = logger or getLogger(__name__)
        try:
            with open(cfgfile, 'w', encoding='utf-8') as cf:
                json.dump(data, cf, indent=4)
        except PermissionError:
            log.exception("Error writing to %s due to permissions" % (cfgfile))
        except IOError:
            log.exception("Error writing to %s" % (cfgfile))

    def readConfig(self, config: FancyConfigParser) -> None:
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

        self.mode = self.MODE_MATCHER.get(config.get("Skip", "mode").lower(), self.MODE_TYPES.SKIP)
        self.tags = config.getlist("Skip", "tags", replace=[])
        self.types = config.getlist("Skip", "types")
        self.ignoredlibraries = config.getlist("Skip", "ignored-libraries", replace=[])
        self.skipunwatched = config.getboolean("Skip", "unwatched")
        self.skiplastchapter = config.getfloat("Skip", "last-chapter")
        try:
            self.skipS01E01 = self.SKIP_MATCHER.get(config.getboolean("Skip", "first-episode-series"))  # Legacy bool support
        except ValueError:
            self.skipS01E01 = self.SKIP_MATCHER.get(config.get("Skip", "first-episode-series").lower(), self.SKIP_TYPES.ALWAYS)
        try:
            self.skipE01 = self.SKIP_MATCHER.get(config.getboolean("Skip", "first-episode-season"))  # Legacy bool support
        except ValueError:
            self.skipE01 = self.SKIP_MATCHER.get(config.get("Skip", "first-episode-season").lower(), self.SKIP_TYPES.ALWAYS)
        self.skipnext = config.getboolean("Skip", "next")

        self.leftOffset = config.getint("Offsets", "start")
        self.rightOffset = config.getint("Offsets", "end")
        self.commandDelay = config.getint("Offsets", "command")
        self.offsetTags = config.getlist("Offsets", "tags", replace=[])

        self.volumelow = config.getint("Volume", "low")
        self.volumehigh = config.getint("Volume", "high")

        for v in [self.volumelow, self.volumehigh]:
            if v < 0:
                v = 0
            if v > 100:
                v = 100

    @staticmethod
    def replaceWithGUIDs(data, server: PlexServer, ratingKeyLookup: dict, logger: logging.Logger = None) -> None:
        log = logger or getLogger(__name__)
        c = CustomEntries(data, logger=log)
        c.convertToGuids(server, ratingKeyLookup)

    @staticmethod
    def replaceWithRatingKeys(data, server: PlexServer, guidLookup: dict, logger: logging.Logger = None) -> None:
        log = logger or getLogger(__name__)
        c = CustomEntries(data, logger=log)
        c.convertToRatingKeys(server, guidLookup)
