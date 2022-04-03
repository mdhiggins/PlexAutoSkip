import sys
import os
from argparse import ArgumentParser
from resources.log import getLogger
from resources.settings import Settings
from resources.introSkipper import IntroSkipper
from resources.server import getPlexServer

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

    plex, sslopt = getPlexServer(settings, log)

    if plex:
        intro_skipper = IntroSkipper(plex, settings, log)
        intro_skipper.start(sslopt=sslopt)
    else:
        log.error("Unable to establish Plex Server object via PlexAPI")
