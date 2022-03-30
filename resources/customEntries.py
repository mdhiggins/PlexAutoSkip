import logging
from typing import Dict, List


class CustomEntries():
    @property
    def markers(self) -> Dict[str, list]:
        return self.data.get("markers", {})

    @property
    def offsets(self) -> Dict[str, dict]:
        return self.data.get("offsets", {})

    @property
    def allowed(self) -> Dict[str, List[str]]:
        return self.data.get("allowed", {})

    @property
    def allowedClients(self) -> List[str]:
        return self.allowed.get("clients", [])

    @property
    def allowedUsers(self) -> List[str]:
        return self.allowed.get("users", [])

    @property
    def allowedKeys(self) -> List[str]:
        return self.allowed.get("keys", [])

    @property
    def blocked(self) -> List[str]:
        return self.data.get("blocked", {})

    @property
    def blockedClients(self) -> List[str]:
        return self.blocked.get("clients", [])

    @property
    def blockedUsers(self) -> List[str]:
        return self.blocked.get("users", [])

    @property
    def blockedKeys(self) -> List[str]:
        return self.blocked.get("keys", [])

    @property
    def clients(self) -> Dict[str, str]:
        return self.data.get("clients", {})

    def __init__(self, data: dict, cascade: bool, logger: logging.Logger = None) -> None:
        self.data = data
        for m in self.markers:
            if isinstance(self.markers[m], dict):
                self.markers[m] = [self.markers[m]]
        self.cascade = cascade
        self.log = logger or logging.getLogger(__name__)
