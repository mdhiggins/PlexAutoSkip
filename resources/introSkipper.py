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


class IntroSkipper():
    media_sessions = {}
    delete = []
    ignored = []
    customEntries = None

    GDM_ERROR = "FrameworkException: Unable to find player with identifier"
    FORBIDDEN_ERROR = "HTTPError: HTTP Error 403: Forbidden"
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
        except:
            self.log.exception("getDataFromSessions Error")
        return None

    def start(self, sslopt=None):
        self.listener = SSLAlertListener(self.server, self.processAlert, self.error, sslopt=sslopt, logger=self.log)
        self.listener.start()
        while self.listener.is_alive():
            try:
                for session in list(self.media_sessions.values()):
                    self.checkMedia(session)
                time.sleep(1)
            except KeyboardInterrupt:
                self.listener.stop()
                break

    def checkMedia(self, mediaWrapper):
        for marker in mediaWrapper.customMarkers:
            # self.log.debug("Checking custom marker %s (%d-%d)" % (marker.type, marker.start, marker.end))
            if (marker.start) <= mediaWrapper.viewOffset <= marker.end:
                self.log.info("Found a custom marker for media %s with range %d-%d and viewOffset %d" % (mediaWrapper, marker.start, marker.end, mediaWrapper.viewOffset))
                self.seekTo(mediaWrapper, marker.end)
                return

        if hasattr(mediaWrapper.media, 'chapters'):
            for chapter in [x for x in mediaWrapper.media.chapters if x.title and x.title.lower() == 'advertisement']:
                # self.log.debug("Checking chapter %s (%d-%d)" % (chapter.title, chapter.start, chapter.end))
                if (chapter.start + self.leftOffset) <= mediaWrapper.viewOffset <= chapter.end:
                    self.log.info("Found an advertisement chapter for media %s with range %d-%d and viewOffset %d" % (mediaWrapper, chapter.start + self.leftOffset, chapter.end, mediaWrapper.viewOffset))
                    self.seekTo(mediaWrapper, chapter.end + self.rightOffset)
                    return

        if hasattr(mediaWrapper.media, 'markers'):
            for marker in [x for x in mediaWrapper.media.markers if x.type and x.type.lower() in ['intro', 'commercial']]:
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
        for player in mediaWrapper.media.players:
            try:
                player.proxyThroughServer(True, self.server)
                # Playback / Media check fails if the timeline cannot be pulled but not all players return a timeline so check first
                if self.checkPlayerForMedia(player, mediaWrapper.media):
                    mediaWrapper.willSeek()
                    self.log.info("Seeking player %s playing %s from %d to %d" % (player.title, mediaWrapper, mediaWrapper.viewOffset, (targetOffset + self.rightOffset)))
                    try:
                        player.seekTo(targetOffset)
                        mediaWrapper.updateOffset(targetOffset)
                    except ElementTree.ParseError:
                        self.log.debug("ParseError, seems to be certain players but still functional, continuing")
                        mediaWrapper.updateOffset(targetOffset)
                    except (ReadTimeout, ReadTimeoutError, timeout):
                        self.log.debug("TimeoutError, removing from cache to prevent false triggers, will be restored with next sync")
                        del self.media_sessions[mediaWrapper.media.sessionKey]
                    except BadRequest as br:
                        if self.GDM_ERROR in br.args[0]:
                            self.log.error("BadRequest Error: Please enable 'Local Network Discovery (GDM)' in your Plex Server > Settings > Network options")
                        elif self.FORBIDDEN_ERROR in br.args[0]:
                            self.log.error("Forbidden Error: Please enable 'Advertise as player' in your Plex client settings and verify your server credentials/token")
            except:
                self.log.exception("Error seeking")
        mediaWrapper.seeking = False

    def checkPlayerForMedia(self, player, media):
        try:
            return not player.timeline or (player.isPlayingMedia(False) and player.timeline.key == media.key)
        except BadRequest as br:
            if self.GDM_ERROR in br.args[0]:
                self.log.error("BadRequest Error: Please enable 'Local Network Discovery (GDM)' in your Plex Server > Settings > Network options")
            elif self.FORBIDDEN_ERROR in br.args[0]:
                self.log.error("Forbidden Error: Please enable 'Advertise as player' in your Plex client settings and verify your server credentials/token")
            else:
                self.log.debug("checkPlayerForMedia failed with BadRequest", exc_info=1)
            return False

    def stillPlaying(self, mediaWrapper):
        for player in mediaWrapper.media.players:
            try:
                player.proxyThroughServer(True, self.server)
                if self.checkPlayerForMedia(player, mediaWrapper.media):
                    return True
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
                        wrapper = MediaWrapper(media)
                        if self.customEntries:
                            self.customEntries.loadCustomMarkers(wrapper)
                        if self.shouldAdd(media):
                            self.log.info("Found a new %s LAN session %s with viewOffset %d users %s" % (media.type, wrapper, media.viewOffset, media.usernames))
                            self.media_sessions[sessionKey] = wrapper
                        else:
                            if len(wrapper.customMarkers) > 0:
                                self.log.info("Found a blocked %s LAN session %s with viewOffset %d, adding only custom markers" % (media.type, wrapper, media.viewOffset))
                                if hasattr(wrapper.media, 'markers'):
                                    del wrapper.media.markers[:]
                                if hasattr(wrapper.media, 'chapters'):
                                    del wrapper.media.chapters[:]
                                self.media_sessions[sessionKey] = wrapper
                            else:
                                self.log.debug("Ignoring LAN session %s" % (sessionKey))
                                self.ignored.append(sessionKey)
                                self.ignored = self.ignored[-self.IGNORED_CAP:]
                    elif not self.media_sessions[sessionKey].seeking and not self.media_sessions[sessionKey].buffering:
                        self.log.debug("Updating an existing %s media session %s with viewOffset %d (previous %d)" % (media.type, self.media_sessions[sessionKey], media.viewOffset, self.media_sessions[sessionKey].viewOffset))
                        self.media_sessions[sessionKey].updateOffset(media.viewOffset)
                    elif self.media_sessions[sessionKey].seeking:
                        self.log.debug("Skipping update as session %s appears to be actively seeking" % (self.media_sessions[sessionKey]))
                    elif self.media_sessions[sessionKey].buffering:
                        self.log.debug("Skipping update as session %s appears to be actively buffering from a recent seek" % (self.media_sessions[sessionKey]))
                else:
                    pass
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

        if media.ratingKey in self.customEntries.allowedKeys:
            self.log.debug("Allowing media based on key %s" % (media.key))
            return True
        if media.ratingKey in self.customEntries.blockedKeys:
            self.log.debug("Blocking media based on key %s" % (media.key))
            return False
        if hasattr(media, "parentRatingKey"):
            if media.parentRatingKey in self.customEntries.allowedParentKeys:
                self.log.debug("Allowing media based on parent key %s" % (media.parentRatingKey))
                return True
            if media.parentRatingKey in self.customEntries.blockedParentKeys:
                self.log.debug("Blocking media based on parent key %s" % (media.parentRatingKey))
                return False
        if hasattr(media, "grandparentRatingKey"):
            if media.grandparentRatingKey in self.customEntries.allowedGrandparentKeys:
                self.log.debug("Allowing media based on grandparent key %s" % (media.grandparentRatingKey))
                return True
            if media.grandparentRatingKey in self.customEntries.blockedGrandparentKeys:
                self.log.debug("Blocking media based on grandparent key %s" % (media.grandparentRatingKey))
                return False
        if self.customEntries.allowedKeys + self.customEntries.allowedParentKeys + self.customEntries.allowedGrandparentKeys:
            self.log.debug("Blocking media because it was not on the allowed list")
            return False

        return True

    def error(self, data):
        self.log.error(data)
