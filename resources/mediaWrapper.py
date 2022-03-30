import logging
from datetime import datetime
from plexapi.video import Episode, Movie
from plexapi.server import PlexServer
from plexapi.media import Marker, Chapter
from resources.customEntries import CustomEntries
from typing import TypeVar, List


Media = TypeVar("Media", Episode, Movie)

STARTKEY = "start"
ENDKEY = "end"


class CustomMarker():
    def __init__(self, data, key) -> None:
        self.start = data[STARTKEY]
        self.end = data[ENDKEY]
        self.key = key

    def __repr__(self) -> str:
        return "%d-%d" % (self.start, self.end)


class MediaWrapper():
    def __init__(self, media: Media, server: PlexServer, tags: List[str] = [], custom: CustomEntries = None, logger: logging.Logger = None) -> None:
        self._viewOffset: int = media.viewOffset
        self.media: Media = media

        self.lastUpdate: datetime = datetime.now()
        self.lastSeek: datetime = datetime(1970, 1, 1)

        self.seeking: bool = False
        self.seekBuffer: int = 5000

        self.markers: List[Marker] = []
        self.chapters: List[Chapter] = []
        self.lastchapter: Chapter = None

        self.customOnly: bool = False
        self.customMarkers: List[CustomMarker] = []

        self.leftOffset: int = 0
        self.rightOffset: int = 0

        self.log = logger or logging.getLogger(__name__)
        self.log.debug("Custom count %d" % len(self.customMarkers))
        self.customMarkers = []
        self.markers = []
        self.chapters = []

        for p in self.media.players:
            if custom and p.title in custom.clients:
                p._baseurl = custom.clients[p.title].strip('/')
                p._baseurl = p._baseurl if p._baseurl.startswith("http://") else "http://%s" % (p._baseurl)
                p.proxyThroughServer(False)
                self.log.debug("Overriding player %s with custom baseURL %s, will not proxy through server" % (p.title, p._baseurl))
            else:
                p.proxyThroughServer(True, server)

        if hasattr(self.media, 'markers') and not self.customOnly:
            self.markers = [x for x in self.media.markers if x.type and x.type.lower() in tags]

        if hasattr(self.media, 'chapters') and not self.customOnly:
            self.chapters = [x for x in self.media.chapters if x.title and x.title.lower() in tags]

        if hasattr(self.media, 'chapters') and not self.customOnly and len(self.media.chapters) > 0:
            self.lastchapter = self.media.chapters[-1]

        if len(self.media.players) > 0:
            self.playerName: str = self.media.players[0].title
        else:
            self.playerName: str = "Player"

        if custom:
            if hasattr(self.media, "grandparentRatingKey"):
                if str(self.media.grandparentRatingKey) in custom.markers:
                    for markerdata in custom.markers[str(self.media.grandparentRatingKey)]:
                        cm = CustomMarker(markerdata, self.media.grandparentRatingKey)
                        if cm not in self.customMarkers:
                            self.log.debug("Found custom marker range %s entry for %s (grandparentRatingKey match)" % (cm, self))
                            self.customMarkers.append(cm)
                if str(self.media.grandparentRatingKey) in custom.offsets:
                    self.leftOffset = custom.offsets[str(self.media.grandparentRatingKey)].get(STARTKEY, self.leftOffset)
                    self.rightOffset = custom.offsets[str(self.media.grandparentRatingKey)].get(ENDKEY, self.rightOffset)

            if hasattr(self.media, "parentRatingKey"):
                if str(self.media.parentRatingKey) in custom.markers:
                    if not custom.cascade and self.customMarkers:
                        self.log.debug("Cascading is disabled, better parentRatingKey markers found, clearing %d previous marker(s)" % (len(self.customMarkers)))
                        self.customMarkers = []
                    for markerdata in custom.markers[str(self.media.parentRatingKey)]:
                        cm = CustomMarker(markerdata, self.media.parentRatingKey)
                        if cm not in self.customMarkers:
                            self.log.debug("Found custom marker range %s entry for %s (parentRatingKey match)" % (cm, self))
                            self.customMarkers.append(cm)
                if str(self.media.parentRatingKey) in custom.offsets:
                    self.leftOffset = custom.offsets[str(self.media.parentRatingKey)].get(STARTKEY, self.leftOffset)
                    self.rightOffset = custom.offsets[str(self.media.parentRatingKey)].get(ENDKEY, self.rightOffset)

            if str(self.media.ratingKey) in custom.markers:
                if not custom.cascade and self.customMarkers:
                    self.log.debug("Cascading is disabled, better ratingKey markers found, clearing %d previous marker(s)" % (len(self.customMarkers)))
                    self.customMarkers = []
                for markerdata in custom.markers[str(self.media.ratingKey)]:
                    cm = CustomMarker(markerdata, self.media.ratingKey)
                    if cm not in self.customMarkers:
                        self.log.debug("Found custom marker range %s entry for %s" % (cm, self))
                        self.customMarkers.append(cm)
            if str(self.media.ratingKey) in custom.offsets:
                self.leftOffset = custom.offsets[str(self.media.ratingKey)].get(STARTKEY, self.leftOffset)
                self.rightOffset = custom.offsets[str(self.media.ratingKey)].get(ENDKEY, self.rightOffset)

            if self.leftOffset:
                self.log.debug("Custom start offset value of %d found for %s" % (self.leftOffset, self))
            if self.rightOffset:
                self.log.debug("Custom end offset value of %d found for %s" % (self.rightOffset, self))

    def __repr__(self) -> str:
        base = "%d [%d]" % (self.media.sessionKey, self.media.ratingKey)
        if hasattr(self.media, "title"):
            if hasattr(self.media, "grandparentTitle") and hasattr(self.media, "seasonEpisode"):
                return "%s (%s %s - %s) %s" % (base, self.media.grandparentTitle, self.media.seasonEpisode, self.media.title, self.playerName)
            return "%s (%s) %s" % (base, self.media.title, self.playerName)
        return "%s %s" % (base, self.playerName)

    @property
    def sinceLastUpdate(self) -> int:
        return (datetime.now() - self.lastUpdate).total_seconds()

    @property
    def viewOffset(self) -> int:
        return self._viewOffset + round((datetime.now() - self.lastUpdate).total_seconds() * 1000)

    def updateOffset(self, offset: int, seeking: bool) -> bool:
        if self.seeking and not seeking and (self.viewOffset - self.seekBuffer) > offset:
            self.log.debug("Skipping update session %s is actively seeking" % (self))
            return False
        if not seeking:
            self.log.debug("Updating session %s viewOffset %d, old %d, diff %d (%ds since last update)" % (self, offset, self.viewOffset, (offset - self.viewOffset), (datetime.now() - self.lastUpdate).total_seconds()))
        if self.seeking and not seeking and (self.viewOffset - self.seekBuffer) < offset:
            self.log.debug("Recent seek successful, server offset update %d greater than threshold %d, setting seeking to %s" % (offset, (self.viewOffset - self.seekBuffer), seeking))

        self._viewOffset = offset
        self.media.viewOffset = offset
        self.lastUpdate = datetime.now()
        self.seeking = seeking
        return True
