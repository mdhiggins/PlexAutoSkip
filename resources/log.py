import logging
import os
import shutil
from logging.config import fileConfig
from logging.handlers import BaseRotatingHandler
from configparser import RawConfigParser


defaults = {
    'loggers': {
        'keys': 'root',
    },
    'handlers': {
        'keys': 'consoleHandler, fileHandler',
    },
    'formatters': {
        'keys': 'simpleFormatter, minimalFormatter',
    },
    'logger_root': {
        'level': 'DEBUG',
        'handlers': 'consoleHandler, fileHandler',
    },
    'handler_consoleHandler': {
        'class': 'StreamHandler',
        'level': 'INFO',
        'formatter': 'minimalFormatter',
        'args': '(sys.stdout,)',
    },
    'handler_fileHandler': {
        'class': 'handlers.RotatingFileHandler',
        'level': 'INFO',
        'formatter': 'simpleFormatter',
        'args': "('%(logfilename)s', 'a', 100000, 3, 'utf-8')",
    },
    'formatter_simpleFormatter': {
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'datefmt': '%Y-%m-%d %H:%M:%S',
    },
    'formatter_minimalFormatter': {
        'format': '%(levelname)s - %(message)s',
        'datefmt': ''
    }
}

CONFIG_DEFAULT = "logging.ini"
CONFIG_DIRECTORY = "./config"
RESOURCE_DIRECTORY = "./resources"
RELATIVE_TO_ROOT = "../"
LOG_NAME = "pas.log"


def checkLoggingConfig(configfile: str) -> None:
    write = True
    config = RawConfigParser()
    if os.path.exists(configfile):
        config.read(configfile)
        write = False
    for s in defaults:
        if not config.has_section(s):
            config.add_section(s)
            write = True
        for k in defaults[s]:
            if not config.has_option(s, k):
                config.set(s, k, str(defaults[s][k]))

    # Remove sysLogHandler if you're on Windows
    if 'sysLogHandler' in config.get('handlers', 'keys'):
        config.set('handlers', 'keys', config.get('handlers', 'keys').replace('sysLogHandler', ''))
        write = True
    while config.get('handlers', 'keys').endswith(",") or config.get('handlers', 'keys').endswith(" "):
        config.set('handlers', 'keys', config.get('handlers', 'keys')[:-1])
        write = True
    if write:
        fp = open(configfile, "w")
        config.write(fp)
        fp.close()


def getLogger(name: str = None, custompath: str = None) -> logging.Logger:
    if custompath:
        custompath = os.path.realpath(custompath)
        if not os.path.isdir(custompath):
            custompath = os.path.dirname(custompath)
        rootpath = os.path.abspath(custompath)
        resourcepath = os.path.normpath(os.path.join(rootpath, RESOURCE_DIRECTORY))
        configpath = os.path.normpath(os.path.join(rootpath, CONFIG_DIRECTORY))
    else:
        rootpath = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), RELATIVE_TO_ROOT))
        resourcepath = os.path.normpath(os.path.join(rootpath, RESOURCE_DIRECTORY))
        configpath = os.path.normpath(os.path.join(rootpath, CONFIG_DIRECTORY))

    logpath = configpath
    if not os.path.isdir(logpath):
        os.makedirs(logpath)

    if not os.path.isdir(configpath):
        os.makedirs(configpath)

    configfile = os.path.abspath(os.path.join(configpath, CONFIG_DEFAULT)).replace("\\", "\\\\")
    checkLoggingConfig(configfile)

    logfile = os.path.abspath(os.path.join(logpath, LOG_NAME)).replace("\\", "\\\\")
    fileConfig(configfile, defaults={'logfilename': logfile})

    logger = logging.getLogger(name)
    rotatingFileHandlers = [x for x in logger.handlers if isinstance(x, BaseRotatingHandler)]
    for rh in rotatingFileHandlers:
        rh.rotator = rotator

    return logging.getLogger(name)


def rotator(source: str, dest: str) -> None:
    if os.path.exists(source):
        try:
            os.rename(source, dest)
        except:
            try:
                shutil.copyfile(source, dest)
                open(source, 'w').close()
            except Exception as e:
                print("Error rotating logfiles: %s." % (e))
