#!/usr/bin/python3

import logging
import time
import os
from resources.settings import Settings
from resources.customEntries import CustomEntries
from resources.sslAlertListener import SSLAlertListener
from resources.mediaWrapper import Media, MediaWrapper, PLAYINGKEY, STOPPEDKEY, PAUSEDKEY, BUFFERINGKEY, DURATION_TOLERANCE, rd
from resources.log import getLogger
from xml.etree.ElementTree import ParseError
from urllib3.exceptions import ReadTimeoutError
from requests.exceptions import ReadTimeout
from socket import timeout
from plexapi.exceptions import BadRequest
from plexapi.client import PlexClient
from plexapi.server import PlexServer
from plexapi.playqueue import PlayQueue
from plexapi.base import PlexSession
from threading import Thread
from typing import Dict, List
from pkg_resources import parse_version


class Skipper():
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
        "Plex for Apple TV": 32500,
        "Plex for Windows": 32700,
        "Plex for Mac": 32700
    }

    CREDIT_SKIP_FIX = {
        "Plex for Roku": 1500
    }

    # :( </3
    BROKEN_CLIENTS = {
        "Plex Web": "4.83.2",
        "Plex for Windows": "1.46.1",
        "Plex for Mac": "1.46.1",
        "Plex for Linux": "1.46.1"
    }

    PROXY_ONLY = [
        "Plex Web",
        "Plex for Windows",
        "Plex for Mac",
        "Plex for Linux"
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
        self.verbose = os.environ.get("PAS_VERBOSE", "").lower() == "true"

        self.media_sessions: Dict[str, MediaWrapper] = {}
        self.delete: List[str] = []
        self.ignored: List[str] = []
        self.reconnect: bool = True

        self.log.debug("%s init with leftOffset %d rightOffset %d" % (self.__class__.__name__, self.settings.leftOffset, self.settings.rightOffset))
        self.log.debug("Offset tags %s" % (self.settings.offsetTags))
        self.log.debug("Operating in %s mode" % (self.settings.mode))
        self.log.debug("Skip tags %s" % (self.settings.tags))
        self.log.debug("Skip S01E01 %s" % (self.settings.skipS01E01))
        self.log.debug("Skip S**E01 %s" % (self.settings.skipE01))
        self.log.debug("Skip last chapter %s" % (self.settings.skiplastchapter))

        if settings.customEntries.needsGuidResolution:
            self.log.debug("Custom entries contain GUIDs that need ratingKey resolution")
            settings.customEntries.convertToRatingKeys(server)

        self.log.info("Skipper initiated and ready")

    def getMediaSession(self, sessionKey: str) -> PlexSession:
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
        if mediaWrapper.sinceLastAlert > self.TIMEOUT:
            self.log.debug("Session %s hasn't been updated in %d seconds" % (mediaWrapper, self.TIMEOUT))
            self.removeSession(mediaWrapper)

        if mediaWrapper.state == BUFFERINGKEY:
            return

        leftOffset = mediaWrapper.leftOffset or self.settings.leftOffset
        rightOffset = mediaWrapper.rightOffset or self.settings.rightOffset

        self.checkMediaSkip(mediaWrapper, leftOffset, rightOffset)
        self.checkMediaVolume(mediaWrapper, leftOffset, rightOffset)

        if mediaWrapper.skipnext and mediaWrapper.ended and (mediaWrapper.viewOffset >= rd(mediaWrapper.media.duration * DURATION_TOLERANCE)):
            self.log.info("Found ended session %s that has reached the end of its duration %d with viewOffset %d with skip-next enabled, will skip to next" % (mediaWrapper, mediaWrapper.media.duration, mediaWrapper.viewOffset))
            self.seekTo(mediaWrapper, mediaWrapper.media.duration)
        elif mediaWrapper.ended:
            self.log.debug("Session %s has been marked as ended with viewOffset %d and state %s, removing" % (mediaWrapper, mediaWrapper.viewOffset, mediaWrapper.state))
            self.removeSession(mediaWrapper)

    def checkMediaSkip(self, mediaWrapper: MediaWrapper, leftOffset: int, rightOffset: int) -> None:
        if mediaWrapper.state != PLAYINGKEY:
            return

        skipMarkers = [m for m in mediaWrapper.customMarkers if m.mode == Settings.MODE_TYPES.SKIP]
        for marker in skipMarkers:
            if marker.start <= mediaWrapper.viewOffset < rd(marker.end):
                self.log.info("Found a custom marker for media %s with range %d-%d and viewOffset %d (%d)" % (mediaWrapper, marker.start, marker.end, mediaWrapper.viewOffset, marker.key))
                self.seekTo(mediaWrapper, marker.end)
                return

        if mediaWrapper.mode != Settings.MODE_TYPES.SKIP:
            return

        if self.settings.skiplastchapter and mediaWrapper.lastchapter and (mediaWrapper.lastchapter.start / mediaWrapper.media.duration) > self.settings.skiplastchapter:
            if mediaWrapper.lastchapter and mediaWrapper.lastchapter.start <= mediaWrapper.viewOffset < rd(mediaWrapper.lastchapter.end):
                self.log.info("Found a valid last chapter for media %s with range %d-%d and viewOffset %d with skip-last-chapter enabled" % (mediaWrapper, mediaWrapper.lastchapter.start, mediaWrapper.lastchapter.end, mediaWrapper.viewOffset))
                self.seekTo(mediaWrapper, mediaWrapper.media.duration)
                return

        for chapter in mediaWrapper.chapters:
            if chapter.start <= mediaWrapper.viewOffset < rd(chapter.end):
                self.log.info("Found skippable chapter %s for media %s with range %d-%d and viewOffset %d" % (chapter.title, mediaWrapper, chapter.start, chapter.end, mediaWrapper.viewOffset))
                self.seekTo(mediaWrapper, chapter.end)
                return

        for marker in mediaWrapper.markers:
            lo = leftOffset if marker.type.lower() in mediaWrapper.offsetTags else 0
            ro = rightOffset if marker.type.lower() in mediaWrapper.offsetTags else 0

            start = marker.start if marker.start < lo else (marker.start + lo)
            if (start) <= mediaWrapper.viewOffset < rd(marker.end):
                self.log.info("Found skippable marker %s for media %s with range %d(+%d)-%d(+%d) and viewOffset %d" % (marker.type, mediaWrapper, marker.start, lo, marker.end, ro, mediaWrapper.viewOffset))
                self.seekTo(mediaWrapper, marker.end + ro)
                return

    def checkMediaVolume(self, mediaWrapper: MediaWrapper, leftOffset: int, rightOffset: int) -> None:
        if mediaWrapper.state != PLAYINGKEY:
            return

        shouldLower = self.shouldLowerMediaVolume(mediaWrapper, leftOffset, rightOffset)
        if not mediaWrapper.loweringVolume and shouldLower:
            self.log.info("Moving from normal volume to low volume viewOffset %d which is a low volume area for media %s, lowering volume to %d" % (mediaWrapper.viewOffset, mediaWrapper, self.settings.volumelow))
            self.setVolume(mediaWrapper, self.settings.volumelow, shouldLower)
            return
        elif mediaWrapper.loweringVolume and not shouldLower:
            self.log.info("Moving from lower volume to normal volume viewOffset %d for media %s, raising volume to %d" % (mediaWrapper.viewOffset, mediaWrapper, mediaWrapper.cachedVolume))
            self.setVolume(mediaWrapper, mediaWrapper.cachedVolume, shouldLower)
            return

    def shouldLowerMediaVolume(self, mediaWrapper: MediaWrapper, leftOffset: int, rightOffset: int) -> bool:
        customVolumeMarkers = [m for m in mediaWrapper.customMarkers if m.mode == Settings.MODE_TYPES.VOLUME]
        for marker in customVolumeMarkers:
            if marker.start <= mediaWrapper.viewOffset < marker.end:
                self.log.debug("Inside a custom marker for media %s with range %d-%d and viewOffset %d (%d), volume should be low" % (mediaWrapper, marker.start, marker.end, mediaWrapper.viewOffset, marker.key))
                return True

        if mediaWrapper.mode != Settings.MODE_TYPES.VOLUME:
            return False

        if self.settings.skiplastchapter and mediaWrapper.lastchapter and (mediaWrapper.lastchapter.start / mediaWrapper.media.duration) > self.settings.skiplastchapter:
            if mediaWrapper.lastchapter and mediaWrapper.lastchapter.start <= mediaWrapper.viewOffset <= mediaWrapper.lastchapter.end:
                self.log.debug("Inside a valid last chapter for media %s with range %d-%d and viewOffset %d with skip-last-chapter enabled, volume should be low" % (mediaWrapper, mediaWrapper.lastchapter.start, mediaWrapper.lastchapter.end, mediaWrapper.viewOffset))
                return True

        for chapter in mediaWrapper.chapters:
            if chapter.start <= mediaWrapper.viewOffset < chapter.end:
                self.log.debug("Inside chapter %s for media %s with range %d-%d and viewOffset %d, volume should be low" % (chapter.title, mediaWrapper, chapter.start, chapter.end, mediaWrapper.viewOffset))
                return True

        for marker in mediaWrapper.markers:
            lo = leftOffset if marker.type.lower() in mediaWrapper.offsetTags else 0
            ro = rightOffset if marker.type.lower() in mediaWrapper.offsetTags else 0
            if (marker.start + lo) <= mediaWrapper.viewOffset < (marker.end + ro):
                self.log.debug("Inside marker %s for media %s with range %d(+%d)-%d(+%d) and viewOffset %d, volume should be low" % (marker.type, mediaWrapper, marker.start, lo, marker.end, ro, mediaWrapper.viewOffset))
                return True
        return False

    def seekTo(self, mediaWrapper: MediaWrapper, targetOffset: int) -> None:
        t = Thread(target=self._seekTo, args=(mediaWrapper, targetOffset,))
        t.start()

    def _seekTo(self, mediaWrapper: MediaWrapper, targetOffset: int) -> None:
        try:
            self.seekPlayerTo(mediaWrapper.player, mediaWrapper, targetOffset)
        except (ReadTimeout, ReadTimeoutError, timeout):
            self.log.debug("TimeoutError, removing from cache to prevent false triggers, will be restored with next sync")
            self.removeSession(mediaWrapper)
        except:
            self.log.exception("Exception, removing from cache to prevent false triggers, will be restored with next sync")
            self.removeSession(mediaWrapper)

    def seekPlayerTo(self, player: PlexClient, mediaWrapper: MediaWrapper, targetOffset: int, pq: PlayQueue = None) -> bool:
        if not player:
            return False

        try:
            try:
                if mediaWrapper.skipnext and targetOffset >= mediaWrapper.media.duration:
                    try:
                        pq = pq or PlayQueue.get(self.server, mediaWrapper.playQueueID)
                    except Exception as e:
                        self.log.warning("Seek target is the end but unable to get PlayQueue %d (%s) data from server, aborting to prevent extra skips or playback issues" % (mediaWrapper.playQueueID, mediaWrapper.media.playQueueItemID))
                        self.log.debug(e)
                        return False
                    return self.skipPlayerTo(player, mediaWrapper, pq)
                else:
                    if mediaWrapper.media.duration and targetOffset >= (mediaWrapper.media.duration - self.CREDIT_SKIP_FIX.get(player.product, 0)):
                        self.log.debug("TargetOffset %d is greater or equal to duration of media %d(-%d), adjusting to match" % (targetOffset, mediaWrapper.media.duration, self.CREDIT_SKIP_FIX.get(player.product, 0)))
                        targetOffset = mediaWrapper.media.duration - self.CREDIT_SKIP_FIX.get(player.product, 0)

                    if targetOffset <= mediaWrapper.viewOffset:
                        self.log.debug("TargetOffset %d is less than or equal to current viewOffset %d, ignoring" % (targetOffset, mediaWrapper.viewOffset))
                        return False

                    self.log.info("Seeking %s player playing %s from %d to %d" % (player.product, mediaWrapper, mediaWrapper.viewOffset, targetOffset))
                    mediaWrapper.seekTo(targetOffset, player)
                return True
            except ParseError:
                self.log.debug("ParseError, seems to be certain players but still functional, continuing")
                return True
            except BadRequest as br:
                self.logErrorMessage(br, "BadRequest exception seekPlayerTo")
                mediaWrapper.badSeek()
                return self.seekPlayerTo(self.recoverPlayer(player), mediaWrapper, targetOffset, pq)
        except:
            raise

    def skipPlayerTo(self, player: PlexClient, mediaWrapper: MediaWrapper, pq: PlayQueue) -> bool:
        self.removeSession(mediaWrapper)
        self.ignoreSession(mediaWrapper)

        if not pq or not pq.items:
            self.log.warning("Unable to get PlayQueue %d (%s) data from server, aborting to prevent extra skips or playback issues" % (mediaWrapper.playQueueID, mediaWrapper.media.playQueueItemID))
            return False

        commandDelay = mediaWrapper.commandDelay or self.settings.commandDelay

        if pq.items[-1] == mediaWrapper.media:
            self.log.debug("Seek target is the end but no more items in the playQueue, using seekTo to prevent loop")
            mediaWrapper.seekTo(mediaWrapper.media.duration - self.CREDIT_SKIP_FIX.get(player.product, 0), player)
        else:
            nextItem: Media = pq[pq.items.index(mediaWrapper.media) + 1]
            server = self.server
            if mediaWrapper.plexsession.user != self.server.myPlexAccount() and mediaWrapper.userToken:
                server = PlexServer(self.server._baseurl, token=mediaWrapper.userToken, session=self.server._session, timeout=self.server._timeout)
            newQueue = PlayQueue.create(server, list(pq.items), nextItem)
            self.log.debug("Creating new PlayQueue %d with start item %s" % (newQueue.playQueueID, nextItem))
            time.sleep(commandDelay / 1000)
            player.stop()
            time.sleep(commandDelay / 1000)
            player.playMedia(newQueue)
        return True

    def setVolume(self, mediaWrapper: MediaWrapper, volume: int, lowering: bool) -> None:
        t = Thread(target=self._setVolume, args=(mediaWrapper, volume, lowering))
        t.start()

    def _setVolume(self, mediaWrapper: MediaWrapper, volume: int, lowering: bool) -> None:
        try:
            self.setPlayerVolume(mediaWrapper.player, mediaWrapper, volume, lowering)
        except (ReadTimeout, ReadTimeoutError, timeout):
            self.log.debug("TimeoutError, removing from cache to prevent false triggers, will be restored with next sync")
            self.removeSession(mediaWrapper)
        except:
            self.log.exception("Exception, removing from cache to prevent false triggers, will be restored with next sync")
            self.removeSession(mediaWrapper)

    def setPlayerVolume(self, player: PlexClient, mediaWrapper: MediaWrapper, volume: int, lowering: bool) -> bool:
        if not player:
            return False
        try:
            try:
                previousVolume = self.settings.volumehigh if lowering else self.settings.volumelow
                if player.timeline and player.timeline.volume is not None:
                    previousVolume = player.timeline.volume
                else:
                    self.log.debug("Unable to access timeline data for player %s to cache previous volume value, will restore to %d" % (player.product, previousVolume))
                self.log.info("Setting %s player volume playing %s from %d to %d" % (player.product, mediaWrapper, previousVolume, volume))
                mediaWrapper.updateVolume(volume, previousVolume, lowering)
                player.setVolume(volume)
                return True
            except ParseError:
                self.log.debug("ParseError, seems to be certain players but still functional, continuing")
                return True
            except BadRequest as br:
                self.logErrorMessage(br, "BadRequest exception setPlayerVolume")
                return self.setPlayerVolume(self.recoverPlayer(player), mediaWrapper, volume, lowering)
        except:
            raise

    def safeVersion(self, version) -> str:
        return version.split("-")[0]

    def validPlayer(self, player: PlexClient) -> bool:
        bad = self.BROKEN_CLIENTS.get(player.product)
        if bad and player.version and parse_version(self.safeVersion(player.version)) >= parse_version(bad):
            self.log.error("Bad %s version %s due to Plex team removing 'Advertise as Player/Plex Companion' functionality. Please visit %s#notice to review this issue and voice your support on the Plex forums for this feature to be restored" % (player.product, player.version, self.TROUBLESHOOT_URL))
            return False
        return True

    def recoverPlayer(self, player: PlexClient, protocol: str = "http://") -> PlexClient:
        if player.product in self.PROXY_ONLY:
            self.log.debug("Player %s (%s) does not support direct IP connections, nothing to fall back upon, returning None" % (player.title, player.product))
            return None

        if not player._proxyThroughServer:
            self.log.debug("Player %s (%s) is already not proxying through server, no fallback options left" % (player.title, player.product))
            return None
        port = int(self.server._myPlexClientPorts().get(player.machineIdentifier, self.CLIENT_PORTS.get(player.product, self.DEFAULT_CLIENT_PORT)))
        baseurl = "%s%s:%d" % (protocol, player.address, port)
        self.log.debug("Modifying client for direct connection using baseURL %s for player %s (%s)" % (baseurl, player.title, player._baseurl))
        player._baseurl = baseurl
        player.proxyThroughServer(False)
        return player

    def processAlert(self, data: dict) -> None:
        if data['type'] == 'playing':
            sessionKey = int(data['PlaySessionStateNotification'][0]['sessionKey'])
            clientIdentifier = data['PlaySessionStateNotification'][0]['clientIdentifier']
            pasIdentifier = MediaWrapper.getSessionClientIdentifier(sessionKey, clientIdentifier)

            if pasIdentifier in self.ignored:
                if self.verbose:
                    self.log.debug("Ignoring session %s" % pasIdentifier)
                return

            try:
                state = data['PlaySessionStateNotification'][0]['state']
                viewOffset = int(data['PlaySessionStateNotification'][0]['viewOffset'])
                playQueueID = int(data['PlaySessionStateNotification'][0].get('playQueueID', 0))

                if pasIdentifier not in self.media_sessions:
                    mediaSession = self.getMediaSession(sessionKey)
                    if self.verbose:
                        self.log.debug("Alert for %s with state %s viewOffset %d playQueueID %d location %s" % (pasIdentifier, state, viewOffset, playQueueID, mediaSession.session.location))
                    if mediaSession and mediaSession.session and mediaSession.session.location == 'lan':
                        wrapper = MediaWrapper(mediaSession, clientIdentifier, state, playQueueID, self.server, settings=self.settings, custom=self.customEntries, logger=self.log)
                        if not self.blockedClientUser(wrapper):
                            if self.shouldAdd(wrapper):
                                self.addSession(wrapper)
                            else:
                                if len(wrapper.customMarkers) > 0:
                                    wrapper.customOnly = True
                                    self.addSession(wrapper)
                                else:
                                    self.ignoreSession(wrapper)
                else:
                    mediaSession = self.media_sessions[pasIdentifier]
                    mediaSession.updateOffset(viewOffset, state=state)
                    if not mediaSession.ended and state in [STOPPEDKEY, PAUSEDKEY] and not self.getMediaSession(sessionKey):
                        self.media_sessions[pasIdentifier].ended = True

            except KeyboardInterrupt:
                raise
            except:
                self.log.exception("Unexpected error getting data from session alert")

    def blockedClientUser(self, mediaWrapper: MediaWrapper) -> bool:
        session = mediaWrapper.plexsession

        # Users
        if session._username in self.customEntries.blockedUsers:
            self.log.debug("Blocking %s based on blocked user in %s" % (mediaWrapper, session._username))
            return True
        if self.customEntries.allowedUsers and session._username not in self.customEntries.allowedUsers:
            self.log.debug("Blocking %s based on no allowed user in %s" % (mediaWrapper, session._username))
            return True
        elif self.customEntries.allowedUsers:
            self.log.debug("Allowing %s based on allowed user in %s" % (mediaWrapper, session._username))

        # Clients/players
        if self.customEntries.allowedClients and (mediaWrapper.player.title not in self.customEntries.allowedClients and mediaWrapper.clientIdentifier not in self.customEntries.allowedClients):
            self.log.debug("Blocking %s based on no allowed player %s %s" % (mediaWrapper, mediaWrapper.player.title, mediaWrapper.clientIdentifier))
            return True
        elif self.customEntries.allowedClients:
            self.log.debug("Allowing %s based on allowed player %s %s" % (mediaWrapper, mediaWrapper.player.title, mediaWrapper.clientIdentifier))
        if self.customEntries.blockedClients and (mediaWrapper.player.title in self.customEntries.blockedClients or mediaWrapper.clientIdentifier in self.customEntries.blockedClients):
            self.log.debug("Blocking %s based on blocked player %s %s" % (mediaWrapper, mediaWrapper.player.title, mediaWrapper.clientIdentifier))
            return True
        return False

    def shouldAdd(self, mediaWrapper: MediaWrapper) -> bool:
        media = mediaWrapper.media

        if mediaWrapper.media.type not in self.settings.types:
            self.log.debug("Blocking %s of type %s as its not on the approved type list %s" % (mediaWrapper, media.type, self.settings.types))
            return False

        if media.librarySectionTitle and media.librarySectionTitle.lower() in self.settings.ignoredlibraries:
            self.log.debug("Blocking %s in library %s as its library is on the ignored list %s" % (mediaWrapper, media.librarySectionTitle, self.settings.ignoredlibraries))
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

    def addSession(self, mediaWrapper: MediaWrapper) -> None:
        if mediaWrapper.player and self.validPlayer(mediaWrapper.player):
            if mediaWrapper.customOnly:
                self.log.info("Found blocked session %s viewOffset %d %s on %s, using custom markers only, sessions: %d" % (mediaWrapper, mediaWrapper.plexsession.viewOffset, mediaWrapper.plexsession._username, mediaWrapper.plexsession.player.product, len(self.media_sessions)))
            else:
                self.log.info("Found new session %s viewOffset %d %s on %s, sessions: %d" % (mediaWrapper, mediaWrapper.plexsession.viewOffset, mediaWrapper.plexsession._username, mediaWrapper.plexsession.player.product, len(self.media_sessions)))
            self.purgeOldSessions(mediaWrapper)
            self.checkMedia(mediaWrapper)
            self.media_sessions[mediaWrapper.pasIdentifier] = mediaWrapper
        else:
            self.log.info("Session %s has no accessible player, it will be ignored" % (mediaWrapper))
            self.ignoreSession(mediaWrapper)

    def ignoreSession(self, mediaWrapper: MediaWrapper) -> None:
        self.purgeOldSessions(mediaWrapper)
        self.ignored.append(mediaWrapper.pasIdentifier)
        self.ignored = self.ignored[-self.IGNORED_CAP:]
        self.log.debug("Ignoring session %s %s, ignored: %d" % (mediaWrapper, mediaWrapper.plexsession._username, len(self.ignored)))

    def purgeOldSessions(self, mediaWrapper: MediaWrapper) -> None:
        for sessionMediaWrapper in list(self.media_sessions.values()):
            if sessionMediaWrapper.clientIdentifier == mediaWrapper.player.machineIdentifier:
                self.log.info("Session %s shares player (%s) with new session %s, deleting old session %s" % (sessionMediaWrapper, mediaWrapper.player.machineIdentifier, mediaWrapper, sessionMediaWrapper.plexsession.sessionKey))
                self.removeSession(sessionMediaWrapper)
                break

    def removeSession(self, mediaWrapper: MediaWrapper):
        if mediaWrapper.pasIdentifier in self.media_sessions:
            del self.media_sessions[mediaWrapper.pasIdentifier]
            self.log.debug("Deleting session %s, sessions: %d" % (mediaWrapper, len(self.media_sessions)))

    def error(self, data: dict) -> None:
        self.log.error(data)

    def logErrorMessage(self, exception: Exception, default: str) -> None:
        for e in self.ERRORS:
            if e in exception.args[0]:
                self.log.error(self.ERRORS[e])
                return
        self.log.exception("%s, see %s" % (default, self.TROUBLESHOOT_URL))
