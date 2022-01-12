import json
import logging
from plexapi import media
from plexapi.media import Marker


class CustomEntries():
    data = {
        "markers": {},
        "allowed": {
            'keys': [],
            'parents': [],
            'grandparents': []
        },
        "blocked": {
            'keys': [],
            'parents': [],
            'grandparents': []
        }
    }

    @property
    def allowed(self):
        return self.data.get("allowed", {})

    @property
    def blocked(self):
        return self.data.get("blocked", {})

    def __init__(self, path, logger=None) -> None:
        self.log = logger or logging.getLogger(__name__)
        if path:
            with open(path) as f:
                self.data = json.load(f)

    def loadCustomMarkers(self, mediaWrapper) -> None:
        if str(mediaWrapper.media.ratingKey) in self.data.get("markers", {}):
            for markerdata in self.data['markers'][str(mediaWrapper.media.ratingKey)]:
                cm = CustomMarker(markerdata)
                if cm not in mediaWrapper.customMarkers:
                    self.log.debug("Found a custom marker range %s entry for %s" % (cm, mediaWrapper))
                    mediaWrapper.customMarkers.append(cm)


class CustomMarker():
    def __init__(self, data) -> None:
        self.start = data['start']  # * 1000
        self.end = data['end']  # * 1000

    def __repr__(self) -> str:
        return "%d-%d" % (self.start, self.end)
