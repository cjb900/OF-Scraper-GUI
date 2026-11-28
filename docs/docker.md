[🏠 README](../README.md) · [Install](install.md) · [GUI guide](gui-guide.md) · [Docker](docker.md) · [PostgreSQL](postgresql.md) · [Plugins](plugins.md) · [Versions](versions.md) · [Troubleshooting](troubleshooting.md)

---

# Docker

Run the **patched GUI** on a machine without a desktop. You open the GUI from any browser (noVNC) or a VNC client. You can also run just the command-line daemon, with no GUI at all ([`MODE=cli`](#running-the-cli-instead-of-the-gui-modecli)).

| File | Role |
|---|---|
| `docker-compose.yml` | The `ofscraper-gui` service: build settings, environment, volumes, networking |
| `docker/Dockerfile` | Ubuntu 24.04 + OF-Scraper + the GUI patch + FFmpeg + TigerVNC / noVNC |
| `docker/entrypoint.sh` | Starts the virtual display, VNC and noVNC, then `ofscraper --gui` (restarted if it exits). With `MODE=cli`: only `ofscraper $CLI_ARGS` |

## What you get

- OF-Scraper installed and patched with the GUI (default **3.18.1**, with OnlyFans and Fansly tabs)
- A virtual display with a built-in VNC server (TigerVNC) and a small window manager
- **The desktop resizes to fit your browser window**, and the GUI stays maximized in it
- **noVNC** on port **6699** (browser) and raw **VNC** on port **5900**, with an optional password (`VNC_PASSWORD`)
- **FFmpeg inside the image** (needed for DRM merges; don't mount a host copy)
- If the GUI exits or crashes, it is started again after `GUI_RESTART_DELAY` seconds (default 5)
- `docker stop` asks OF-Scraper to cancel the current scrape and exit cleanly (within `stop_grace_period: 30s`)
- A health check: `docker ps` shows the container as `healthy` while the display and noVNC answer
- A start-up warning in the log when a site's Save Location isn't on a mounted volume

## Files you need

Docker builds from the **repository root**, the folder that contains `docker-compose.yml`. You don't need the `OF-Scraper-3.x.x/` source folders.

```text
OF-Scraper-GUI/                          ← run all docker compose commands here
├── docker-compose.yml
├── docker/
│   ├── Dockerfile
│   └── entrypoint.sh
└── patch_ofscraper_3.18.1_gui.py        ← the patch for the version you build (at the repo root)
```

The Dockerfile copies `patch_ofscraper_*_gui.py` from the **repo root**, not from `OF-Scraper-3.18.1/`. Only the patch for the version you build has to be there; keeping all of them is fine.

`docker/comfyui-joycaption/` is a separate, optional stack for the JoyCaption plugin; see [Plugins](plugins.md#joycaption-tagger-joycaption_tagger).

## Prerequisites

1. **Docker Engine** with the Compose plugin (`docker compose version` should work), or **Docker Desktop** on Windows / macOS
2. This repository on the Docker host
3. A few GB of free disk for the first build

## Before the first build: edit `docker-compose.yml`

The compose file is set up for a **Linux** host. Two things must be checked before the first run.

### 1. Volumes (required)

The compose file mounts folders from your computer into the container. Replace every `/home/YOU/...` path with yours. **Left side** = path on the Docker host, **right side** = path inside the container.

```yaml
volumes:
  # 1) REQUIRED — config: auth.json, config.json, databases, logs, CDM keys (device/)
  - /home/YOU/.config/ofscraper:/root/.config/ofscraper
  # 2) OPTIONAL — only if config.json stores absolute paths under your host home
  #    (e.g. CDM keys at /home/YOU/.config/ofscraper/client_id.bin). Same path on both sides.
  - /home/YOU/.config/ofscraper:/home/YOU/.config/ofscraper
  # 3) REQUIRED — downloads. Same path on both sides, matching each site's Save Location
  - /home/YOU/Photos/OnlyFans:/home/YOU/Photos/OnlyFans
  - /home/YOU/Photos/Fansly:/home/YOU/Photos/Fansly
```

- **Each site has its own Save Location.** OnlyFans reads `config.json`, Fansly reads `fansly/config.json`; both files are in the config folder (volume 1). Set each one (in that tab's **Configuration → File Options**) to a mounted folder. A site left on its default saves to `/root/Data/ofscraper/OnlyFans` or `/root/Data/ofscraper/Fansly` inside the container, which isn't on a volume, so those downloads are lost when the container is recreated. Mounting one parent folder (e.g. `/home/YOU/Photos:/home/YOU/Photos`) covers both sites' folders under it.

- **Volume 1 must end in `/root/.config/ofscraper`.** Inside the container OF-Scraper runs as `root`, so its home folder is `/root`. It always reads `config.json`, auth, the databases and the `plugins/` folder from `/root/.config/ofscraper`, whatever path you mount elsewhere.
- **Volume 2 doesn't replace volume 1.** It only makes absolute paths saved in `config.json` (like CDM key paths) work. If you mount your config folder **only** at `/home/YOU/.config/ofscraper`, the file browser will show your files there, but the GUI will use an empty `/root/.config/ofscraper`: no plugins on the Plugins page, default settings, no auth, and anything you save is lost when the container is recreated.
- Create the host folders first. If a folder doesn't exist, Docker creates it owned by `root`.
- The download folder uses the **same path on both sides**, so the Save Location in your `config.json` works both on the desktop and in the container. If you mount it somewhere else in the container, set **Configuration → File Options → Save Location** to the **container** path.
- On Windows (Docker Desktop) the left side is a Windows path, e.g. `C:/Users/you/.config/ofscraper:/root/.config/ofscraper`. The right side must then be a Linux path such as `/data/OnlyFans`, and Save Location must be set to that path.

### 2. Networking (Docker Desktop users must change this)

The compose file uses **host networking** (`network_mode: host`): the container shares the host's network directly, which removes Docker's NAT overhead on large scrapes. noVNC is then simply at `http://<host>:6699/`, with no port mapping.

**Host networking only works on Linux.** On **Docker Desktop (Windows / macOS)**, edit `docker-compose.yml`:

```yaml
    # network_mode: host        ← remove or comment out this line
    ports:                      ← and restore the ports block
      - "6699:6699"
      - "5900:5900"             # only if you want raw VNC
```

To use a different port with host networking, change `NOVNC_PORT` (and `VNC_PORT`) under `environment`. With the `ports:` block, change the **left** number instead (e.g. `"8669:6699"`).

## Quick start

From the repository root:

```bash
docker compose build ofscraper-gui     # first time, or after changing the patch or GUI_PATCH_VERSION
docker compose up -d ofscraper-gui     # start in the background
```

Open **http://localhost:6699/** (or `http://<host-ip>:6699/` from another computer). noVNC connects automatically and shows the GUI.

Then, in the GUI:

1. **Authentication**: paste or import credentials (see [Logging in inside Docker](#logging-in-inside-docker))
2. **Configuration**: check Save Location, Discord webhook and CDM key paths
3. For DRM videos, put the CDM key files in the config folder (see [CDM keys](#cdm-keys-and-ffmpeg))
4. Start a scrape from **Select Action**

Config and auth are stored on the config volume, so they survive rebuilds and restarts.

## Accessing the GUI

<img src="images/docker-novnc.png" width="700" alt="OF-Scraper GUI in Docker, open in a web browser through noVNC on port 6699: both the OnlyFans and Fansly tabs show a dot because both sites are scraping in one container (daemon mode, Privacy mode on); the host address is blurred">

| Method | Address | Notes |
|---|---|---|
| **Browser (noVNC)** | `http://localhost:6699/` | Easiest. From another computer: `http://<host-ip>:6699/` (check your firewall) |
| **VNC client** | `localhost:5900` | Any VNC viewer |

### Password (`VNC_PASSWORD`)

With `network_mode: host`, ports 6699 and 5900 listen on **every network interface** of the host. Without a password, anyone who can reach them controls the GUI: your OnlyFans and Fansly logins, CDM keys, and the mounted folders through its file dialogs.

```yaml
environment:
  - VNC_PASSWORD=choose-one
```

- When it's set, noVNC asks for it in the browser and VNC clients ask when they connect. Blank means no password.
- VNC uses only the **first 8 characters**.
- It's not encryption: noVNC over plain `http://` sends the session unencrypted. For access from outside your home network, use a VPN (or an HTTPS reverse proxy with its own login) instead of opening the ports.
- After changing it: `docker compose up -d --force-recreate ofscraper-gui` (no rebuild).

The desktop follows the size of your browser window: resize the window or go full screen and the GUI grows or shrinks with it. `SCREEN_WIDTH` / `SCREEN_HEIGHT` are only the starting size. In a VNC client, turn on its "resize remote session" option (TigerVNC viewer, Remmina and RealVNC have one) to get the same behavior. If you'd rather have a fixed size scaled to fit, open `http://<host>:6699/vnc.html?autoconnect=true&resize=scale`.

## What's in the config volume

| Path under the config mount | Purpose |
|---|---|
| `auth.json` / profile auth | Session credentials |
| `config.json` | OF-Scraper settings (save location, webhook, CDM mode, …) |
| `fansly/` | The Fansly tab's own `config.json`, `fansly_auth.json`, profile and databases |
| `gui_settings.json` | GUI-only preferences |
| `logging/` | OF-Scraper logs, plus `gui-docker.log` (everything the GUI prints) |
| `gui_crash_logs/` | Breadcrumbs and crash dumps |
| `device/` | CDM key files (`client_id.bin`, `private_key.pem`) |

## CDM keys and FFmpeg

**CDM keys:** DRM key creation does **not** work in Docker. Create the keys with the desktop GUI (**DRM Key Creation**), copy `client_id.bin` and `private_key.pem` into `device/` in the config folder, and set **Configuration → CDM** to the paths **as seen inside the container**, e.g. `/root/.config/ofscraper/device/client_id.bin`. (Or keep your desktop paths and use optional volume 2 above.)

**FFmpeg:** use the one in the image. Don't bind-mount a host `ffmpeg`: it usually needs libraries the container doesn't have, and DRM merges then leave videos stuck as `.part` files.

## Logging in inside Docker

The container can't see the browsers on your computer, so some login methods are limited:

| Method | In Docker? | Notes |
|---|---|---|
| Login in App Browser | ✅ | Since patch v410. **Authentication → Login in App Browser…** opens OnlyFans in a browser window inside the GUI; log in and the credentials are filled in for you. Recommended in Docker |
| Paste credentials manually | ✅ | Copy `sess` / `auth_id` / user agent / `x-bc` from DevTools in a desktop browser, paste into Authentication. All four must come from the **same browser and the same request**: e.g. a Firefox user agent with Chrome cookies fails with "Wrong user" (code 301) |
| Import Cookies from a host browser | ❌ | The container can't see browser profiles on the host |
| Login in System Browser | ❌ | No desktop browser inside the container |

The App Browser keeps its login in `/tmp`, which the compose file makes a RAM-only folder, so after a container restart it asks you to log in again. The credentials it captured are saved in `auth.json` and keep working.

**Also possible:** log in with the desktop GUI, then copy its `auth.json` into the mounted config folder before starting the container.

## Auto-starting a scrape (`GUI_ARGS`)

`GUI_ARGS` is added after `ofscraper --gui` when the container starts. With enough flags, the GUI skips the wizard and starts scraping, without any clicks: confirmation, disk-space and remote-key dialogs are skipped for these unattended starts.

```yaml
environment:
  # daemon scrape every 2 hours for all active subscriptions
  - GUI_ARGS=--daemon 120 --username ALL --sub-status active --posts all --discord low
```

```bash
docker compose up -d --force-recreate ofscraper-gui
```

Leave `GUI_ARGS` empty to just open the GUI and use it through noVNC.

`GUI_ARGS` starts **one** site: the tab used last, or the one you name with `--site onlyfans` or `--site fansly`. To keep a daemon on OnlyFans whichever tab you last clicked in noVNC, add `--site onlyfans`.

## Scraping both sites at start-up (`ONLYFANS_GUI_ARGS`, `FANSLY_GUI_ARGS`)

With the 3.17.1 patch or later, one container can scrape OnlyFans and Fansly at the same time. Each variable takes the same flags as `GUI_ARGS`, for that site only:

```yaml
environment:
  - ONLYFANS_GUI_ARGS=--daemon 120 --username ALL -ts --posts all --discord low
  - FANSLY_GUI_ARGS=--daemon 120 --username ALL --posts all --discord low
```

- Each site that has a variable set starts in its tab with its own scrape and its own daemon timer. Their files, databases and settings stay separate.
- A blank variable leaves that site's tab waiting for a click in noVNC.
- When either variable is set, `GUI_ARGS` is not used (the log says so). Leave it blank.
- `--site`, `--config` and `--gui` are set by the tab window for each site and are ignored here.
- **Fansly and `-ts` / `--sub-status active`:** on Fansly this keeps only creators with a paid subscription that hasn't ended. Creators you follow for free have no subscription, so they're dropped. Leave the flag out to scrape everyone you follow.
- Discord messages say which site they come from ("OF-Scraper · OnlyFans" / "OF-Scraper · Fansly").

## PostgreSQL (optional, 3.18.0 and later)

The image includes the PostgreSQL driver. To run the server itself, including next to this container in the same `docker-compose.yml`, see [PostgreSQL](postgresql.md#b-next-to-the-gui-container). Then either:

- set it up in the GUI under **Manage DBs → PostgreSQL**, which saves the address to `postgresql.env` in the config volume, or
- set it in `docker-compose.yml`:
  ```yaml
  environment:
    - OFSC_DATABASE_URL=postgresql://user:password@host:5432/database
  ```

Use one or the other: an address saved in the GUI replaces the one from `environment:`. Then bring your `user_data.db` files in from the same GUI tab before the next scrape. The [GUI guide](gui-guide.md#postgresql-optional-3180) covers what it does and what changes.

## Running the CLI instead of the GUI (`MODE=cli`)

Set `MODE=cli` to run plain `ofscraper` in the container: no GUI, virtual display, VNC or noVNC. It's meant for a **daemon** that scrapes on a schedule:

```yaml
environment:
  - MODE=cli
  - CLI_ARGS=--daemon 120 --username ALL --posts all --action download
```

```bash
docker compose up -d ofscraper-gui
docker compose logs -f ofscraper-gui          # the CLI's output
```

- **Stop:** `docker compose stop ofscraper-gui` shuts the daemon down cleanly (the current run is interrupted the same way as Ctrl+C), well within `stop_grace_period`.
- **Scrape now:** `docker kill --signal=USR1 ofscraper-gui` starts the next daemon run immediately when the daemon is idle between runs (ignored while a run is in progress).
- **Exit code:** the container exits with the CLI's exit code.
- `CLI_ARGS` are the arguments after `ofscraper` (the same flags as on a desktop). There is no `--gui` and no restart loop.

**One-shot runs and the interactive menu:** a run without `--daemon` exits when it's done, and `restart: unless-stopped` would start it again. Use `docker compose run --rm` for those. Arguments after the service name replace `CLI_ARGS`:

```bash
# one scrape, then the container is removed
docker compose run --rm -e MODE=cli ofscraper-gui --username somemodel --posts all --action download

# the interactive menu (needs a terminal; compose run provides one)
docker compose run --rm -e MODE=cli ofscraper-gui
```

`MODE=cli` without `CLI_ARGS`, arguments or a terminal stops with a message (exit code 2). Set `MODE=gui` (the default) to go back to the GUI.

## Choosing the patch version

Set `GUI_PATCH_VERSION` under `build.args` in `docker-compose.yml`, or pass it when building:

```bash
docker compose build --build-arg GUI_PATCH_VERSION=3.14.7 ofscraper-gui
docker compose up -d --force-recreate ofscraper-gui
```

Supported values: `3.12.9`, `3.14.3`, `3.14.5`, `3.14.7`, `3.17.1`, `3.18.0`, `3.18.1` (default and recommended: OnlyFans and Fansly tabs, optional PostgreSQL). 3.17.1 and later have the Fansly tab; 3.18.0 and later can use PostgreSQL. The build prints `Applied GUI patch: <id>` so you can confirm which patch went in.

## Updating

After pulling a new patch into the repository root:

```bash
docker compose build ofscraper-gui
docker compose up -d --force-recreate ofscraper-gui
```

Use `docker compose build --no-cache ofscraper-gui` if the build seems to reuse an old patch.

## Useful commands

```bash
docker compose up -d ofscraper-gui              # start in the background
docker compose logs -f ofscraper-gui            # entrypoint messages (CLI output in MODE=cli)
docker compose stop ofscraper-gui               # stop cleanly
docker compose down                             # stop and remove the container (volumes kept)
docker compose exec ofscraper-gui bash          # shell inside the running container
```

In GUI mode, the GUI's own output goes to `logging/gui-docker.log` in the config folder, not to `docker compose logs`.

`docker ps` shows the health check: `healthy` while the virtual display and noVNC answer, `unhealthy` if either has stopped (restart the container). In `MODE=cli` it always reports healthy.

### Quoting in `GUI_ARGS` and `CLI_ARGS`

All the start-up variables are read like a shell command line: quote a value that contains spaces (`--username "some name"`), and `*` is passed as is, not expanded. They're printed in the log, so don't put passwords or tokens in them.

### File ownership

The container runs as `root`, so the files it creates in your mounted folders (downloads, databases, logs) are owned by `root` on the host. To take them over: `sudo chown -R $USER: /home/YOU/Photos/OnlyFans` (and the same for your other mounted folders).

## Limitations

- **DRM key creation doesn't work in Docker.** Create keys on a desktop, then copy them in
- **Host browser cookie import and system-browser login don't work.** Paste credentials or copy `auth.json`
- **Don't bind-mount a host FFmpeg**
- **Host networking is Linux-only**; Docker Desktop needs the `ports:` block
- Plugins that need extra services (e.g. JoyCaption + ComfyUI) need their own compose stack: `docker/comfyui-joycaption/`

## Troubleshooting Docker

| Symptom | What to try |
|---|---|
| `docker compose`: no configuration file | Run commands from the repo root (where `docker-compose.yml` is) |
| Build fails at `COPY patch_ofscraper_…_gui.py` | The patch for `GUI_PATCH_VERSION` must be at the **repo root** (e.g. `patch_ofscraper_3.18.1_gui.py` next to `docker-compose.yml`) |
| Docker Desktop: can't open noVNC | Remove `network_mode: host` and restore the `ports:` block (see [Networking](#2-networking-docker-desktop-users-must-change-this)) |
| Linux: can't open noVNC | Check that nothing else uses port 6699 and your firewall allows it; try `http://127.0.0.1:6699/` |
| Container keeps restarting with `exec /entrypoint.sh: no such file or directory` | `docker/entrypoint.sh` has Windows line endings (copied or edited on Windows). Current images strip them during the build, and the repo's `.gitattributes` keeps git checkouts LF. With an older Dockerfile, run `sed -i 's/\r$//' docker/entrypoint.sh`, then `docker compose build ofscraper-gui` and `docker compose up -d --force-recreate ofscraper-gui` |
| Log says `WARNING: OnlyFans saves to …` (or Fansly) `which is not on a mounted volume` | That site's downloads are inside the container and are lost when it's recreated. Mount the folder (see [Volumes](#1-volumes-required)) or change that site's Save Location to a mounted folder |
| noVNC asks for a password | `VNC_PASSWORD` is set in `docker-compose.yml`; enter it (first 8 characters) |
| GUI doesn't fill the browser; black space around it | The image predates the TigerVNC change: copy the new `docker/Dockerfile` and `docker/entrypoint.sh`, rebuild and recreate the container, then reload the noVNC tab. Use the default address (`http://<host>:6699/`), which includes `resize=remote` |
| Plugins page is empty and shows `Plugins folder: /root/.config/ofscraper/plugins`, but the file browser shows your plugins under `/home/YOU/.config/ofscraper/plugins` | Your config folder isn't mounted at `/root/.config/ofscraper`. Add `- /home/YOU/.config/ofscraper:/root/.config/ofscraper` to `volumes:` (see [Volumes](#1-volumes-required)), then `docker compose up -d --force-recreate ofscraper-gui`. No rebuild needed |
| Settings or auth gone after recreating the container | Same cause: without the `/root/.config/ofscraper` mount the GUI saves inside the container, and that is thrown away on recreate |
| **Open plugins folder**: `No such file or directory: 'xdg-open'` | Expected: the container has no file manager. Manage the plugin folder from the host, in your mounted config folder's `plugins/` |
| Emoji show as empty boxes (sidebar, Live Monitor, buttons) | The image predates the emoji font: copy the new `docker/Dockerfile` and rebuild (`docker compose build ofscraper-gui`, then `docker compose up -d --force-recreate ofscraper-gui`) |
| Black or empty noVNC screen | Wait a few seconds for the display and GUI to start; check `logging/gui-docker.log` |
| GUI keeps restarting | It crashed; see `logging/gui-docker.log` and `gui_crash_logs/` in the config folder |
| Patch older than v410: **Login in App Browser** says "Not Supported in Docker" | Update the patch (`GUI_PATCH_VERSION` / the root `patch_ofscraper_3.18.1_gui.py`) and rebuild the image |
| Auth works on the desktop but not in Docker | Copy the desktop `auth.json` into the config folder; Dynamic Mode / SSL Verify must match |
| Videos stuck as `.part` | Use the image's FFmpeg (remove any host ffmpeg mount); check the CDM key paths are valid **inside** the container |
| DRM videos skipped with "CDM files can't be used" | The key paths in Configuration → CDM don't exist inside the container; see [CDM keys](#cdm-keys-and-ffmpeg) |
| Downloads missing on the host | Save Location must be the **container** path of your download mount |
| Permission errors on Linux bind mounts | The container runs as `root`; fix ownership of the host folder, or create the folders before the first run |

Crash diagnostics are on the config volume: `gui_crash_logs/model_fetch_breadcrumbs.log` and `gui_crash_logs/faulthandler.log`.
