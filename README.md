PlexAutoSkip
==============
 **Automatically skip tagged content in Plex**

A background python script that monitors local playback on your server (LAN only) and will automatically 'press' the Skip Intro button or skip other similarly tagged content automatically

Currently Plex users markers and chapters to tag potentially skippable content as follows:
- Markers
  - Intros
  - Commercials
- Chapters
  - Advertisements

Requirements
--------------
- Python3
- PlexPass (markers are not available otherwise)
- PIP
- PlexAPI
- Websocket-client

Setup
--------------
1. Clone the repository
2. Install requirements using `pip install -R ./setup/requirements.txt`
3. Run `main.py` once to generate config files or copy samples from the `./setup` directory
4. Edit `./config/config.ini` with your Plex account or Plex server settings
5. Run `main.py`

Config.ini
--------------
- See https://github.com/mdhiggins/PlexAutoSkip/wiki/Configuration

Docker
--------------
Coming soon

Special Thanks
--------------
- Plex
- PlexAPI
- Skippex
- https://github.com/Casvt/Plex-scripts/blob/main/stream_control/intro_skipper.py
