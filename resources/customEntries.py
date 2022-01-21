import logging


class CustomEntries():
    @property
    def markers(self) -> dict:
        return self.data.get("markers", {})

    @property
    def allowed(self) -> dict:
        return self.data.get("allowed", {})

    @property
    def allowedClients(self) -> list[str]:
        return self.allowed.get("clients", [])

    @property
    def allowedUsers(self) -> list[str]:
        return self.allowed.get("users", [])

    @property
    def allowedKeys(self) -> list[str]:
        return self.allowed.get("keys", [])

    @property
    def blocked(self) -> list[str]:
        return self.data.get("blocked", {})

    @property
    def blockedClients(self) -> list[str]:
        return self.blocked.get("clients", [])

    @property
    def blockedUsers(self) -> list[str]:
        return self.blocked.get("users", [])

    @property
    def blockedKeys(self) -> list[str]:
        return self.blocked.get("keys", [])

    @property
    def clients(self) -> dict:
        return self.data.get("clients", {})

    def __init__(self, data: dict, logger: logging.Logger = None) -> None:
        self.data = data
        self.log = logger or logging.getLogger(__name__)
