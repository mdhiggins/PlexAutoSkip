from datetime import datetime


class MediaWrapper():
    media = None
    lastUpdate = datetime.now()
    _viewOffset = 0
    seeking = False
    lastSeek = datetime(1970, 1, 1)
    seekBuffer = 5

    def __init__(self, media):
        self._viewOffset = media.viewOffset
        self.media = media
        self.lastUpdate = datetime.now()

    @property
    def buffering(self):
        return (datetime.now() - self.lastSeek).total_seconds() < self.seekBuffer

    @property
    def playerName(self):
        if len(self.media.players) > 0:
            return self.media.players[0].name
        return "Player"

    @property
    def sinceLastUpdate(self):
        return (datetime.now() - self.lastUpdate).total_seconds()

    @property
    def viewOffset(self):
        x = round((datetime.now() - self.lastUpdate).total_seconds() * 1000)
        return self._viewOffset + round((datetime.now() - self.lastUpdate).total_seconds() * 1000)

    def updated(self):
        self.lastUpdate = datetime.now()

    def willSeek(self):
        self.seeking = True
        self.lastSeek = datetime.now()

    def updateOffset(self, offset):
        self._viewOffset = offset
        self.media.viewOffset = offset
        self.lastUpdate = datetime.now()

    def updateMedia(self, media):
        self.media = media
        self.lastUpdate = datetime.now()
