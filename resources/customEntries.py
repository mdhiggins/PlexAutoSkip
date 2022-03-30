import logging
from typing import Dict, List
from plexapi.server import PlexServer


class CustomEntries():
    PREFIXES = ["imdb://", "tmdb://", "tvdb://"]

    @property
    def markers(self) -> Dict[str, list]:
        return self.data.get("markers", {})

    @property
    def offsets(self) -> Dict[str, dict]:
        return self.data.get("offsets", {})

    @property
    def allowed(self) -> Dict[str, List[dict]]:
        return self.data.get("allowed", {})

    @property
    def allowedClients(self) -> List[str]:
        return self.allowed.get("clients", [])

    @property
    def allowedUsers(self) -> List[str]:
        return self.allowed.get("users", [])

    @property
    def allowedKeys(self) -> List[int]:
        return self.allowed.get("keys", [])

    @property
    def blocked(self) -> List[dict]:
        return self.data.get("blocked", {})

    @property
    def blockedClients(self) -> List[str]:
        return self.blocked.get("clients", [])

    @property
    def blockedUsers(self) -> List[str]:
        return self.blocked.get("users", [])

    @property
    def blockedKeys(self) -> List[int]:
        return self.blocked.get("keys", [])

    @property
    def clients(self) -> Dict[str, str]:
        return self.data.get("clients", {})

    @property
    def needsGuidResolution(self) -> bool:
        return any(str(key).startswith(p) for key in (list(self.markers.keys()) + list(self.offsets.keys()) + self.allowedKeys + self.blockedKeys) for p in self.PREFIXES)

    def loadGuids(self, plex: PlexServer) -> dict:
        self.log.debug("Generating GUID to ratingKey match table")
        guidLookup = {guid.id: item for item in plex.library.all() if hasattr(item, "guids") for guid in item.guids}
        self.log.debug("Finished generated match table with %d entries" % (len(guidLookup)))
        return guidLookup

    def convertToRatingKeys(self, server: PlexServer) -> None:
        guidLookup = self.loadGuids(server)
        for k in [x for x in list(self.markers.keys()) if self.keyIsGuid(x)]:
            ratingKey = self.resolveGuidToKey(k, guidLookup)
            if ratingKey != k:
                self.log.debug("Resolving custom markers GUID %s to ratingKey %s" % (k, ratingKey))
                self.markers[str(ratingKey)] = self.markers.pop(k)
            else:
                self.log.error("Unable to resolve GUID %s to ratingKey in custom markers" % (k))
        for k in [x for x in list(self.offsets.keys()) if self.keyIsGuid(x)]:
            ratingKey = self.resolveGuidToKey(k, guidLookup)
            if ratingKey != k:
                self.log.debug("Resolving custom offsets GUID %s to ratingKey %s" % (k, ratingKey))
                self.offsets[str(ratingKey)] = self.offsets.pop(k)
            else:
                self.log.error("Unable to resolve GUID %s to ratingKey in custom offsets" % (k))
        for k in [x for x in self.allowedKeys if self.keyIsGuid(x)]:
            ratingKey = self.resolveGuidToKey(k, guidLookup)
            if ratingKey != k:
                self.log.debug("Resolving custom allowedKey GUID %s to ratingKey %s" % (k, ratingKey))
                self.allowedKeys.append(int(ratingKey))
                self.allowedKeys.remove(k)
            else:
                self.log.error("Unable to resolve GUID %s to ratingKey in custom allowedKeys" % (k))
        for k in [x for x in self.blockedKeys if self.keyIsGuid(x)]:
            ratingKey = self.resolveGuidToKey(k, guidLookup)
            if ratingKey != k:
                self.log.debug("Resolving custom blockedKeys GUID %s to ratingKey %s" % (k, ratingKey))
                self.blockedKeys.append(int(ratingKey))
                self.blockedKeys.remove(k)
            else:
                self.log.error("Unable to resolve GUID %s to ratingKey in custom blockedKeys" % (k))

    def loadRatingKeys(self, server: PlexServer) -> dict:
        self.log.debug("Generating ratingKey to GUID match table")
        ratingKeyLookup = {item.ratingKey: item for item in server.library.all() if hasattr(item, "ratingKey")}
        for v in list(ratingKeyLookup.values()):
            if v.type == "show":
                for e in v.episodes():
                    ratingKeyLookup[e.ratingKey] = e
                for s in v.seasons():
                    ratingKeyLookup[s.ratingKey] = s
        self.log.debug("Finished generated match table with %d entries" % (len(ratingKeyLookup)))
        return ratingKeyLookup

    def convertToGuids(self, server: PlexServer) -> None:
        ratingKeyLookup = self.loadRatingKeys(server)
        for k in [x for x in list(self.markers.keys()) if not self.keyIsGuid(x)]:
            guid = self.resolveKeyToGuid(k, ratingKeyLookup)
            if k != guid:
                self.log.debug("Resolving custom marker ratingKey %s to GUID %s" % (k, guid))
                self.markers[guid] = self.markers.pop(k)
            else:
                self.log.error("Unable to resolve ratingKey %s to GUID in custom markers" % (k))
        for k in [x for x in list(self.offsets.keys()) if not self.keyIsGuid(x)]:
            guid = self.resolveKeyToGuid(k, ratingKeyLookup)
            if k != guid:
                self.log.debug("Resolving custom offset ratingKey %s to GUID %s" % (k, guid))
                self.offsets[guid] = self.offsets.pop(k)
            else:
                self.log.error("Unable to resolve ratingKey %s to GUID in custom offsets" % (k))
        for k in [x for x in self.allowedKeys if not self.keyIsGuid(x)]:
            guid = self.resolveKeyToGuid(str(k), ratingKeyLookup)
            if k != guid:
                self.log.debug("Resolving custom allowedKey ratingKey %s to GUID %s" % (k, guid))
                self.allowedKeys.append(guid)
                self.allowedKeys.remove(k)
            else:
                self.log.error("Unable to resolve ratingKey %s to GUID in custom allowedKeys" % (k))
        for k in [x for x in self.blockedKeys if not self.keyIsGuid(x)]:
            guid = self.resolveKeyToGuid(str(k), ratingKeyLookup)
            if k != guid:
                self.log.debug("Resolving custom blockedKey ratingKey %s to GUID %s" % (k, guid))
                self.blockedKeys.append(guid)
                self.blockedKeys.remove(k)
            else:
                self.log.error("Unable to resolve ratingKey %s to GUID in custom blockedKeys" % (k))

    def keyIsGuid(self, key: str) -> bool:
        return any(str(key).startswith(p) for p in self.PREFIXES)

    def resolveGuidToKey(self, key: str, guidLookup: dict) -> str:
        k = key.split(".")
        base = guidLookup.get(k[0])
        if base:
            if len(k) == 2 and base.type == "show":
                return base.season(season=int(k[1])).ratingKey
            elif len(k) == 3 and base.type == "show":
                return base.episode(season=int(k[1]), episode=int(k[2])).ratingKey
            else:
                return base.ratingKey
        return key

    def resolveKeyToGuid(self, key: str, ratingKeyLookup: dict, prefix="tmdb://") -> str:
        base = ratingKeyLookup.get(int(key))
        if base and hasattr(base, "guids"):
            if base.type == "episode":
                tmdb = next(g for g in base.show().guids if g.id.startswith(prefix))
                return "%s.%d.%d" % (tmdb.id, base.seasonNumber, base.episodeNumber)
            elif base.type == "season":
                tmdb = next(g for g in base.show().guids if g.id.startswith(prefix))
                return "%s.%d" % (tmdb.id, base.seasonNumber)
            else:
                tmdb = next(g for g in base.guids if g.id.startswith(prefix))
                return tmdb.id
        return key

    def __init__(self, data: dict, cascade: bool, logger: logging.Logger = None) -> None:
        self.data = data
        for m in self.markers:
            if isinstance(self.markers[m], dict):
                self.markers[m] = [self.markers[m]]
        self.cascade = cascade
        self.log = logger or logging.getLogger(__name__)
