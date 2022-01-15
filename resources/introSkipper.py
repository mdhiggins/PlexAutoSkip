#!/usr/bin/python3

import logging
import time
from resources.sslAlertListener import SSLAlertListener
from resources.mediaWrapper import MediaWrapper
from xml.etree import ElementTree
from urllib3.exceptions import ReadTimeoutError
from requests.exceptions import ReadTimeout
from socket import timeout
from plexapi.exceptions import BadRequest
from plexapi.client import PlexClient


class IntroSkipper():
    media_sessions = {}
    delete = []
    ignored = []
    customEntries = None
    reconnect = True

    GDM_ERROR = "FrameworkException: Unable to find player with identifier"
    GDM_ERROR_MSG = "BadRequest Error, see https://github.com/mdhiggins/PlexAutoSkip/wiki/Troubleshooting#badrequest-error"
    FORBIDDEN_ERROR = "HTTPError: HTTP Error 403: Forbidden"
    FORBIDDEN_ERROR_MSG = "Forbidden Error, see https://github.com/mdhiggins/PlexAutoSkip/wiki/Troubleshooting#forbidden-error"

    CLIENT_PORTS = {
        "Plex for Roku": 8324,
        "Plex for Android (TV)": 32500,
        "Plex for Android (Mobile)": 32500,
        "Plex for iOS": 32500
    }
    PROXY_ONLY = ["Plex Web"]
    DEFAULT_CLIENT_PORT = 32500

    IGNORED_CAP = 200

    def __init__(self, server, leftOffset=0, rightOffset=0, timeout=60 * 2, logger=None):
        self.server = server
        self.log = logger or logging.getLogger(__name__)
        self.leftOffset = leftOffset
        self.rightOffset = rightOffset
        self.timeout = timeout
        self.timeoutWithoutCheck = True

    def getDataFromSessions(self, sessionKey):
        try:
            for session in self.server.sessions():
                if session.sessionKey == sessionKey:
                    return session
        except KeyboardInterrupt:
            raise
        except:
            self.log.exception("getDataFromSessions Error")
        return None

    def start(self, sslopt=None):
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

    def checkMedia(self, mediaWrapper):
        for marker in mediaWrapper.customMarkers:
            # self.log.debug("Checking custom marker %s (%d-%d)" % (marker.type, marker.start, marker.end))
            if (marker.start) <= mediaWrapper.viewOffset <= marker.end:
                self.log.info("Found a custom marker for media %s with range %d-%d and viewOffset %d" % (mediaWrapper, marker.start, marker.end, mediaWrapper.viewOffset))
                self.seekTo(mediaWrapper, marker.end)
                return

        for chapter in mediaWrapper.chapters:
            # self.log.debug("Checking chapter %s (%d-%d)" % (chapter.title, chapter.start, chapter.end))
            if (chapter.start + self.leftOffset) <= mediaWrapper.viewOffset <= chapter.end:
                self.log.info("Found an advertisement chapter for media %s with range %d-%d and viewOffset %d" % (mediaWrapper, chapter.start + self.leftOffset, chapter.end, mediaWrapper.viewOffset))
                self.seekTo(mediaWrapper, chapter.end + self.rightOffset)
                return

        for marker in mediaWrapper.markers:
            # self.log.debug("Checking marker %s (%d-%d)" % (marker.type, marker.start, marker.end))
            if (marker.start + self.leftOffset) <= mediaWrapper.viewOffset <= marker.end:
                self.log.info("Found an intro marker for media %s with range %d-%d and viewOffset %d" % (mediaWrapper, marker.start + self.leftOffset, marker.end, mediaWrapper.viewOffset))
                self.seekTo(mediaWrapper, marker.end + self.rightOffset)
                return

        if mediaWrapper.sinceLastUpdate > self.timeout:
            self.log.debug("Session %s hasn't been updated in %d seconds, checking if still playing" % (mediaWrapper, self.timeout))
            # Check to see if media is still playing before being deleted, probably overkill so using a bool (timeoutWithoutCheck) to bypass this check for now
            if self.timeoutWithoutCheck or not self.stillPlaying(mediaWrapper):
                self.log.debug("Session %s will be removed from cache" % (mediaWrapper))
                del self.media_sessions[mediaWrapper.media.sessionKey]

    def seekTo(self, mediaWrapper, targetOffset):
        mediaWrapper.willSeek()
        for player in mediaWrapper.media.players:
            try:
                if self.seekPlayerTo(player, mediaWrapper.media, targetOffset):
                    self.log.info("Seeking player playing %s from %d to %d" % (mediaWrapper, mediaWrapper.viewOffset, (targetOffset + self.rightOffset)))
                    mediaWrapper.updateOffset(targetOffset)
            except (ReadTimeout, ReadTimeoutError, timeout):
                self.log.debug("TimeoutError, removing from cache to prevent false triggers, will be restored with next sync")
                del self.media_sessions[mediaWrapper.media.sessionKey]
                break
            except:
                self.log.exception("Error seeking")
        mediaWrapper.seeking = False

    def seekPlayerTo(self, player, media, targetOffset):
        if not player:
            return False

        try:
            player = self.checkPlayerForMedia(player, media)
            if player:
                try:
                    player.seekTo(targetOffset)
                    return True
                except ElementTree.ParseError:
                    self.log.debug("ParseError, seems to be certain players but still functional, continuing")
                    return True
                except BadRequest as br:
                    if self.GDM_ERROR in br.args[0]:
                        self.log.error(self.GDM_ERROR_MSG)
                    elif self.FORBIDDEN_ERROR in br.args[0]:
                        self.log.error(self.FORBIDDEN_ERROR_MSG)
                    else:
                        self.log.exception("BadRequest exception")
                    return self.seekPlayerTo(self.recoverPlayer(player), media, targetOffset)
            else:
                self.log.debug("Not seeking player %s, checkPlayerForMedia returned False" % (player.title))
                return False
        except:
            raise

    def checkPlayerForMedia(self, player, media):
        if not player:
            return None

        try:
            if not player.timeline or (player.isPlayingMedia(False) and player.timeline.key == media.key):
                return player
        except BadRequest as br:
            if self.GDM_ERROR in br.args[0]:
                self.log.error(self.GDM_ERROR_MSG)
            elif self.FORBIDDEN_ERROR in br.args[0]:
                self.log.error(self.FORBIDDEN_ERROR_MSG)
            else:
                self.log.debug("checkPlayerForMedia failed with BadRequest", exc_info=1)
            return self.checkPlayerForMedia(self.recoverPlayer(player), media)
        return None

    def recoverPlayer(self, player, protocol="http://"):
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

    def stillPlaying(self, mediaWrapper):
        for player in mediaWrapper.media.players:
            try:
                if self.checkPlayerForMedia(player, mediaWrapper.media):
                    return True
            except KeyboardInterrupt:
                raise
            except:
                self.log.exception("Error while checking player")
        return False

    def processAlert(self, data):
        if data['type'] == 'playing':
            sessionKey = int(data['PlaySessionStateNotification'][0]['sessionKey'])

            if sessionKey in self.ignored:
                return

            try:
                media = self.getDataFromSessions(sessionKey)
                if media and media.session and len(media.session) > 0 and media.session[0].location == 'lan':
                    if sessionKey not in self.media_sessions:
                        wrapper = MediaWrapper(media, self.server, custom=self.customEntries, logger=self.log)
                        if self.shouldAdd(media):
                            self.log.info("Found a new %s session %s with viewOffset %d %s" % (media.type, wrapper, media.viewOffset, media.usernames))
                            self.addSession(sessionKey, wrapper)
                        else:
                            if len(wrapper.customMarkers) > 0:
                                self.log.info("Found a blocked %s session %s with viewOffset %d, will use custom markers only" % (media.type, wrapper, media.viewOffset))
                                wrapper.customOnly = True
                                self.addSession(sessionKey, wrapper)
                            else:
                                self.ignoreSession(sessionKey)
                    elif not self.media_sessions[sessionKey].seeking and not self.media_sessions[sessionKey].buffering:
                        self.log.debug("Updating an existing %s media session %s with viewOffset %d (previous %d)" % (media.type, self.media_sessions[sessionKey], media.viewOffset, self.media_sessions[sessionKey].viewOffset))
                        self.media_sessions[sessionKey].updateOffset(media.viewOffset)
                    elif self.media_sessions[sessionKey].seeking:
                        self.log.debug("Skipping update as session %s appears to be actively seeking" % (self.media_sessions[sessionKey]))
                    elif self.media_sessions[sessionKey].buffering:
                        self.log.debug("Skipping update as session %s appears to be actively buffering from a recent seek" % (self.media_sessions[sessionKey]))
                else:
                    pass
            except KeyboardInterrupt:
                raise
            except:
                self.log.exception("Unexpected error getting data from session alert")

    def shouldAdd(self, media):
        if not self.customEntries:
            return True

        if any(b for b in self.customEntries.blockedUsers if b in media.usernames):
            self.log.debug("Blocking session based on blocked user %s" % (media.usernames))
            return False

        if self.customEntries.allowedUsers and not any(u for u in media.usernames if u in self.customEntries.allowedUsers):
            self.log.debug("Blocking session based on not allowed user %s" % (media.usernames))
            return False

        if self.customEntries.allowedClients and not any(player for player in media.players if player.title in self.customEntries.allowedClients):
            self.log.debug("Blocking session based on no allowed player in %s" % ([p.title for p in media.players]))
            return False

        if self.customEntries.blockedClients and any(player for player in media.players if player.title in self.customEntries.blockedClients):
            self.log.debug("Blocking session based on blocked player in %s" % ([p.title for p in media.players]))
            return False

        if media.ratingKey in self.customEntries.allowedKeys:
            self.log.debug("Allowing media based on key %s" % (media.ratingKey))
            return True
        if media.ratingKey in self.customEntries.blockedKeys:
            self.log.debug("Blocking media based on key %s" % (media.ratingKey))
            return False
        if hasattr(media, "parentRatingKey"):
            if media.parentRatingKey in self.customEntries.allowedKeys:
                self.log.debug("Allowing media based on parent key %s" % (media.parentRatingKey))
                return True
            if media.parentRatingKey in self.customEntries.blockedKeys:
                self.log.debug("Blocking media based on parent key %s" % (media.parentRatingKey))
                return False
        if hasattr(media, "grandparentRatingKey"):
            if media.grandparentRatingKey in self.customEntries.allowedKeys:
                self.log.debug("Allowing media based on grandparent key %s" % (media.grandparentRatingKey))
                return True
            if media.grandparentRatingKey in self.customEntries.blockedKeys:
                self.log.debug("Blocking media based on grandparent key %s" % (media.grandparentRatingKey))
                return False
        if self.customEntries.allowedKeys:
            self.log.debug("Blocking media because it was not on the allowed list")
            return False

        return True

    def addSession(self, sessionKey, mediaWrapper):
        if mediaWrapper.media.players:
            self.media_sessions[sessionKey] = mediaWrapper
        else:
            self.log.info("Session %s has no accessible players, it will be ignored" % (sessionKey))
            self.ignored.append(sessionKey)

    def ignoreSession(self, sessionKey):
        self.log.debug("Ignoring session %s" % (sessionKey))
        self.ignored.append(sessionKey)
        self.ignored = self.ignored[-self.IGNORED_CAP:]

    def error(self, data):
        self.log.error(data)
