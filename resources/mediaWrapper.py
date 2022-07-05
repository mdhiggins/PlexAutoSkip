import logging
from datetime import datetime
from plexapi.video import Episode, Movie
from plexapi.server import PlexServer
from plexapi.media import Marker, Chapter
from resources.customEntries import CustomEntries
from resources.settings import Settings
from resources.log import getLogger
from typing import TypeVar, List


Media = TypeVar("Media", Episode, Movie)

STARTKEY = "start"
ENDKEY = "end"
PLAYINGKEY = "playing"
CASCADEKEY = "cascade"
MODEKEY = "mode"


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
        return "%d-%d" % (self.start, self.end)

    @property
    def length(self) -> int:
        return self.end - self.start


class MediaWrapper():
    def __init__(self, media: Media, state: str, server: PlexServer, tags: List[str] = [], mode: Settings.MODE_TYPES = Settings.MODE_TYPES.SKIP, custom: CustomEntries = None, logger: logging.Logger = None) -> None:
        self._viewOffset: int = media.viewOffset
        self.media: Media = media
        self.state: str = state

        self.lastUpdate: datetime = datetime.now()
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

        self.tags: List[str] = tags

        self.log = logger or getLogger(__name__)
        self.customMarkers = []
        self.markers = []
        self.chapters = []

        self.mode: Settings.MODE_TYPES = mode

        self.cachedVolume: int = 0
        self.loweringVolume: bool = False

        for p in self.media.players:
            if custom and p.title in custom.clients:
                p._baseurl = custom.clients[p.title].strip('/')
                p._baseurl = p._baseurl if p._baseurl.startswith("http://") else "http://%s" % (p._baseurl)
                p.proxyThroughServer(False)
                self.log.debug("Overriding player %s with custom baseURL %s, will not proxy through server" % (p.title, p._baseurl))
            else:
                p.proxyThroughServer(True, server)

        if len(self.media.players) > 0:
            self.playerName: str = self.media.players[0].title
        else:
            self.playerName: str = "Player"

        if custom:
            if hasattr(self.media, "grandparentRatingKey"):
                if str(self.media.grandparentRatingKey) in custom.markers:
                    for markerdata in custom.markers[str(self.media.grandparentRatingKey)]:
                        try:
                            cm = CustomMarker(markerdata, self.media.grandparentRatingKey, media.duration, mode)
                            if cm not in self.customMarkers:
                                self.log.debug("Found custom marker range %s entry for %s (grandparentRatingKey match)" % (cm, self))
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
                            cm = CustomMarker(markerdata, self.media.parentRatingKey, media.duration, mode)
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
                        cm = CustomMarker(markerdata, self.media.ratingKey, media.duration, mode)
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

            for player in self.media.players:
                if player.title and player.title in custom.mode:
                    self.mode = Settings.MODE_MATCHER.get(custom.mode[player.title], self.mode)

            self.tags = [x.lower() for x in self.tags]

            if self.leftOffset:
                self.log.debug("Custom start offset value of %d found for %s" % (self.leftOffset, self))
            if self.rightOffset:
                self.log.debug("Custom end offset value of %d found for %s" % (self.rightOffset, self))
            if self.tags != tags:
                self.log.debug("Custom tags value of %s found for %s" % (self.tags, self))
            if self.mode != mode:
                self.log.debug("Custom mode value of %s found for %s" % (self.mode, self))

        if hasattr(self.media, 'markers') and not self.customOnly:
            self.markers = [x for x in self.media.markers if x.type and x.type.lower() in self.tags]

        if hasattr(self.media, 'chapters') and not self.customOnly:
            self.chapters = [x for x in self.media.chapters if x.title and x.title.lower() in self.tags]

        if hasattr(self.media, 'chapters') and not self.customOnly and len(self.media.chapters) > 0:
            self.lastchapter = self.media.chapters[-1]

    def __repr__(self) -> str:
        base = "%d [%d]" % (self.media.sessionKey, self.media.ratingKey)
        if hasattr(self.media, "title"):
            if hasattr(self.media, "grandparentTitle") and hasattr(self.media, "seasonEpisode"):
                return "%s (%s %s - %s) %s" % (base, self.media.grandparentTitle, self.media.seasonEpisode, self.media.title, self.playerName)
            return "%s (%s) %s" % (base, self.media.title, self.playerName)
        return "%s %s" % (base, self.playerName)

    @property
    def seeking(self) -> bool:
        return self.seekTarget > 0

    @property
    def sinceLastUpdate(self) -> int:
        return (datetime.now() - self.lastUpdate).total_seconds()

    @property
    def viewOffset(self) -> int:
        if self.state != PLAYINGKEY:
            return self._viewOffset
        vo = self._viewOffset + round((datetime.now() - self.lastUpdate).total_seconds() * 1000)
        return vo if vo <= (self.media.duration or vo) else self.media.duration

    def updateOffset(self, offset: int, seeking: bool, state: str = None) -> bool:
        if self.seeking and not seeking and offset < self.seekTarget:
            if offset <= self.seekOrigin:
                self.log.debug("Seeking but new offset is earlier than the old one for session %s, resetting" % (self))
            else:
                self.log.debug("Skipping update session %s is actively seeking" % (self))
                return False
        if not seeking:
            self.log.debug("Updating session %s viewOffset %d, old %d, diff %d (%ds since last update)" % (self, offset, self.viewOffset, (offset - self.viewOffset), (datetime.now() - self.lastUpdate).total_seconds()))
        if self.seeking and not seeking and offset >= self.seekTarget:
            self.log.debug("Recent seek successful, server offset update %d meets/exceeds target %d, setting seeking to %s" % (offset, self.seekTarget, seeking))

        self.seekOrigin = self._viewOffset if seeking else 0
        self.seekTarget = offset if seeking else 0
        self._viewOffset = offset
        self.media.viewOffset = offset
        self.lastUpdate = datetime.now()
        self.state = state or self.state
        return True

    def updateVolume(self, volume: int, previousVolume: int, lowering: bool) -> bool:
        self.cachedVolume = previousVolume
        self.loweringVolume = lowering
        return volume != previousVolume
