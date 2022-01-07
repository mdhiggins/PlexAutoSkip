import requests
import sys
import os

from argparse import ArgumentParser
from resources.log import getLogger
from ssl import CERT_NONE
from resources.settings import Settings
from plexapi.server import PlexServer
from plexapi.myplex import MyPlexAccount
from resources.introSkipper import IntroSkipper


if __name__ == '__main__':
    log = getLogger(__name__)

    parser = ArgumentParser(description="Plex Autoskip")
    parser.add_argument('-c', '--config', help='Specify an alternate configuration file location')
    args = vars(parser.parse_args())

    if args['config'] and os.path.exists(args['config']):
        settings = Settings(args['config'], logger=log)
    elif args['config'] and os.path.exists(os.path.join(os.path.dirname(sys.argv[0]), args['config'])):
        settings = Settings(os.path.join(os.path.dirname(sys.argv[0]), args['config']), logger=log)
    else:
        settings = Settings(logger=log)

    plex = None
    sslopt = None
    session = None

    if not settings.username and not settings.address:
        log.error("No plex server settings specified, please update your configuration file")
        exit()

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

    if plex:
        intro_skipper = IntroSkipper(plex, settings.leftoffset, settings.rightoffset, logger=log)
        intro_skipper.allowed = settings.allowed
        intro_skipper.blocked = settings.blocked
        intro_skipper.start(sslopt=sslopt)
    else:
        log.error("Unable to establish Plex Server object via PlexAPI")
