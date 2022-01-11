#!/usr/bin/python3

import logging
import time
from resources.sslAlertListener import SSLAlertListener
from resources.mediaWrapper import MediaWrapper
from xml.etree import ElementTree
from urllib3.exceptions import ReadTimeoutError
from requests.exceptions import ReadTimeout
from socket import timeout


class IntroSkipper():
    media_sessions = {}
    delete = []
    allowed = {
        'keys': [],
        'parents': [],
        'grandparents': []
    }
    blocked = {
        'keys': [],
        'parents': [],
        'grandparents': []
    }

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
        self.listener = SSLAlertListener(self.server, self.processAlert, self.error, sslopt=sslopt)
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
        if hasattr(mediaWrapper.media, 'chapters'):
            for chapter in [x for x in mediaWrapper.media.chapters if x.title and x.title.lower() == 'advertisement']:
                # self.log.debug("Checking chapter %s (%d-%d)" % (chapter.title, chapter.start, chapter.end))
                if (chapter.start + self.leftOffset) <= mediaWrapper.viewOffset <= chapter.end:
                    self.log.info("Found an advertisement chapter for media %s with range %d-%d and viewOffset %d" % (mediaWrapper, chapter.start + self.leftOffset, chapter.end, mediaWrapper.viewOffset))
                    self.seekTo(mediaWrapper, chapter.end)
                    return

        if hasattr(mediaWrapper.media, 'markers'):
            for marker in [x for x in mediaWrapper.media.markers if x.type and x.type.lower() in ['intro', 'commercial']]:
                # self.log.debug("Checking marker %s (%d-%d)" % (marker.type, marker.start, marker.end))
                if (marker.start + self.leftOffset) <= mediaWrapper.viewOffset <= marker.end:
                    self.log.info("Found an intro marker for media %s with range %d-%d and viewOffset %d" % (mediaWrapper, marker.start + self.leftOffset, marker.end, mediaWrapper.viewOffset))
                    self.seekTo(mediaWrapper, marker.end)
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
                        player.seekTo(targetOffset + self.rightOffset)
                        mediaWrapper.updateOffset(targetOffset + self.rightOffset)
                    except ElementTree.ParseError:
                        self.log.debug("ParseError, seems to be certain players but still functional, continuing")
                        mediaWrapper.updateOffset(targetOffset + self.rightOffset)
                    except (ReadTimeout, ReadTimeoutError, timeout):
                        self.log.debug("TimeoutError, removing from cache to prevent false triggers, will be restored with next sync")
                        del self.media_sessions[mediaWrapper.media.sessionKey]
            except:
                self.log.exception("Error seeking")
        mediaWrapper.seeking = False

    def checkPlayerForMedia(self, player, media):
        return not player.timeline or (player.isPlayingMedia(False) and player.timeline.key == media.key)

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
            try:
                media = self.getDataFromSessions(sessionKey)
                if media and media.session and len(media.session) > 0 and media.session[0].location == 'lan':
                    wrapper = MediaWrapper(media)
                    if sessionKey not in self.media_sessions:
                        if self.shouldAdd(wrapper):
                            self.log.info("Found a new %s LAN session %s with viewOffset %d" % (media.type, wrapper, media.viewOffset))
                            self.media_sessions[sessionKey] = wrapper
                        else:
                            self.log.debug("Ignoring LAN session %s" % (wrapper))
                    elif not self.media_sessions[sessionKey].seeking and not self.media_sessions[sessionKey].buffering:
                        self.log.debug("Updating an existing %s media session %s with viewOffset %d (previous %d)" % (media.type, wrapper, media.viewOffset, self.media_sessions[sessionKey].viewOffset))
                        self.media_sessions[sessionKey] = wrapper
                    elif self.media_sessions[sessionKey].seeking:
                        self.log.debug("Skipping update as session %s appears to be actively seeking" % (wrapper))
                    elif self.media_sessions[sessionKey].buffering:
                        self.log.debug("Skipping update as session %s appears to be actively buffering from a recent seek" % (wrapper))
                else:
                    pass
            except:
                self.log.exception("Unexpected error getting media data from session alert")

    def shouldAdd(self, mediaWrapper):
        if mediaWrapper.media.ratingKey in self.allowed['keys']:
            self.log.debug("Allowing media based on key %s" % (mediaWrapper.media.key))
            return True
        if mediaWrapper.media.ratingKey in self.blocked['keys']:
            self.log.debug("Blocking media based on key %s" % (mediaWrapper.media.key))
            return False
        if hasattr(mediaWrapper.media, "parentRatingKey"):
            if mediaWrapper.media.parentRatingKey in self.allowed['parents']:
                self.log.debug("Allowing media based on parent key %s" % (mediaWrapper.media.parentRatingKey))
                return True
            if mediaWrapper.media.parentRatingKey in self.blocked['parents']:
                self.log.debug("Blocking media based on parent key %s" % (mediaWrapper.media.parentRatingKey))
                return False
        if hasattr(mediaWrapper.media, "grandparentRatingKey"):
            if mediaWrapper.media.grandparentRatingKey in self.allowed['grandparents']:
                self.log.debug("Allowing media based on grandparent key %s" % (mediaWrapper.media.grandparentRatingKey))
                return True
            if mediaWrapper.media.grandparentRatingKey in self.allowed['grandparents']:
                self.log.debug("Blocking media based on grandparent key %s" % (mediaWrapper.media.grandparentRatingKey))
                return False
        for k in self.allowed:
            if len(self.allowed[k]) > 0:
                self.log.debug("Blocking media because it was not on the allowed list")
                return False
        return True

    def error(self, data):
        self.log.error(data)
