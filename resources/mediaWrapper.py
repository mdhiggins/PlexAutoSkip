import logging
from datetime import datetime
from plexapi import utils
from plexapi.video import Episode, Movie
from plexapi.server import PlexServer
from plexapi.media import Marker, Chapter
from plexapi.client import PlexClient
from plexapi.base import PlexSession
from plexapi.myplex import MyPlexAccount
from plexapi.exceptions import NotFound
from resources.customEntries import CustomEntries
from resources.settings import Settings
from resources.log import getLogger
from typing import TypeVar, List
from math import floor


Media = TypeVar("Media", Episode, Movie)

STARTKEY = "start"
ENDKEY = "end"

PLAYINGKEY = "playing"
STOPPEDKEY = "stopped"
PAUSEDKEY = "paused"
CASCADEKEY = "cascade"
BUFFERINGKEY = "buffering"

MODEKEY = "mode"
MARKERPREFIX = "m"
CHAPTERPREFIX = "c"


# During paused/stopped states some PlexClients will report viewOffset rounded down to the nearest 1000, round accordingly
def rd(num: int, place: int = 1000) -> int:
    return int(floor(num / place) * place)


def strtobool(val):
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return True
    elif val in ('n', 'no', 'f', 'false', 'off', '0'):
        return False
    else:
        raise ValueError("Invalid truth value %r" % (val,))


class CustomMarker():
    class CustomMarkerException(Exception):
        pass

    class CustomMarkerDurationException(Exception):
        pass

    def __init__(self, data: dict, key: str, duration: int, parentMode: Settings.MODE_TYPES = Settings.MODE_TYPES.SKIP) -> None:
        if STARTKEY not in data or ENDKEY not in data:
            raise self.CustomMarkerException
        try:
            self._start = int(data[STARTKEY])
            self._end = int(data[ENDKEY])
            self.cascade = data.get(CASCADEKEY, False)
            if isinstance(self.cascade, str):
                self.cascade = bool(strtobool(self.cascade))
        except ValueError:
            raise self.CustomMarkerException
        self.mode = Settings.MODE_MATCHER.get(data.get(MODEKEY, "").lower(), parentMode)
        self.duration = duration
        self.key = key

        if not duration and (self._start < 0 or self._end < 0):
            raise self.CustomMarkerDurationException

    def safeRange(self, target) -> int:
        if target < 0:
            return 0
        if self.duration and target > self.duration:
            return self.duration
        return target

    @property
    def start(self) -> int:
        return self.safeRange(self.duration + self._start if self._start < 0 else self._start)

    @property
    def end(self) -> int:
        return self.safeRange(self._end if self._end > 0 else self.duration + self._end)

    def __repr__(self) -> str:
        return "<CustomMarker:%s-%s>" % (utils.millisecondToHumanstr(self.start), utils.millisecondToHumanstr(self.end))

    @property
    def length(self) -> int:
        return self.end - self.start


