import logging


class CustomEntries():
    @property
    def markers(self):
        return self.data.get("markers", {})

    @property
    def allowed(self):
        return self.data.get("allowed", {})

    @property
    def allowedClients(self):
        return self.allowed.get("clients", [])

    @property
    def allowedUsers(self):
        return self.allowed.get("users", [])

    @property
    def allowedKeys(self):
        return self.allowed.get("keys", [])

    @property
    def blocked(self):
        return self.data.get("blocked", {})

    @property
    def blockedClients(self):
        return self.blocked.get("clients", [])

    @property
    def blockedUsers(self):
        return self.blocked.get("users", [])

    @property
    def blockedKeys(self):
        return self.blocked.get("keys", [])

    @property
    def clients(self):
        return self.data.get("clients", [])

    def __init__(self, data, logger=None) -> None:
        self.data = data
        self.log = logger or logging.getLogger(__name__)
