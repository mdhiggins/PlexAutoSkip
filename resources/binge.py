import logging
from datetime import datetime
from resources.mediaWrapper import MediaWrapper, STOPPEDKEY
from resources.log import getLogger
from resources.settings import Settings
from typing import Dict, List


class BingeSession():
    EPISODETYPE = "episode"
    WATCHED_PERCENTAGE = 0.5  # Consider replacing with server watched percentage setting when available in PlexAPI future update

    class BingeSessionException(Exception):
        pass

    def __init__(self, mediaWrapper: MediaWrapper, blockCount: int, safeTags: List[str], sameShowOnly: bool) -> None:
        if mediaWrapper.media.type != self.EPISODETYPE:
            raise self.BingeSessionException

        self.current: MediaWrapper = mediaWrapper
        self.count: int = 1
        self.blockCount: int = blockCount
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
            if self.sameShowOnly and hasattr(self.current.media, "grandparentRatingKey") and hasattr(mediaWrapper.media, "grandparentRatingKey") and self.current.media.grandparentRatingKey != mediaWrapper.media.grandparentRatingKey:
                return False
            if mediaWrapper.media != self.current.media:
                self.current = mediaWrapper
                if self.current.media.duration and (self.current.viewOffset / self.current.media.duration) > self.WATCHED_PERCENTAGE:
                    self.count += 1
                self.__updateMediaWrapper__()
            self.lastUpdate = datetime.now()
            return True
        return False

    @property
    def block(self) -> bool:
        return self.count <= self.blockCount

    @property
    def remaining(self) -> int:
        r = self.blockCount - self.count
        return r if r > 0 else 0

    def __repr__(self) -> str:
        return "%s-%s" % (self.clientIdentifier, self.current.playQueueID)


class BingeSessions():
    TIMEOUT = 300

    def __init__(self, settings: Settings, logger: logging.Logger = None) -> None:
        self.log = logger or getLogger(__name__)
        self.settings: Settings = settings
        self.sessions: Dict[BingeSession] = {}

    def update(self, mediaWrapper: MediaWrapper) -> None:
        if not self.settings.binge:
            return

        if mediaWrapper.state in [STOPPEDKEY] or mediaWrapper.ended:
            return

        if mediaWrapper.clientIdentifier in self.sessions:
            if self.sessions[mediaWrapper.clientIdentifier].update(mediaWrapper):
                self.log.debug("Updating binge starter (%s) with %s, remaining %d" % ("active" if self.sessions[mediaWrapper.clientIdentifier].block else "inactive", mediaWrapper, self.sessions[mediaWrapper.clientIdentifier].remaining))
                return
            else:
                self.log.debug("Binge starter %s is no longer relavant, player is playing alternative content, deleting" % (self.sessions[mediaWrapper.clientIdentifier]))
                del self.sessions[mediaWrapper.clientIdentifier]

        try:
            self.sessions[mediaWrapper.clientIdentifier] = BingeSession(mediaWrapper, self.settings.binge, self.settings.bingesafetags, self.settings.bingesameshowonly)
            self.log.debug("Creating binge starter (%s) for %s, remaining %d" % ("active" if self.sessions[mediaWrapper.clientIdentifier].block else "inactive", mediaWrapper, self.sessions[mediaWrapper.clientIdentifier].remaining))
        except BingeSession.BingeSessionException:
            pass

    def shouldBlockSkipping(self, mediaWrapper: MediaWrapper) -> bool:
        if not self.settings.binge:
            return False

        if mediaWrapper.clientIdentifier in self.sessions:
            return self.sessions[mediaWrapper.clientIdentifier].block
        return False

    def clean(self) -> None:
        for session in list(self.sessions.values()):
            if session.sinceLastUpdate > self.TIMEOUT:
                self.log.debug("Binge starter %s hasn't been updated in %d seconds, removing" % (session, self.TIMEOUT))
                del self.sessions[session.clientIdentifier]
