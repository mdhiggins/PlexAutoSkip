from plexapi.alert import AlertListener


class SSLAlertListener(AlertListener):
    """ Override class for PlexAPI AlertListener to allow SSL options to be passed to WebSocket

        Parameters:
            server (:class:`~plexapi.server.PlexServer`): PlexServer this listener is connected to.
            callback (func): Callback function to call on received messages. The callback function
                will be sent a single argument 'data' which will contain a dictionary of data
                received from the server. :samp:`def my_callback(data): ...`
            callbackError (func): Callback function to call on errors. The callback function
                will be sent a single argument 'error' which will contain the Error object.
                :samp:`def my_callback(error): ...`
            sslopt (dict): ssl socket optional dict.
                :samp:`{"cert_reqs": ssl.CERT_NONE}`
    """
    def __init__(self, server, callback=None, callbackError=None, sslopt=None):
        super(SSLAlertListener, self).__init__(server, callback, callbackError)
        self._sslopt = sslopt

    def run(self):
        try:
            import websocket
        except ImportError:
            return
        # create the websocket connection
        url = self._server.url(self.key, includeToken=True).replace('http', 'ws')
        self._ws = websocket.WebSocketApp(url, on_message=self._onMessage, on_error=self._onError)
        self._ws.run_forever(sslopt=self._sslopt)