class MediaWrapper():
    def __init__(self, session: PlexSession, clientIdentifier: str, state: str, playQueueID: int, server: PlexServer, settings: Settings, custom: CustomEntries = None, logger: logging.Logger = None) -> None:
        self._viewOffset: int = session.viewOffset
        self.session: PlexSession = session
        self.media: Media = session.source()

        self.clientIdentifier = clientIdentifier
        self.state: str = state
        self.ended: bool = False
        self.playQueueID: dict = playQueueID
        self.player = session.player

        self.lastUpdate: datetime = datetime.now()
        self.lastAlert: datetime = datetime.now()
        self.lastSeek: datetime = datetime(1970, 1, 1)

        self.seekTarget: int = 0
        self.seekOrigin: int = 0

        self.markers: List[Marker] = []
        self.chapters: List[Chapter] = []
        self.lastchapter: Chapter = None

        self.customOnly: bool = False
        self.customMarkers: List[CustomMarker] = []

        self.leftOffset: int = 0
        self.rightOffset: int = 0
        self.commandDelay: int = 0

        self.tags: List[str] = settings.tags

        self.log = logger or getLogger(__name__)
        self.customMarkers = []
        self.markers = []
        self.chapters = []

        self.mode: Settings.MODE_TYPES = settings.mode

        self.skipnext: bool = settings.skipnext

        self.cachedVolume: int = 0
        self.loweringVolume: bool = False

        try:
            self.userToken: str = self.session.user._token if isinstance(self.session.user, MyPlexAccount) else self.session.user.get_token(server.machineIdentifier)
        except NotFound:
            self.userToken: str = None

        if custom and self.player.title in custom.clients:
            self.player._baseurl = custom.clients[self.player.title].strip('/')
            self.player._baseurl = self.player._baseurl if self.player._baseurl.startswith("http://") else "http://%s" % (self.player._baseurl)
            self.player.proxyThroughServer(False)
            self.log.debug("Overriding player %s with custom baseURL %s, will not proxy through server" % (self.player.title, self.player._baseurl))
        elif custom and self.clientIdentifier in custom.clients:
            self.player._baseurl = custom.clients[self.clientIdentifier].strip('/')
            self.player._baseurl = self.player._baseurl if self.player._baseurl.startswith("http://") else "http://%s" % (self.player._baseurl)
            self.player.proxyThroughServer(False)
            self.log.debug("Overriding player %s with custom baseURL %s, will not proxy through server" % (self.clientIdentifier, self.player._baseurl))
        else:
            self.player.proxyThroughServer(True, server)

        if custom:
            if hasattr(self.media, "grandparentRatingKey"):
                if str(self.media.grandparentRatingKey) in custom.markers:
                    for markerdata in custom.markers[str(self.media.grandparentRatingKey)]:
                        try:
                            cm = CustomMarker(markerdata, self.media.grandparentRatingKey, self.media.duration, settings.mode)
                            if cm not in self.customMarkers:
                                self.customMarkers.append(cm)
                        except CustomMarker.CustomMarkerException:
                            self.log.error("Invalid CustomMarker data for grandparentRatingKey %s" % (self.media.grandparentRatingKey))
                        except CustomMarker.CustomMarkerDurationException:
                            self.log.error("Invalid CustomMarker data for grandparentRatingKey %s, negative value start/end but API not reporting duration" % (self.media.grandparentRatingKey))
                if str(self.media.grandparentRatingKey) in custom.offsets:
                    self.leftOffset = custom.offsets[str(self.media.grandparentRatingKey)].get(STARTKEY, self.leftOffset)
                    self.rightOffset = custom.offsets[str(self.media.grandparentRatingKey)].get(ENDKEY, self.rightOffset)
                if str(self.media.grandparentRatingKey) in custom.tags:
                    self.tags = custom.tags[str(self.media.grandparentRatingKey)]
                if str(self.media.grandparentRatingKey) in custom.mode:
                    self.mode = Settings.MODE_MATCHER.get(custom.mode[str(self.media.grandparentRatingKey)], self.mode)

            if hasattr(self.media, "parentRatingKey"):
                if str(self.media.parentRatingKey) in custom.markers:
                    filtered = [x for x in self.customMarkers if x.cascade]
                    if self.customMarkers != filtered:
                        self.log.debug("Better parentRatingKey markers found, clearing %d previous marker(s)" % (len(self.customMarkers) - len(filtered)))
                        self.customMarkers = filtered
                    for markerdata in custom.markers[str(self.media.parentRatingKey)]:
                        try:
                            cm = CustomMarker(markerdata, self.media.parentRatingKey, self.media.duration, settings.mode)
                            if cm not in self.customMarkers:
                                self.log.debug("Found custom marker range %s entry for %s (parentRatingKey match)" % (cm, self))
                                self.customMarkers.append(cm)
                        except CustomMarker.CustomMarkerException:
                            self.log.error("Invalid CustomMarker data for parentRatingKey %s" % (self.media.parentRatingKey))
                        except CustomMarker.CustomMarkerDurationException:
                            self.log.error("Invalid CustomMarker data for parentRatingKey %s, negative value start/end but API not reporting duration" % (self.media.parentRatingKey))
                if str(self.media.parentRatingKey) in custom.offsets:
                    self.leftOffset = custom.offsets[str(self.media.parentRatingKey)].get(STARTKEY, self.leftOffset)
                    self.rightOffset = custom.offsets[str(self.media.parentRatingKey)].get(ENDKEY, self.rightOffset)
                if str(self.media.parentRatingKey) in custom.tags:
                    self.tags = custom.tags[str(self.media.parentRatingKey)]
                if str(self.media.parentRatingKey) in custom.mode:
                    self.mode = Settings.MODE_MATCHER.get(custom.mode[str(self.media.parentRatingKey)], self.mode)

            if str(self.media.ratingKey) in custom.markers:
                filtered = [x for x in self.customMarkers if x.cascade]
                if self.customMarkers != filtered:
                    self.log.debug("Better ratingKey markers found, clearing %d previous marker(s)" % (len(self.customMarkers) - len(filtered)))
                    self.customMarkers = filtered
                for markerdata in custom.markers[str(self.media.ratingKey)]:
                    try:
                        cm = CustomMarker(markerdata, self.media.ratingKey, self.media.duration, settings.mode)
                        if cm not in self.customMarkers:
                            self.log.debug("Found custom marker range %s entry for %s" % (cm, self))
                            self.customMarkers.append(cm)
                    except CustomMarker.CustomMarkerException:
                        self.log.error("Invalid CustomMarker data for ratingKey %s" % (self.media.ratingKey))
                    except CustomMarker.CustomMarkerDurationException:
                        self.log.error("Invalid CustomMarker data for ratingKey %s, negative value start/end but API not reporting duration" % (self.media.ratingKey))
            if str(self.media.ratingKey) in custom.offsets:
                self.leftOffset = custom.offsets[str(self.media.ratingKey)].get(STARTKEY, self.leftOffset)
                self.rightOffset = custom.offsets[str(self.media.ratingKey)].get(ENDKEY, self.rightOffset)
            if str(self.media.ratingKey) in custom.tags:
                self.tags = custom.tags[str(self.media.ratingKey)]
            if str(self.media.ratingKey) in custom.mode:
                self.mode = Settings.MODE_MATCHER.get(custom.mode[str(self.media.ratingKey)], self.mode)

            if self.player.title in custom.mode:
                self.mode = Settings.MODE_MATCHER.get(custom.mode[self.player.title], self.mode)
            elif self.clientIdentifier in custom.mode:
                self.mode = Settings.MODE_MATCHER.get(custom.mode[self.clientIdentifier], self.mode)

            if self.player.title in custom.offsets:
                self.commandDelay = custom.offsets[self.player.title].get("command", self.commandDelay)
            elif self.clientIdentifier in custom.offsets:
                self.commandDelay = custom.offsets[self.clientIdentifier].get("command", self.commandDelay)

            if not self.skipnext and custom.allowedSkipNext and (self.player.title in custom.allowedSkipNext or self.clientIdentifier in custom.allowedSkipNext):
                self.skipnext = True
            elif self.skipnext and custom.allowedSkipNext and (self.player.title not in custom.allowedSkipNext and self.clientIdentifier not in custom.allowedSkipNext):
                self.skipnext = False
            elif self.skipnext and custom.blockedSkipNext and (self.player.title in custom.blockedSkipNext or self.clientIdentifier in custom.blockedSkipNext):
                self.skipnext = False

            self.tags = [x.lower() for x in self.tags]

            if self.leftOffset:
                self.log.debug("Custom start offset value of %dms found for %s" % (self.leftOffset, self))
            if self.rightOffset:
                self.log.debug("Custom end offset value of %dms found for %s" % (self.rightOffset, self))
            if self.tags != settings.tags:
                self.log.debug("Custom tags value of %s found for %s" % (self.tags, self))
            if self.mode != settings.mode:
                self.log.debug("Custom mode value of %s found for %s" % (self.mode, self))
            if self.commandDelay:
                self.log.debug("Custom command delay value of %dms found for %s" % (self.commandDelay, self))
            if self.skipnext != settings.skipnext:
                self.log.debug("Custom skipNext value of %s found for %s" % (self.skipnext, self))

        if hasattr(self.media, 'markers') and not self.customOnly:
            self.markers = [x for x in self.media.markers if x.type and (x.type.lower() in self.tags or "%s:%s" % (MARKERPREFIX, x.type.lower()) in self.tags)]

        if hasattr(self.media, 'chapters') and not self.customOnly:
            self.chapters = [x for x in self.media.chapters if x.title and (x.title.lower() in self.tags or "%s:%s" % (CHAPTERPREFIX, x.title.lower()) in self.tags)]

        if hasattr(self.media, 'chapters') and not self.customOnly and len(self.media.chapters) > 0:
            self.lastchapter = self.media.chapters[-1]

    def __repr__(self) -> str:
        base = "%d [%d]" % (self.session.sessionKey, self.media.ratingKey)
        if hasattr(self.media, "title"):
            if hasattr(self.media, "grandparentTitle") and hasattr(self.media, "seasonEpisode"):
                return "%s (%s %s - %s) %s|%s" % (base, self.media.grandparentTitle, self.media.seasonEpisode, self.media.title, self.player.title, self.clientIdentifier)
            return "%s (%s) %s|%s" % (base, self.media.title, self.player.title, self.clientIdentifier)
        return "%s %s|%s" % (base, self.player.title, self.clientIdentifier)

    @property
    def hasContent(self) -> bool:
        return len(self.chapters + self.markers + self.customMarkers) > 0

    @staticmethod
    def getSessionClientIdentifier(sessionKey, clientIdentifier) -> str:
        return "%s-%s" % (sessionKey, clientIdentifier)

    @property
    def pasIdentifier(self) -> str:
        return MediaWrapper.getSessionClientIdentifier(self.session.sessionKey, self.clientIdentifier)

    @property
    def seeking(self) -> bool:
        return self.seekTarget > 0

    @property
    def sinceLastUpdate(self) -> int:
        return (datetime.now() - self.lastUpdate).total_seconds()

    @property
    def sinceLastAlert(self) -> int:
        return (datetime.now() - self.lastAlert).total_seconds()

    @property
    def viewOffset(self) -> int:
        if self.state != PLAYINGKEY:
            return self._viewOffset
        vo = self._viewOffset + round((datetime.now() - self.lastUpdate).total_seconds() * 1000)
        return vo if vo <= (self.media.duration or vo) else self.media.duration

    def seekTo(self, offset: int, player: PlexClient) -> None:
        self.session.viewOffset = self.viewOffset
        self.seekOrigin = rd(self._viewOffset)
        self.seekTarget = rd(offset)
        self.lastUpdate = datetime.now()
        self._viewOffset = offset
        player.seekTo(offset)
        self.session.viewOffset = offset

    def badSeek(self) -> None:
        self._viewOffset = self.session.viewOffset
        self.seekOrigin = 0
        self.seekTarget = 0
        self.lastUpdate = datetime.now()

    def updateOffset(self, offset: int, state: str) -> None:
        self.lastAlert = datetime.now()

        if self.seeking:
            if self.seekOrigin < offset < self.seekTarget:
                self.log.debug("Rejecting %d [%s] update session %s, alert is out of date" % (offset, state, self))
                return
            elif offset < self.seekOrigin:
                self.log.debug("Seeking but new offset is earlier than the old one for session %s [%s], updating data and assuming user manual seek" % (self, state))
            else:
                self.log.debug("Recent seek successful, server offset update %d meets/exceeds target %d [%s]" % (offset, self.seekTarget, state))

        self.log.debug("Updating session %s [%s] viewOffset %d, old %d, diff %dms (%ds since last update)" % (self, state, offset, self.viewOffset, (offset - self.viewOffset), (datetime.now() - self.lastUpdate).total_seconds()))

        self.state = state
        self.seekOrigin = 0
        self.seekTarget = 0
        self._viewOffset = offset
        self.session.viewOffset = offset
        self.lastUpdate = datetime.now()
        if not self.ended and state in [PAUSEDKEY, STOPPEDKEY] and offset >= rd(self.media.duration):
            self.ended = True

    def updateVolume(self, volume: int, previousVolume: int, lowering: bool) -> bool:
        self.cachedVolume = previousVolume
        self.loweringVolume = lowering
        return volume != previousVolume
