from resources.server import getPlexServer
from resources.log import getLogger
from resources.settings import Settings
from argparse import ArgumentParser
import os
import sys
import requests

###########################################################################################################################
# Credit to https://gist.github.com/liamcottle/86180844b81fcf8085e2c9182daa278c for the original script
###########################################################################################################################

log = getLogger(__name__)

parser = ArgumentParser(description="Plex Autoskip Notification Sender")
parser.add_argument('-m', '--message', help='Message to send to users')
parser.add_argument('-c', '--config', help='Specify an alternate configuration file location')
parser.add_argument('-u', '--users', help="Users to send message to, leave back to send to all users")
parser.add_argument('-bu', '--blockedusers', help="Users to exlude sending the message to")
parser.add_argument('-ns', '--noself', action='store_true', help="Don't send notification to self")
args = vars(parser.parse_args())

if args['config'] and os.path.exists(args['config']):
    settings = Settings(args['config'], loadCustom=False, logger=log)
elif args['config'] and os.path.exists(os.path.join(os.path.dirname(sys.argv[0]), args['config'])):
    settings = Settings(os.path.join(os.path.dirname(sys.argv[0]), args['config']), loadCustom=False, logger=log)
else:
    settings = Settings(loadCustom=False, logger=log)

server, _ = getPlexServer(settings, log)
message = args['message']
if not message:
    log.warning("No message included, aborting")
    sys.exit(1)

users = args['users'] or []
blocked = args['blockedusers'] or []

myPlexAccount = server.myPlexAccount()

if not myPlexAccount:
    log.warning("No myPlex account found, aborting")
    sys.exit(1)

myPlexUsers = myPlexAccount.users()

if users:
    users = users.split(",")
    myPlexUsers = [u for u in myPlexUsers if u.username in users]
if blocked:
    blocked = blocked.split(",")
    myPlexUsers = [u for u in myPlexUsers if u.username not in blocked]

uids = [u.id for u in myPlexUsers]

if not args['noself']:
    uids.append(myPlexAccount.id)

if not uids:
    log.warning("No valid users to notify, aborting")
    sys.exit(1)

headers = {
    "X-Plex-Token": server._token,
}

data = {
    "group": 'media',
    "identifier": 'tv.plex.notification.library.new',
    "to": uids,
    "play": False,
    "data": {
        "provider": {
            "identifier": server.machineIdentifier,
            "title": server.friendlyName,
        }
    },
    "metadata": {
        "type": 'movie',
        "title": message,
    },
    "uri": "https://github.com/mdhiggins/PlexAutoSkip",
}

url = 'https://notifications.plex.tv/api/v1/notifications'

log.debug(data)

x = requests.post(url, json=data, headers=headers)
log.debug(x.text)
log.info("Response received with status code %s" % (x.status_code))

if x.status_code in [200, 201]:
    sys.exit(0)
else:
    sys.exit(1)
