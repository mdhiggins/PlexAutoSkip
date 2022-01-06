import requests

from log import getLogger
from ssl import CERT_NONE
from settings import Settings
from plexapi.server import PlexServer
from plexapi.myplex import MyPlexAccount
from introSkipper import IntroSkipper


if __name__ == '__main__':
    log = getLogger(__name__)
    settings = Settings(log=log)
    plex = None
    sslopt = None
    session = None

    if settings.ignore_certs:
        sslopt = {"cert_reqs": CERT_NONE}
        session = requests.Session()
        session.verify = False
        requests.packages.urllib3.disable_warnings()

    if settings.username and settings.password:
        try:
            account = MyPlexAccount(username=settings.usernmae, password=settings.password, token=settings.token, session=session)
            plex = account.resource(settings.servername).connect()
        except:
            log.exception("Error connecting to myPlex account")

    if not plex and settings.address and settings.port and settings.token:
        protocol = "https://" if settings.ssl else "http://"
        try:
            plex = PlexServer(protocol + settings.address + ':' + str(settings.port), settings.token, session=session)
        except:
            log.exception("Error connecting to Plex server")

    if plex:
        intro_skipper = IntroSkipper(plex, 2500, 2000, log=log)
        intro_skipper.start(sslopt=sslopt)
    else:
        log.error("Unable to establish Plex Server object via PlexAPI")
