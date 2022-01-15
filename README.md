PlexAutoSkip
==============
 **Automatically skip tagged content in Plex**

A background python script that monitors local playback on your server and will automatically 'press' the Skip Intro button or skip other similarly tagged content automatically

Only works on LAN sessions (not remote) as Plex does not allow seeking adjustments via the API for remote sessions

Currently Plex uses markers and chapters to tag potentially skippable content as follows:
- Markers
  - Intros
  - Commercials
- Chapters
  - Advertisements

Requirements
--------------
- Python3
- PIP
- PlexPass (for automatic markers)
- PlexAPI
- Websocket-client

Setup
--------------
1. Enable `Enable local network discovery (GDM)` in your Plex Server > Network settings
2. Enable `Advertise as player` on Plex players
3. Ensure you have [Python](https://docs.python-guide.org/starting/installation/#installation) and [PIP](https://packaging.python.org/en/latest/tutorials/installing-packages/) installed
4. Clone the repository
5. Install requirements using `pip install -R ./setup/requirements.txt`
6. Run `main.py` once to generate config files or copy samples from the `./setup` directory and rename removing the `.sample` suffix
7. Edit `./config/config.ini` with your Plex account or Plex server settings
8. Run `main.py`

_Script has fallback methods for when GDM is not enabled or is nonfunctional_

config.ini
--------------
- See https://github.com/mdhiggins/PlexAutoSkip/wiki/Configuration

custom.json
--------------
Optional custom parameters for which movie, show, season, or episode should be included or blocked. You can also define custom skip segments for media if you do not have Plex Pass or would like to skip additional areas of content
- See https://github.com/mdhiggins/PlexAutoSkip/wiki/Configuration

Docker
--------------
- https://github.com/mdhiggins/plexautoskip-docker

Special Thanks
--------------
- Plex
- PlexAPI
- Skippex
- https://github.com/Casvt/Plex-scripts/blob/main/stream_control/intro_skipper.py
