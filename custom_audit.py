
import sys
import os
import json
from argparse import ArgumentParser
from resources.settings import Settings
from resources.log import getLogger

parser = ArgumentParser(description="Plex Autoskip Custom JSON auditer")
parser.add_argument('-p', '--path', help="Path to custom JSON file(s)")
parser.add_argument('-o', '--offset', type=int, help="Specify an offset by which to adjust for both start and end")
parser.add_argument('-so', '--startoffset', type=int, help="Specify an offset by which to adjust for start")
parser.add_argument('-eo', '--endoffset', type=int, help="Specify an offset by which to adjust for end")
parser.add_argument('-d', '--duration', type=int, help="Validate marker duration in milliseconds")
args = vars(parser.parse_args())

path = args.get("path") or os.path.dirname(sys.argv[0])

log = getLogger(__name__)


def processFile(filename):
    if filename.endswith(os.path.splitext(Settings.CUSTOM_DEFAULT)[1]):
        data = {}
        with open(filename, encoding='utf-8') as f:
            data = json.load(f)
        log.info("Opening file %s" % (filename))
        markers = data.get("markers")
        for k in markers:
            for m in markers[k]:
                diff = m['end'] - m['start']
                if args.get("offset"):
                    log.info("Adjusting start offset by %d for %d" % (args.get("offset"), m['start']))
                    log.info("Adjusting end offset by %d for %d" % (args.get("offset"), m['end']))
                    m['start'] = m['start'] + args.get("offset")
                    m['end'] = m['end'] + args.get("offset")
                else:
                    if args.get("startoffset"):
                        log.info("Adjusting start offset by %d for %d" % (args.get("startoffset"), m['start']))
                        m['start'] = m['start'] + args.get("startoffset")
                    if args.get("endoffset"):
                        log.info("Adjusting end offset by %d for %d" % (args.get("endoffset"), m['end']))
                        m['end'] = m['end'] + args.get("endoffset")
                if diff < 0:
                    log.info("Entry is less than zero, likely invalid")
                    log.info("%s %s" % (filename, k))
                if args.get("duration") and diff != args.get("duration"):
                    log.info("Entry does not equal specified duration of %d milliseconds" % args.get("duration"))
                    log.info("%s %s" % (filename, k))
                if m['start'] < 0:
                    log.info("Start point %d is < 0, setting to 0" % (m['start']))
                    m['start'] = 0
                if m['end'] < 0:
                    log.info("End point %d is < 0, setting to 0" % (m['end']))
                    m['end'] = 0
        Settings.writeCustom(data, filename, log)
    else:
        log.debug("Ignoring invalid extension for path %s" % (filename))


if __name__ == '__main__':
    if os.path.isdir(path):
        for filename in os.listdir(os.path.abspath(path)):
            processFile(os.path.join(path, filename))
    elif os.path.exists(path):
        processFile(path)
    else:
        log.error("Invalid path %s, does it exist?" % (path))
