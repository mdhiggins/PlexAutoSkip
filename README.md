PlexAutoSkip
==============
 **Automatically skip tagged content in Plex**

A background python script that monitors local playback on your server and will automatically 'press' the Skip Intro button or skip other similarly tagged content automatically. Maintains real-time playback states for your server (not dependent on API updates) for accurate skip timing. Threaded to handle multiple players simultaneously. Several layers of state validation to prevent unnecessary stuttering/buffering. Custom definitions allow you to expand on features and functionality beyond what is automatically detected by Plex. Works with all automatically tagged markers including intros, credits, and advertisements.

Requirements
--------------
- LAN sessions (not remote) as Plex does not allow seeking adjustments via the API for remote sessions
- "Advertise as Player" / Plex Companion compatible player

See https://github.com/mdhiggins/PlexAutoSkip/wiki/Troubleshooting#notice for changes to Plex Web based players

Features
--------------
- Skip any Plex identified markers with adjustable offsets
  - Markers
    - Intros (Plex Pass)
    - Commercials (Plex Pass)
  - Chapters
    - Advertisements
- Only skip for watched content
- Ignore skipping series and season premieres
- Skip last chapter (credits)
- Bypass the "Up Next" screen
- Custom Definitions
  - Define your own markers when auto detection fails
  - Filter clients/users
  - Export and audit Plex markers to make corrections / fill in gaps
  - Bulk edit marker timing
  - Negative value offsets to skip relative to content end
- Mute or lower volume instead of skipping
  - Client must support Plex setVolume API call
- Docker


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
- See https://github.com/mdhiggins/PlexAutoSkip/wiki/Configuration#configuration-options-for-configini

custom.json
--------------
Optional custom parameters for which movie, show, season, or episode should be included or blocked. You can also define custom skip segments for media if you do not have Plex Pass or would like to skip additional areas of content
- See https://github.com/mdhiggins/PlexAutoSkip/wiki/Configuration#configuration-options-for-customjson
- For a small but hopefully growing repository of community made custom markers, please see https://github.com/mdhiggins/PlexAutoSkipCustomMarkers

Docker
--------------
- https://github.com/mdhiggins/plexautoskip-docker

custom_audit.py
--------------
Additional support script that contains features to check and modify your custom definition files in mass. Can offset entire collections of markers, export data from Plex, convert between GUID and ratingKey formats and more

```
# Get started
python custom_audit.py --help
```

Special Thanks
--------------
- Plex
- PlexAPI
- Skippex
- https://github.com/Casvt/Plex-scripts/blob/main/stream_control/intro_skipper.py
- https://github.com/liamcottle
