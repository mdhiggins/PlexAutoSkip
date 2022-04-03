
import sys
import os
import json
from argparse import ArgumentParser
from resources.customEntries import CustomEntries
from resources.settings import Settings
from resources.log import getLogger
from plexapi.server import PlexServer
from resources.server import getPlexServer

parser = ArgumentParser(description="Plex Autoskip Custom JSON auditer")
parser.add_argument('-c', '--config', help='Specify an alternate configuration file location')
parser.add_argument('-g', '--write_guids', action='store_true', help="Overwrite custom.json ratingKeys with GUIDs")
parser.add_argument('-rk', '--write_ratingkeys', action='store_true', help="Overwrite custom.json GUIDs with ratingKeys")
parser.add_argument('-p', '--path', help="Path to custom JSON file or directory. If unspecified default ./config folder will be used")
parser.add_argument('-o', '--offset', type=int, help="Specify an offset by which to adjust for both start and end")
parser.add_argument('-so', '--startoffset', type=int, help="Specify an offset by which to adjust for start")
parser.add_argument('-eo', '--endoffset', type=int, help="Specify an offset by which to adjust for end")
parser.add_argument('-d', '--duration', type=int, help="Validate marker duration in milliseconds")
args = vars(parser.parse_args())

path = args["path"] or os.path.join(os.path.dirname(sys.argv[0]), Settings.CONFIG_DIRECTORY)

log = getLogger(__name__)


def processFile(path, server: PlexServer = None, ratingKeyLookup: dict = None, guidLookup: dict = None):
    _, ext = os.path.splitext(Settings.CUSTOM_DEFAULT)
    if os.path.splitext(path)[1] == ext:
        data = {}
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        log.info("Reading file %s" % (path))
        markers = data.get("markers")
        for k in markers:
            for m in markers[k]:
                diff = m['end'] - m['start']
                if args["offset"]:
                    log.info("Adjusting start offset by %d for %d" % (args["offset"], m['start']))
                    log.info("Adjusting end offset by %d for %d" % (args["offset"], m['end']))
                    m['start'] = m['start'] + args["offset"]
                    m['end'] = m['end'] + args["offset"]
                else:
                    if args["startoffset"]:
                        log.info("Adjusting start offset by %d for %d" % (args["startoffset"], m['start']))
                        m['start'] = m['start'] + args["startoffset"]
                    if args["endoffset"]:
                        log.info("Adjusting end offset by %d for %d" % (args["endoffset"], m['end']))
                        m['end'] = m['end'] + args["endoffset"]
                if diff < 0:
                    log.warning("%s entry is less than zero, likely invalid" % (k))
                if args["duration"] and diff != args["duration"]:
                    log.warning("%s does not equal specified duration of %d milliseconds (%d)" % (k, args["duration"], diff))
                if m['start'] < 0:
                    log.info("Start point %d is < 0, setting to 0" % (m['start']))
                    m['start'] = 0
                if m['end'] < 0:
                    log.info("End point %d is < 0, setting to 0" % (m['end']))
                    m['end'] = 0
        if args['write_guids']:
            Settings.replaceWithGUIDs(data, server, ratingKeyLookup, log)
        elif args['write_ratingkeys']:
            Settings.replaceWithRatingKeys(data, server, guidLookup, log)
        Settings.writeCustom(data, path, log)


if __name__ == '__main__':
    server = None
    ratingKeyLookup = None
    guidLookup = None

    if args['write_guids'] or args['write_ratingkeys']:
        if args['config'] and os.path.exists(args['config']):
            settings = Settings(args['config'], loadCustom=False, logger=log)
        elif args['config'] and os.path.exists(os.path.join(os.path.dirname(sys.argv[0]), args['config'])):
            settings = Settings(os.path.join(os.path.dirname(sys.argv[0]), args['config']), loadCustom=False, logger=log)
        else:
            settings = Settings(loadCustom=False, logger=log)
        server, _ = getPlexServer(settings, log)

        if args['write_guids']:
            ratingKeyLookup = CustomEntries.loadRatingKeys(server, log)
        elif args['write_ratingkeys']:
            guidLookup = CustomEntries.loadGuids(server, log)

    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for filename in files:
                fullpath = os.path.join(root, filename)
                processFile(fullpath, server, ratingKeyLookup, guidLookup)
    elif os.path.exists(path):
        processFile(path, server, ratingKeyLookup, guidLookup)
    else:
        log.error("Invalid path %s, does it exist?" % (path))
