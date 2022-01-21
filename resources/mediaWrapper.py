import logging
from datetime import datetime
from plexapi.video import Episode, Movie
from plexapi.server import PlexServer
from plexapi.media import Marker, Chapter
from resources.customEntries import CustomEntries
from typing import TypeVar, List


Media = TypeVar("Media", Episode, Movie)


class CustomMarker():
    def __init__(self, data) -> None:
        self.start = data['start']  # * 1000
        self.end = data['end']  # * 1000

    def __repr__(self) -> str:
        return "%d-%d" % (self.start, self.end)


class MediaWrapper():
    media: Media = None

    lastUpdate: datetime = datetime.now()
    lastSeek: datetime = datetime(1970, 1, 1)

    _viewOffset: int = 0

    seeking: bool = False
    seekBuffer: int = 5

    customOnly: bool = False
    customMarkers: List[CustomMarker] = []

    MARKER_TAGS = ['intro', 'commercial']
    CHAPTER_TAGS = ['advertisement']

    def __init__(self, media: Media, server: PlexServer, custom: CustomEntries = None, logger: logging.Logger = None) -> None:
        self._viewOffset = media.viewOffset
        self.media = media
        self.lastUpdate = datetime.now()
        self.log = logger or logging.getLogger(__name__)

        for p in self.media.players:
            if custom and p.title in custom.clients:
                p._baseurl = custom.clients[p.title].strip('/')
                p._baseurl = p._baseurl if p._baseurl.startswith("http://") else "http://%s" % (p._baseurl)
                p.proxyThroughServer(False)
                self.log.debug("Overriding player %s using custom baseURL %s, will not proxy through server" % (p.title, p._baseurl))
            else:
                p.proxyThroughServer(True, server)

        if custom:
            if str(self.media.ratingKey) in custom.markers:
                for markerdata in custom.markers[str(self.media.ratingKey)]:
                    cm = CustomMarker(markerdata)
                    if cm not in self.customMarkers:
                        self.log.debug("Found a custom marker range %s entry for %s" % (cm, self))
                        self.customMarkers.append(cm)

            if hasattr(self.media, "parentRatingKey") and str(self.media.parentRatingKey) in custom.markers:
                for markerdata in custom.markers[str(self.media.parentRatingKey)]:
                    cm = CustomMarker(markerdata)
                    if cm not in self.customMarkers:
                        self.log.debug("Found a custom marker range %s entry for %s (parentRatingKey match)" % (cm, self))
                        self.customMarkers.append(cm)

            if hasattr(self.media, "grandparentRatingKey") and str(self.media.grandparentRatingKey) in custom.markers:
                for markerdata in custom.markers[str(self.media.grandparentRatingKey)]:
                    cm = CustomMarker(markerdata)
                    if cm not in self.customMarkers:
                        self.log.debug("Found a custom marker range %s entry for %s (grandparentRatingKey match)" % (cm, self))
                        self.customMarkers.append(cm)

    def __repr__(self) -> str:
        base = "%d [%d]" % (self.media.sessionKey, self.media.ratingKey)
        if hasattr(self.media, "title"):
            if hasattr(self.media, "grandparentTitle") and hasattr(self.media, "seasonEpisode"):
                return "%s (%s %s - %s) %s" % (base, self.media.grandparentTitle, self.media.seasonEpisode, self.media.title, self.playerName)
            return "%s (%s) %s" % (base, self.media.title, self.playerName)
        return "%s %s" % (base, self.playerName)

    @property
    def buffering(self) -> bool:
        return (datetime.now() - self.lastSeek).total_seconds() < self.seekBuffer

    @property
    def playerName(self) -> str:
        if len(self.media.players) > 0:
            return self.media.players[0].title
        return "Player"

    @property
    def sinceLastUpdate(self) -> int:
        return (datetime.now() - self.lastUpdate).total_seconds()

    @property
    def viewOffset(self) -> int:
        return self._viewOffset + round((datetime.now() - self.lastUpdate).total_seconds() * 1000)

    @property
    def markers(self) -> List[Marker]:
        if hasattr(self.media, 'markers') and not self.customOnly:
            return [x for x in self.media.markers if x.type and x.type.lower() in self.MARKER_TAGS]
        else:
            return []

    @property
    def chapters(self) -> List[Chapter]:
        if hasattr(self.media, 'chapters') and not self.customOnly:
            return [x for x in self.media.chapters if x.title and x.title.lower() in self.CHAPTER_TAGS]
        else:
            return []

    def updated(self) -> None:
        self.lastUpdate = datetime.now()

    def willSeek(self) -> None:
        self.seeking = True
        self.lastSeek = datetime.now()

    def updateOffset(self, offset: int) -> None:
        self._viewOffset = offset
        self.media.viewOffset = offset
        self.lastUpdate = datetime.now()
