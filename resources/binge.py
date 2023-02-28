import logging
from datetime import datetime
from resources.mediaWrapper import MediaWrapper, GRANDPARENTRATINGKEY
from resources.log import getLogger
from resources.settings import Settings
from plexapi.playqueue import PlayQueue
from typing import Dict, List


class BingeSession():
    EPISODETYPE = "episode"
    WATCHED_PERCENTAGE = 0.5  # Consider replacing with server watched percentage setting when available in PlexAPI future update

    class BingeSessionException(Exception):
        pass

    def __init__(self, mediaWrapper: MediaWrapper, blockCount: int, maxCount: int, safeTags: List[str], sameShowOnly: bool) -> None:
        if mediaWrapper.media.type != self.EPISODETYPE:
            raise self.BingeSessionException

        self.blockCount: int = blockCount

        try:
            pq: PlayQueue = PlayQueue.get(mediaWrapper.server, mediaWrapper.playQueueID)
            if pq.items[-1] == mediaWrapper.media:
                self.blockCount = 0
            if sameShowOnly and hasattr(mediaWrapper.media, GRANDPARENTRATINGKEY) and any([x for x in pq.items if hasattr(x, GRANDPARENTRATINGKEY) and x.grandparentRatingKey != mediaWrapper.media.grandparentRatingKey]):
                self.blockCount = 0
        except IndexError:
            self.blockCount = 0

        self.current: MediaWrapper = mediaWrapper
        self.count: int = 1
        self.maxCount: int = maxCount
        self._maxCount: int = maxCount
        self.safeTags: List[str] = safeTags
        self.lastUpdate: datetime = datetime.now()
        self.sameShowOnly: bool = sameShowOnly

        self.__updateMediaWrapper__()

    @property
    def clientIdentifier(self) -> str:
        return self.current.clientIdentifier

    @property
    def sinceLastUpdate(self) -> float:
        return (datetime.now() - self.lastUpdate).total_seconds()

    def __updateMediaWrapper__(self) -> None:
        if self.block:
            self.current.tags = [t for t in self.current.tags if t in self.safeTags]
            self.current.customMarkers = [c for c in self.current.customMarkers if c.type in self.safeTags]
            self.current.updateMarkers()

    def update(self, mediaWrapper: MediaWrapper) -> bool:
        if self.clientIdentifier == mediaWrapper.clientIdentifier and self.current.plexsession.user == mediaWrapper.plexsession.user:
            if self.sameShowOnly and hasattr(self.current.media, GRANDPARENTRATINGKEY) and hasattr(mediaWrapper.media, GRANDPARENTRATINGKEY) and self.current.media.grandparentRatingKey != mediaWrapper.media.grandparentRatingKey:
                return False
            if mediaWrapper.media != self.current.media or (mediaWrapper.media == self.current.media and self.current.ended and not mediaWrapper.ended):
                if self.current.media.duration and (self.current.viewOffset / self.current.media.duration) > self.WATCHED_PERCENTAGE:
                    if self.blockSkipNext:
                        self.maxCount += self._maxCount + 1
                    self.count += 1
                self.current = mediaWrapper
                self.__updateMediaWrapper__()
            self.lastUpdate = datetime.now()
            return True
        return False

    @property
    def block(self) -> bool:
        return self.count <= self.blockCount

    @property
    def blockSkipNext(self) -> bool:
        if not self.maxCount:
            return False
        return self.count > self.maxCount

    @property
    def remaining(self) -> int:
        r = self.blockCount - self.count
        return r if r > 0 else 0

    def __repr__(self) -> str:
        return "%s-%s" % (self.clientIdentifier, self.current.playQueueID)


class BingeSessions():
    TIMEOUT = 300
    IGNORED_CAP = 200

    def __init__(self, settings: Settings, logger: logging.Logger = None) -> None:
        self.log = logger or getLogger(__name__)
        self.settings: Settings = settings
        self.sessions: Dict[BingeSession] = {}
        self.ignored: List[str] = []

    def update(self, mediaWrapper: MediaWrapper) -> None:
        if mediaWrapper.ended:
            return

        if mediaWrapper.playQueueID in self.ignored:
            return

        if mediaWrapper.clientIdentifier in self.sessions:
            oldCount = self.sessions[mediaWrapper.clientIdentifier].count
            if self.sessions[mediaWrapper.clientIdentifier].update(mediaWrapper):
                if oldCount != self.sessions[mediaWrapper.clientIdentifier].count:
                    self.log.debug("Updating binge watcher (%s) with %s, remaining %d total %d" % ("active" if self.sessions[mediaWrapper.clientIdentifier].block else "inactive", mediaWrapper, self.sessions[mediaWrapper.clientIdentifier].remaining, self.sessions[mediaWrapper.clientIdentifier].count))
                return
            else:
                self.log.debug("Binge watcher %s is no longer relavant, player is playing alternative content, deleting" % (self.sessions[mediaWrapper.clientIdentifier]))
                del self.sessions[mediaWrapper.clientIdentifier]

        try:
            self.sessions[mediaWrapper.clientIdentifier] = BingeSession(mediaWrapper, self.settings.binge, self.settings.skipnextmax, self.settings.bingesafetags, self.settings.bingesameshowonly)
            self.log.debug("Creating binge watcher (%s) for %s, remaining %d total %d" % ("active" if self.sessions[mediaWrapper.clientIdentifier].block else "inactive", mediaWrapper, self.sessions[mediaWrapper.clientIdentifier].remaining, self.sessions[mediaWrapper.clientIdentifier].count))
        except BingeSession.BingeSessionException:
            self.ignored.append(mediaWrapper.playQueueID)
            self.ignored = self.ignored[-self.IGNORED_CAP:]

    def blockSkipNext(self, mediaWrapper: MediaWrapper) -> bool:
        if not self.settings.skipnextmax:
            return False

        session: BingeSession = self.sessions.get(mediaWrapper.clientIdentifier)
        if session:
            return session.blockSkipNext
        return False

    def clean(self) -> None:
        for session in list(self.sessions.values()):
            if session.sinceLastUpdate > self.TIMEOUT:
                self.log.debug("Binge watcher %s hasn't been updated in %d seconds, removing" % (session, self.TIMEOUT))
                del self.sessions[session.clientIdentifier]
