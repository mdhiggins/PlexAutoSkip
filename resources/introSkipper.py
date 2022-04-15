#!/usr/bin/python3

import logging
import time
from resources.settings import Settings
from resources.customEntries import CustomEntries
from resources.sslAlertListener import SSLAlertListener
from resources.mediaWrapper import Media, MediaWrapper
from resources.log import getLogger
from xml.etree.ElementTree import ParseError
from urllib3.exceptions import ReadTimeoutError
from requests.exceptions import ReadTimeout
from socket import timeout
from plexapi.exceptions import BadRequest
from plexapi.client import PlexClient
from plexapi.server import PlexServer
from threading import Thread
from typing import Dict, List


class IntroSkipper():
    TROUBLESHOOT_URL = "https://github.com/mdhiggins/PlexAutoSkip/wiki/Troubleshooting"
    ERRORS = {
        "FrameworkException: Unable to find player with identifier": "BadRequest Error, see %s#badrequest-error" % TROUBLESHOOT_URL,
        "HTTPError: HTTP Error 403: Forbidden": "Forbidden Error, see %s#forbidden-error" % TROUBLESHOOT_URL
    }

    CLIENT_PORTS = {
        "Plex for Roku": 8324,
        "Plex for Android (TV)": 32500,
        "Plex for Android (Mobile)": 32500,
        "Plex for iOS": 32500,
        "Plex for Windows": 32700,
        "Plex for Mac": 32700
    }
    PROXY_ONLY = [
        "Plex Web",
        "Plex for Windows",
        "Plex for Mac"
    ]
    DEFAULT_CLIENT_PORT = 32500

    TIMEOUT = 30
    IGNORED_CAP = 200

    @property
    def customEntries(self) -> CustomEntries:
        return self.settings.customEntries

    def __init__(self, server: PlexServer, settings: Settings, logger: logging.Logger = None) -> None:
        self.server = server
        self.settings = settings
        self.log = logger or getLogger(__name__)

        self.media_sessions: Dict[str, MediaWrapper] = {}
        self.delete: List[str] = []
        self.ignored: List[str] = []
        self.reconnect: bool = True

        self.log.debug("IntroSeeker init with leftOffset %d rightOffset %d" % (self.settings.leftOffset, self.settings.rightOffset))
        self.log.debug("Skip tags %s" % (self.settings.tags))
        self.log.debug("Skip S01E01 %s" % (self.settings.skipS01E01))
        self.log.debug("Skip S**E01 %s" % (self.settings.skipE01))
        self.log.debug("Skip last chapter %s" % (self.settings.skiplastchapter))

        if settings.customEntries.needsGuidResolution:
            self.log.debug("Custom entries contain GUIDs that need ratingKey resolution")
            settings.customEntries.convertToRatingKeys(server)

    def getDataFromSessions(self, sessionKey: str) -> Media:
        try:
            return next(iter([session for session in self.server.sessions() if session.sessionKey == sessionKey]), None)
        except KeyboardInterrupt:
            raise
        except:
            self.log.exception("getDataFromSessions Error")
        return None

    def start(self, sslopt: dict = None) -> None:
        self.listener = SSLAlertListener(self.server, self.processAlert, self.error, sslopt=sslopt, logger=self.log)
        self.log.debug("Starting listener")
        self.listener.start()
        while self.listener.is_alive():
            try:
                for session in list(self.media_sessions.values()):
                    self.checkMedia(session)
                time.sleep(1)
            except KeyboardInterrupt:
                self.log.debug("Stopping listener")
                self.reconnect = False
                self.listener.stop()
                break
        if self.reconnect:
            self.start(sslopt)

    def checkMedia(self, mediaWrapper: MediaWrapper) -> None:
        if mediaWrapper.seeking:
            return

        for marker in mediaWrapper.customMarkers:
            if (marker.start) <= mediaWrapper.viewOffset <= marker.end:
                self.log.info("Found a custom marker for media %s with range %d-%d and viewOffset %d (%d)" % (mediaWrapper, marker.start, marker.end, mediaWrapper.viewOffset, marker.key))
                self.seekTo(mediaWrapper, marker.end)
                return

        leftOffset = mediaWrapper.leftOffset or self.settings.leftOffset
        rightOffset = mediaWrapper.rightOffset or self.settings.rightOffset

        if self.settings.skiplastchapter and mediaWrapper.lastchapter and (mediaWrapper.lastchapter.start / mediaWrapper.media.duration) > self.settings.skiplastchapter:
            if mediaWrapper.lastchapter and (mediaWrapper.lastchapter.start + leftOffset) <= mediaWrapper.viewOffset <= mediaWrapper.lastchapter.end:
                self.log.info("Found a valid last chapter for media %s with range %d-%d and viewOffset %d with skip-last-chapter enabled" % (mediaWrapper, mediaWrapper.lastchapter.start + leftOffset, mediaWrapper.lastchapter.end, mediaWrapper.viewOffset))
                self.seekTo(mediaWrapper, mediaWrapper.lastchapter.end)

        for chapter in mediaWrapper.chapters:
            if (chapter.start + leftOffset) <= mediaWrapper.viewOffset <= chapter.end:
                self.log.info("Found an advertisement chapter for media %s with range %d-%d and viewOffset %d" % (mediaWrapper, chapter.start + leftOffset, chapter.end, mediaWrapper.viewOffset))
                self.seekTo(mediaWrapper, chapter.end + rightOffset)
                return

        for marker in mediaWrapper.markers:
            if (marker.start + leftOffset) <= mediaWrapper.viewOffset <= marker.end:
                self.log.info("Found an intro marker for media %s with range %d-%d and viewOffset %d" % (mediaWrapper, marker.start + leftOffset, marker.end, mediaWrapper.viewOffset))
                self.seekTo(mediaWrapper, marker.end + rightOffset)
                return

        if mediaWrapper.sinceLastUpdate > self.TIMEOUT:
            self.log.debug("Session %s hasn't been updated in %d seconds" % (mediaWrapper, self.TIMEOUT))
            self.removeSession(mediaWrapper)

    def seekTo(self, mediaWrapper: MediaWrapper, targetOffset: int) -> None:
        t = Thread(target=self._seekTo, args=(mediaWrapper, targetOffset,))
        t.start()

    def _seekTo(self, mediaWrapper: MediaWrapper, targetOffset: int) -> None:
        for player in mediaWrapper.media.players:
            try:
                self.seekPlayerTo(player, mediaWrapper, targetOffset)
            except (ReadTimeout, ReadTimeoutError, timeout):
                self.log.debug("TimeoutError, removing from cache to prevent false triggers, will be restored with next sync")
                self.removeSession(mediaWrapper)
                break
            except:
                self.log.exception("Exception, removing from cache to prevent false triggers, will be restored with next sync")
                self.removeSession(mediaWrapper)

    def seekPlayerTo(self, player: PlexClient, mediaWrapper: MediaWrapper, targetOffset: int) -> bool:
        if not player:
            return False
        try:
            try:
                self.log.info("Seeking %s player playing %s from %d to %d" % (player.product, mediaWrapper, mediaWrapper.viewOffset, targetOffset))
                mediaWrapper.updateOffset(targetOffset, seeking=True)
                player.seekTo(targetOffset)
                return True
            except ParseError:
                self.log.debug("ParseError, seems to be certain players but still functional, continuing")
                return True
            except BadRequest as br:
                self.logErrorMessage(br, "BadRequest exception seekPlayerTo")
                return self.seekPlayerTo(self.recoverPlayer(player), mediaWrapper, targetOffset)
        except:
            raise

    def recoverPlayer(self, player: PlexClient, protocol: str = "http://") -> PlexClient:
        if player.product in self.PROXY_ONLY:
            self.log.debug("Player %s (%s) does not support direct IP connections, nothing to fall back upon, returning None" % (player.title, player.product))
            return None

        if not player._proxyThroughServer:
            self.log.debug("Player %s (%s) is already not proxying through server, no fallback options left" % (player.title, player.product))
            return None

        port = self.CLIENT_PORTS.get(player.product, self.DEFAULT_CLIENT_PORT)
        baseurl = "%s%s:%d" % (protocol, player.address, port)
        self.log.debug("Modifying client for direct connection using baseURL %s for player %s (%s)" % (baseurl, player.title, player._baseurl))
        player._baseurl = baseurl
        player.proxyThroughServer(False)
        return player

    def processAlert(self, data: dict) -> None:
        if data['type'] == 'playing':
            sessionKey = int(data['PlaySessionStateNotification'][0]['sessionKey'])
            state = data['PlaySessionStateNotification'][0]['state']

            if sessionKey in self.ignored:
                return

            try:
                media = self.getDataFromSessions(sessionKey)
                if media and media.session and len(media.session) > 0 and media.session[0].location == 'lan':
                    if sessionKey not in self.media_sessions:
                        wrapper = MediaWrapper(media, state, self.server, tags=self.settings.tags, custom=self.customEntries, logger=self.log)
                        if self.shouldAdd(wrapper):
                            self.addSession(sessionKey, wrapper)
                        else:
                            if len(wrapper.customMarkers) > 0:
                                wrapper.customOnly = True
                                self.addSession(sessionKey, wrapper)
                            else:
                                self.ignoreSession(sessionKey, wrapper)
                    else:
                        self.media_sessions[sessionKey].updateOffset(media.viewOffset, seeking=False, state=state)
                else:
                    pass
            except KeyboardInterrupt:
                raise
            except:
                self.log.exception("Unexpected error getting data from session alert")

    def shouldAdd(self, mediaWrapper: MediaWrapper) -> bool:
        media = mediaWrapper.media

        # Users
        if any(b for b in self.customEntries.blockedUsers if b in media.usernames):
            self.log.debug("Blocking %s based on blocked user in %s" % (mediaWrapper, media.usernames))
            return False
        if self.customEntries.allowedUsers and not any(u for u in media.usernames if u in self.customEntries.allowedUsers):
            self.log.debug("Blocking %s based on no allowed user in %s" % (mediaWrapper, media.usernames))
            return False
        elif self.customEntries.allowedUsers:
            self.log.debug("Allowing %s based on allowed user in %s" % (mediaWrapper, media.usernames))

        # Clients/players
        if self.customEntries.allowedClients and not any(player for player in media.players if player.title in self.customEntries.allowedClients):
            self.log.debug("Blocking %s based on no allowed player in %s" % (mediaWrapper, [p.title for p in media.players]))
            return False
        elif self.customEntries.allowedClients:
            self.log.debug("Allowing %s based on allowed player in %s" % (mediaWrapper, [p.title for p in media.players]))
        if self.customEntries.blockedClients and any(player for player in media.players if player.title in self.customEntries.blockedClients):
            self.log.debug("Blocking %s based on blocked player in %s" % (mediaWrapper, [p.title for p in media.players]))
            return False

        # First episodes
        if hasattr(media, "episodeNumber"):
            if media.episodeNumber == 1:
                if self.settings.skipE01 == Settings.SKIP_TYPES.NEVER:
                    self.log.debug("Blocking %s, first episode in season and skip-first-episode-season is %s" % (mediaWrapper, self.settings.skipE01))
                    return False
                elif self.settings.skipE01 == Settings.SKIP_TYPES.WATCHED and not media.isWatched:
                    self.log.debug("Blocking %s, first episode in season and skip-first-episode-season is %s and isWatched %s" % (mediaWrapper, self.settings.skipE01, media.isWatched))
                    return False
            if hasattr(media, "seasonNumber") and media.seasonNumber == 1 and media.episodeNumber == 1:
                if self.settings.skipS01E01 == Settings.SKIP_TYPES.NEVER:
                    self.log.debug("Blocking %s, first episode in series and skip-first-episode-series is %s" % (mediaWrapper, self.settings.skipS01E01))
                    return False
                elif self.settings.skipS01E01 == Settings.SKIP_TYPES.WATCHED and not media.isWatched:
                    self.log.debug("Blocking %s first episode in series and skip-first-episode-series is %s and isWatched %s" % (mediaWrapper, self.settings.skipS01E01, media.isWatched))
                    return False

        # Keys
        allowed = False
        if media.ratingKey in self.customEntries.allowedKeys:
            self.log.debug("Allowing %s for ratingKey %s" % (mediaWrapper, media.ratingKey))
            allowed = True
        if media.ratingKey in self.customEntries.blockedKeys:
            self.log.debug("Blocking %s for ratingKey %s" % (mediaWrapper, media.ratingKey))
            return False
        if hasattr(media, "parentRatingKey"):
            if media.parentRatingKey in self.customEntries.allowedKeys:
                self.log.debug("Allowing %s for parentRatingKey %s" % (mediaWrapper, media.parentRatingKey))
                allowed = True
            if media.parentRatingKey in self.customEntries.blockedKeys:
                self.log.debug("Blocking %s for parentRatingKey %s" % (mediaWrapper, media.parentRatingKey))
                return False
        if hasattr(media, "grandparentRatingKey"):
            if media.grandparentRatingKey in self.customEntries.allowedKeys:
                self.log.debug("Allowing %s for grandparentRatingKey %s" % (mediaWrapper, media.grandparentRatingKey))
                allowed = True
            if media.grandparentRatingKey in self.customEntries.blockedKeys:
                self.log.debug("Blocking %s for grandparentRatingKey %s" % (mediaWrapper, media.grandparentRatingKey))
                return False
        if self.customEntries.allowedKeys and not allowed:
            self.log.debug("Blocking %s, not on allowed list" % (mediaWrapper))
            return False

        # Watched
        if not self.settings.skipunwatched and not media.isWatched:
            self.log.debug("Blocking %s, unwatched and skip-unwatched is %s" % (mediaWrapper, self.settings.skipunwatched))
            return False
        return True

    def addSession(self, sessionKey: str, mediaWrapper: MediaWrapper) -> None:
        if mediaWrapper.media.players:
            self.purgeOldSessions(mediaWrapper)
            self.checkMedia(mediaWrapper)
            self.media_sessions[sessionKey] = mediaWrapper
            if mediaWrapper.customOnly:
                self.log.info("Found blocked session %s viewOffset %d %s, using custom markers only, sessions: %d" % (mediaWrapper, mediaWrapper.media.viewOffset, mediaWrapper.media.usernames, len(self.media_sessions)))
            else:
                self.log.info("Found new session %s viewOffset %d %s, sessions: %d" % (mediaWrapper, mediaWrapper.media.viewOffset, mediaWrapper.media.usernames, len(self.media_sessions)))
        else:
            self.log.info("Session %s has no accessible players, it will be ignored" % (sessionKey))
            self.ignoreSession(sessionKey, mediaWrapper)

    def ignoreSession(self, sessionKey: str, mediaWrapper: MediaWrapper) -> None:
        self.purgeOldSessions(mediaWrapper)
        self.ignored.append(sessionKey)
        self.ignored = self.ignored[-self.IGNORED_CAP:]
        self.log.debug("Ignoring session %s %s, ignored: %d" % (mediaWrapper, mediaWrapper.media.usernames, len(self.ignored)))

    def purgeOldSessions(self, mediaWrapper) -> None:
        mids = [x.machineIdentifier for x in mediaWrapper.media.players]
        if mids:
            for session in list(self.media_sessions.values()):
                for player in session.media.players:
                    if player.machineIdentifier in mids:
                        self.log.info("Session %s shares player (%s) with new session %s, deleting old session %s" % (session, player.machineIdentifier, mediaWrapper, session.media.sessionKey))
                        self.removeSession(session)
                        break

    def removeSession(self, mediaWrapper):
        if mediaWrapper.media.sessionKey in self.media_sessions:
            del self.media_sessions[mediaWrapper.media.sessionKey]
            self.log.debug("Deleting session %s, sessions: %d" % (mediaWrapper, len(self.media_sessions)))

    def error(self, data: dict) -> None:
        self.log.error(data)

    def logErrorMessage(self, exception: Exception, default: str) -> None:
        for e in self.ERRORS:
            if e in exception.args[0]:
                self.log.error(self.ERRORS[e])
                return
        self.log.exception("%s, see %s" % (default, self.TROUBLESHOOT_URL))
