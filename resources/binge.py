import logging
from datetime import datetime
from resources.mediaWrapper import MediaWrapper, STOPPEDKEY, PAUSEDKEY
from resources.log import getLogger
from resources.settings import Settings
from typing import Dict, List


class BingeSession():
    EPISODETYPE = "episode"

    class BingeSessionException(Exception):
        pass

    def __init__(self, mediaWrapper: MediaWrapper, blockcount: int, safetags: List[str]) -> None:
        if mediaWrapper.media.type != self.EPISODETYPE:
            raise self.BingeSessionException

        self.current: MediaWrapper = mediaWrapper
        self.count: int = 1
        self.blockcount: int = blockcount
        self.safetags: List[str] = safetags
        self.lastUpdate: datetime = datetime.now()

        self.__updateMediaWrapper__()

    @property
    def identifier(self) -> str:
        return self.current.clientIdentifier

    @property
    def sinceLastUpdate(self) -> int:
        return (datetime.now() - self.lastUpdate).total_seconds()

    def __updateMediaWrapper__(self) -> None:
        if self.block:
            self.current.tags = [t for t in self.current.tags if t in self.safetags]
            self.current.customMarkers = [c for c in self.current.customMarkers if c.type in self.safetags]
            self.current.updateMarkers()

    def update(self, mediaWrapper: MediaWrapper) -> None:
        if self.current.clientIdentifier == mediaWrapper.clientIdentifier and self.current.plexsession.user == mediaWrapper.plexsession.user:
            if mediaWrapper.media != self.current.media:
                self.current = mediaWrapper
                self.count += 1
                self.__updateMediaWrapper__()
            self.lastUpdate = datetime.now()

    @property
    def block(self) -> bool:
        return self.count <= self.blockcount

    @property
    def remaining(self) -> int:
        r = self.blockcount - self.count
        return r if r > 0 else 0

    def __repr__(self) -> str:
        return "%s-%s" % (self.current.clientIdentifier, self.current.playQueueID)


class BingeSessions():
    TIMEOUT = 30

    def __init__(self, settings: Settings, logger: logging.Logger = None) -> None:
        self.log = logger or getLogger(__name__)
        self.settings: Settings = settings
        self.sessions: Dict[BingeSession] = {}

    def update(self, mediaWrapper: MediaWrapper) -> None:
        if not self.settings.binge:
            return

        if mediaWrapper.state in [STOPPEDKEY, PAUSEDKEY]:
            return

        if mediaWrapper.clientIdentifier in self.sessions:
            self.sessions[mediaWrapper.clientIdentifier].update(mediaWrapper)
            self.log.debug("Updating binge starter (%s) with %s, remaining %d" % ("active" if self.sessions[mediaWrapper.clientIdentifier].block else "inactive", mediaWrapper, self.sessions[mediaWrapper.clientIdentifier].remaining))
        else:
            try:
                self.sessions[mediaWrapper.clientIdentifier] = BingeSession(mediaWrapper, self.settings.binge, self.settings.bingesafetags)
                self.log.debug("Creating binge starter (%s) for %s, remaining %d" % ("active" if self.sessions[mediaWrapper.clientIdentifier].block else "inactive", mediaWrapper, self.sessions[mediaWrapper.clientIdentifier].remaining))
            except BingeSession.BingeSessionException:
                pass

    def ping(self, clientIdentifier: str, playQueueID: int, state: str) -> None:
        if not self.settings.binge:
            return

        if state in [STOPPEDKEY, PAUSEDKEY]:
            return

        if clientIdentifier in self.sessions:
            session: BingeSession = self.sessions[clientIdentifier]
            if session.current.playQueueID == playQueueID:
                session.update(session.current)

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
                del self.sessions[session.identifier]
