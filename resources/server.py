from plexapi.server import PlexServer
from plexapi.myplex import MyPlexAccount
from resources.log import getLogger
from resources.settings import Settings
from typing import Tuple
from ssl import CERT_NONE
import requests
import logging


def getPlexServer(settings: Settings, logger: logging.Logger = None) -> Tuple[PlexServer, dict]:
    log = logger or getLogger(__name__)

    if not settings.username and not settings.address:
        log.error("No plex server settings specified, please update your configuration file")
        return None

    plex = None
    sslopt = None
    session = None

    if settings.ignore_certs:
        sslopt = {"cert_reqs": CERT_NONE}
        session = requests.Session()
        session.verify = False
        requests.packages.urllib3.disable_warnings()

    if settings.username and settings.servername:
        try:
            account = None
            if settings.token:
                try:
                    account = MyPlexAccount(username=settings.username, token=settings.token, session=session)
                except:
                    log.debug("Unable to connect using token, falling back to password")
                    account = None
            if settings.password and not account:
                try:
                    account = MyPlexAccount(username=settings.username, password=settings.password, session=session)
                except:
                    log.debug("Unable to connect using username/password")
                    account = None
            if account:
                plex = account.resource(settings.servername).connect()
            if plex:
                log.info("Connected to Plex server %s using plex.tv account" % (plex.friendlyName))
        except:
            log.exception("Error connecting to plex.tv account")

    if not plex and settings.address and settings.port and settings.token:
        protocol = "https://" if settings.ssl else "http://"
        try:
            plex = PlexServer(protocol + settings.address + ':' + str(settings.port), settings.token, session=session)
            log.info("Connected to Plex server %s using server settings" % (plex.friendlyName))
        except:
            log.exception("Error connecting to Plex server")
    elif plex and settings.address and settings.token:
        log.debug("Connected to server using plex.tv account, ignoring manual server settings")

    return plex, sslopt
