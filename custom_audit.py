import sys
import os
import json
from argparse import ArgumentParser
from resources.customEntries import CustomEntries
from resources.settings import Settings
from resources.log import getLogger
from plexapi.server import PlexServer
from plexapi.video import Show, Season, Episode, Movie
from resources.server import getPlexServer
from typing import TypeVar

ComplexMedia = TypeVar("ComplexMedia", Show, Season, Episode, Movie)

parser = ArgumentParser(description="Plex Autoskip Custom JSON auditer")
parser.add_argument('-c', '--config', help='Specify an alternate configuration file location')
parser.add_argument('-g', '--write_guids', action='store_true', help="Overwrite custom.json ratingKeys with GUIDs")
parser.add_argument('-rk', '--write_ratingkeys', action='store_true', help="Overwrite custom.json GUIDs with ratingKeys")
parser.add_argument('-p', '--path', help="Path to custom JSON file or directory. If unspecified default ./config folder will be used")
parser.add_argument('-o', '--offset', type=int, help="Specify an offset by which to adjust for both start and end")
parser.add_argument('-so', '--startoffset', type=int, help="Specify an offset by which to adjust for start")
parser.add_argument('-eo', '--endoffset', type=int, help="Specify an offset by which to adjust for end")
parser.add_argument('-d', '--duration', type=int, help="Validate marker duration in milliseconds")
parser.add_argument('-dg', '--dump_guids', type=str, help="Dump existing markers using GUIDs. Specify source as ratingKey or GUID")
parser.add_argument('-drk', '--dump_ratingkeys', type=str, help="Dump existing markers using ratingKeys. Specify source as ratingKey or GUID")
args = vars(parser.parse_args())

path = args["path"] or os.path.join(os.path.dirname(sys.argv[0]), Settings.CONFIG_DIRECTORY)

log = getLogger(__name__)

NEEDS_SERVER = ['write_guids', 'write_ratingkeys', 'dump_guids', 'dump_ratingkeys']


def processData(data, server: PlexServer = None, ratingKeyLookup: dict = None, guidLookup: dict = None) -> dict:
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
    analyzeMarkers(markers)
    return data


def processFile(path, server: PlexServer = None, ratingKeyLookup: dict = None, guidLookup: dict = None) -> None:
    _, ext = os.path.splitext(Settings.CUSTOM_DEFAULT)
    if os.path.splitext(path)[1] == ext:
        data = {}
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        log.info("Reading file %s" % (path))
        data = processData(data, server, ratingKeyLookup, guidLookup)
        Settings.writeCustom(data, path, log)


def analyzeMarkers(markers: dict) -> None:
    total = len(markers)
    populated = len([x for x in markers.values() if x])
    log.info("%d total entries, %d populated, %d empty (%.0f%%)" % (total, populated, total - populated, (populated / total) * 100))


def dumpMarkers(media: ComplexMedia, settings: Settings, useGuid: bool = False) -> dict:
    content = []
    if isinstance(media, Show) or isinstance(media, Season):
        content.extend(media.episodes())
    else:
        content.append(media)
    data = dict(Settings.CUSTOM_DEFAULTS)
    for c in content:
        key = CustomEntries.keyToGuid(c) if useGuid else c.ratingKey
        data['markers'][key] = []
        if hasattr(c, 'markers'):
            for m in c.markers:
                if m.type and m.type.lower() in settings.tags:
                    data['markers'][key].append({
                        'start': m.start,
                        'end': m.end
                    })
        if hasattr(c, 'chapters'):
            for m in c.chapters:
                if m.title and m.title.lower() in settings.tags:
                    data['markers'][key].append({
                        'start': m.start,
                        'end': m.end
                    })
    return data


def dumpMarkersFromRatingKey(ratingKey: str, ratingKeyLookup: dict, settings: Settings, useGuid: bool) -> dict:
    return dumpMarkers(ratingKeyLookup[ratingKey], settings, useGuid)


def dumpMarkersFromGuid(guid: str, guidLookup: dict, settings: Settings, useGuid: bool) -> dict:
    return dumpMarkers(guidLookup[guid], settings, useGuid)


if __name__ == '__main__':
    settings = None
    server = None
    ratingKeyLookup = None
    guidLookup = None

    if any(args[x] for x in NEEDS_SERVER):
        if args['config'] and os.path.exists(args['config']):
            settings = Settings(args['config'], loadCustom=False, logger=log)
        elif args['config'] and os.path.exists(os.path.join(os.path.dirname(sys.argv[0]), args['config'])):
            settings = Settings(os.path.join(os.path.dirname(sys.argv[0]), args['config']), loadCustom=False, logger=log)
        else:
            settings = Settings(loadCustom=False, logger=log)
        server, _ = getPlexServer(settings, log)

        identifier = args['dump_guids'] or args['dump_ratingkeys']
        if identifier:
            useGuid = args['dump_guids'] is not None
            output = None
            if CustomEntries.keyIsGuid(identifier):
                guidLookup = CustomEntries.loadGuids(server, log)
                output = dumpMarkersFromGuid(identifier, guidLookup, settings, useGuid)
            else:
                ratingKeyLookup = CustomEntries.loadRatingKeys(server, log)
                output = dumpMarkersFromRatingKey(identifier, ratingKeyLookup, settings, useGuid)
            if output:
                _, ext = os.path.splitext(Settings.CUSTOM_DEFAULT)
                if os.path.splitext(path)[1] == ext:
                    Settings.writeCustom(output, path, log)
                    processFile(path, server, ratingKeyLookup, guidLookup)
                else:
                    log.info(json.dumps(output, indent=4))
                    processData(output, server, ratingKeyLookup, guidLookup)
            sys.exit(0)

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
