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
    parser.add_argument('-g', '--write_guids', action='store_true', help="Overwrite custom.json ratingKeys with GUIDs")
    parser.add_argument('-rk', '--write_ratingkeys', action='store_true', help="Overwrite custom.json GUIDs with ratingKeys")
    args = vars(parser.parse_args())

    if args['config'] and os.path.exists(args['config']):
        settings = Settings(args['config'], logger=log)
    elif args['config'] and os.path.exists(os.path.join(os.path.dirname(sys.argv[0]), args['config'])):
        settings = Settings(os.path.join(os.path.dirname(sys.argv[0]), args['config']), logger=log)
    else:
        settings = Settings(logger=log)

    plex, sslopt = getPlexServer(settings, log)

    if plex:
        if args['write_guids']:
            log.debug("Overwriting ratingKeys with GUID values in custom.json")
            settings.replaceWithGUIDs(plex)
            log.debug("Custom.json update complete, exiting")
            sys.exit(0)

        if args['write_ratingkeys']:
            log.debug("Overwriting GUIDs with ratingKey values in custom.json")
            settings.replaceWithRatingKeys(plex)
            log.debug("Custom.json update complete, exiting")
            sys.exit(0)

        intro_skipper = IntroSkipper(plex, settings, log)
        intro_skipper.start(sslopt=sslopt)
    else:
        log.error("Unable to establish Plex Server object via PlexAPI")
