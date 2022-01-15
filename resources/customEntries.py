import json
import logging


class CustomEntries():
    defaults = {
        "markers": {},
        "allowed": {
            'users': [],
            'clients': [],
            'keys': []
        },
        "blocked": {
            'users': [],
            'clients': [],
            'keys': []
        },
        "clients": {}
    }

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

    def __init__(self, path, logger=None) -> None:
        self.data = self.defaults
        self.log = logger or logging.getLogger(__name__)
        if path:
            with open(path, encoding='utf-8') as f:
                self.data = json.load(f)

        # Make sure default entries are present to prevent exceptions
        for k in self.defaults:
            if k not in self.data:
                self.data[k] = {}
            for sk in self.defaults[k]:
                if sk not in self.data[k]:
                    self.data[k][sk] = []
