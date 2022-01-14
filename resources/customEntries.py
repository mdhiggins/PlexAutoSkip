import json
import logging
from plexapi import media


class CustomEntries():
    defaults = {
        "markers": {},
        "allowed": {
            'users': [],
            'keys': [],
            'parents': [],
            'grandparents': []
        },
        "blocked": {
            'users': [],
            'keys': [],
            'parents': [],
            'grandparents': []
        }
    }

    @property
    def allowed(self):
        return self.data.get("allowed", {})

    @property
    def allowedUsers(self):
        return self.allowed.get("users", [])

    @property
    def allowedKeys(self):
        return self.allowed.get("keys", [])

    @property
    def allowedParentKeys(self):
        return self.allowed.get("parents", [])

    @property
    def allowedGrandparentKeys(self):
        return self.allowed.get("grandparents", [])

    @property
    def blocked(self):
        return self.data.get("blocked", {})

    @property
    def blockedUsers(self):
        return self.blocked.get("users", [])

    @property
    def blockedKeys(self):
        return self.blocked.get("keys", [])

    @property
    def blockedParentKeys(self):
        return self.blocked.get("parents", [])

    @property
    def blockedGrandparentKeys(self):
        return self.blocked.get("grandparents", [])

    def __init__(self, path, logger=None) -> None:
        self.data = self.defaults
        self.log = logger or logging.getLogger(__name__)
        if path:
            with open(path) as f:
                self.data = json.load(f)

        # Make sure default entries are present to prevent exceptions
        for k in self.defaults:
            if k not in self.data:
                self.data[k] = {}
            for sk in self.defaults[k]:
                if sk not in self.data[k]:
                    self.data[k][sk] = []

    def loadCustomMarkers(self, mediaWrapper) -> None:
        if str(mediaWrapper.media.ratingKey) in self.data.get("markers", {}):
            for markerdata in self.data['markers'][str(mediaWrapper.media.ratingKey)]:
                cm = CustomMarker(markerdata)
                if cm not in mediaWrapper.customMarkers:
                    self.log.debug("Found a custom marker range %s entry for %s" % (cm, mediaWrapper))
                    mediaWrapper.customMarkers.append(cm)

        if hasattr(mediaWrapper.media, "parentRatingKey") and str(mediaWrapper.media.parentRatingKey) in self.data.get("markers", {}):
            for markerdata in self.data['markers'][str(mediaWrapper.media.parentRatingKey)]:
                cm = CustomMarker(markerdata)
                if cm not in mediaWrapper.customMarkers:
                    self.log.debug("Found a custom marker range %s entry for %s (parentRatingKey match)" % (cm, mediaWrapper))
                    mediaWrapper.customMarkers.append(cm)

        if hasattr(mediaWrapper.media, "grandparentRatingKey") and str(mediaWrapper.media.grandparentRatingKey) in self.data.get("markers", {}):
            for markerdata in self.data['markers'][str(mediaWrapper.media.grandparentRatingKey)]:
                cm = CustomMarker(markerdata)
                if cm not in mediaWrapper.customMarkers:
                    self.log.debug("Found a custom marker range %s entry for %s (grandparentRatingKey match)" % (cm, mediaWrapper))
                    mediaWrapper.customMarkers.append(cm)


class CustomMarker():
    def __init__(self, data) -> None:
        self.start = data['start']  # * 1000
        self.end = data['end']  # * 1000

    def __repr__(self) -> str:
        return "%d-%d" % (self.start, self.end)
