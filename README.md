PlexAutoSkip
==============
 **Automatically skip tagged content in Plex**

A background python script that monitors local playback on your server and will automatically 'press' the Skip Intro button or skip other similarly tagged content automatically. Maintains real-time playback states for your server (not dependent on API updates) for accurate skip timing. Threaded to handle multiple players simultaneously. Several layers of state validation to prevent unnecessary stuttering/buffering. Custom definitions allow you to expand on features and functionality beyond what is automatically detected by Plex

Only works on LAN sessions (not remote) as Plex does not allow seeking adjustments via the API for remote sessions

Notice
--------------
Plex has recently removed the "advertise as player" feature from the Plex Web client as well as its desktop clients for Windows/Mac/Linux which breaks the PlexAutoSkip functionality. I'm unclear why this feature which has been stable and present for years was removed without warning, but the patch notes can be found [here](https://forums.plex.tv/t/plex-for-mac-windows-and-linux/446435/63) and [here](https://forums.plex.tv/t/plex-web/20528/389).

Currently I would recommend rolling back to Plex Desktop Client **Plex-1.41.0.2876-e960c9ca** or Plex Server **Plex-1.27.2.5929-a806c5905** which still includes **Plex Web 4.76.1**. If you access the web player via plex.tv/web this will be a newer version of the web player which will not support "advertise as player", you'll need to access the web client from the local plex server address (localhost:32400/web).

You can disable the auto update feature of the Plex Desktop Client by accessing the `plex.ini` file in `C:\Users\<username>\AppData\Local\Plex` and adding the line below to the debug section

```ini
[debug]
disableUpdater=true
```

This is a temporary solution unfortunately and I would encourage all of your who support this project and hope for similar projects in the future to voice your support on the [Plex forums](https://forums.plex.tv/t/please-restore-plex-companion-advertise-as-player-feature/799789)


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
