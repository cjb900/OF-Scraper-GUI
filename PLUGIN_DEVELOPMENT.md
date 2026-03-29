# OF-Scraper Plugin System Documentation

Welcome to the OF-Scraper Plugin API. The plugin system lets you extend OF-Scraper and its GUI without touching the core source code. Use it to add sidebar pages, integrate local AI models, run post-download pipelines, or inject UI controls into existing pages.

---

## Where Are Plugins Stored?

Plugins are loaded from the `plugins` folder next to your OF-Scraper `config.json`:

- **Windows:** `C:\Users\<YourUser>\.config\ofscraper\plugins\`
- **Linux/macOS:** `/home/<YourUser>/.config/ofscraper/plugins/`

The folder is created automatically on first launch if it does not exist.

Plugins are loaded in both **GUI mode** (`ofscraper --gui`) and **headless/CLI mode** (`ofscraper`). The only hook that is GUI-only is `on_ui_setup`.

---

## Plugin Structure

Each plugin lives in its own subdirectory. The folder name is used as the plugin's internal ID.

**Minimum required file:** `main.py`

`metadata.json` is optional but strongly recommended. All other files are up to you.

```text
plugins/
└── my_plugin/
    ├── main.py           # Required — entry point, must contain a Plugin class
    ├── metadata.json     # Optional but recommended — name, version, description
    ├── requirements.txt  # Optional — pip dependencies; triggers install dialog if missing
    ├── __init__.py       # Optional — auto-created by the loader if absent
    ├── gui.py            # Your choice — split complex plugins across multiple files
    ├── database.py       # Your choice
    └── settings.json     # Your choice — persist user settings here
```

### `metadata.json`

```json
{
  "name": "My Plugin",
  "version": "1.0.0",
  "author": "YourName",
  "description": "A short description shown in the GUI.",
  "api_version": 1
}
```

At load time, the manager injects an additional `"id"` key equal to the plugin folder name, so `self.metadata["id"]` always resolves to the directory name regardless of what you put in `metadata.json`.

---

## Enabling and Disabling Plugins

Add this line near the top of `main.py` to control whether the plugin loads:

```python
# Enabled 1 / Disabled 0 — default is 1 (enabled) if this line is absent
plugin_enabled = 1
```

Set it to `0` to make the Plugin Manager skip loading entirely without deleting the folder.

> **Important:** The check is a regex scan on the raw file text (`^plugin_enabled\s*=\s*([01])`) performed *before* the file is imported. The line must appear at the **start of a line with no indentation** and the value must be exactly `0` or `1`. Any other value is ignored and the plugin defaults to enabled.

---

## How Plugins Are Loaded

The Plugin Manager (`ofscraper.plugins.manager`) is a singleton. It runs `discover_and_load()` once at startup — from `main_window.py` in GUI mode, or from `main/open/load.py` in CLI mode.

For each subdirectory in the plugins folder it:

1. Checks for `main.py` — skips the folder if missing.
2. Reads `main.py` as text to check the `plugin_enabled` flag.
3. Parses `metadata.json` if present (not required).
4. Creates an empty `__init__.py` in the plugin folder if one does not already exist.
5. Registers the plugin folder as a Python package named `ofscraper_plugin_<foldername>`.
6. Imports `main.py` as `ofscraper_plugin_<foldername>.main`.
7. Looks for a class named exactly `Plugin` inside `main.py`.
8. Instantiates `Plugin(metadata=..., plugin_dir=...)` and calls `on_load()`.

Because the folder is registered as a package, **relative imports work**:

```python
from .database import init_db       # works
from .gui import MyTab              # works
from . import utils                 # works
```

---

## Writing a Plugin

### Minimal example

```python
# main.py
from ofscraper.plugins.base import BasePlugin

# plugin_enabled = 1  # default; set to 0 to disable without deleting

class Plugin(BasePlugin):

    def on_load(self):
        self.log.info("%s loaded!", self.metadata["name"])

    def on_item_downloaded(self, item_data, file_path):
        self.log.info("New file: %s  (type: %s)", file_path, item_data.mediatype)
```

### What `BasePlugin` gives you

`BasePlugin.__init__` sets three instance attributes before `on_load()` is called:

| Attribute | Type | Contents |
| :--- | :--- | :--- |
| `self.metadata` | `dict` | All fields from `metadata.json`, plus `"id"` = folder name |
| `self.plugin_dir` | `str` | Absolute path to your plugin folder |
| `self.log` | `logging.Logger` | Pre-configured logger named `ofscraper_plugin.<name>` |

You do **not** need to create your own logger or track the plugin directory manually.

---

## Available Event Hooks

Override any of these methods in your `Plugin` class. All hooks are called via `_safe_call`, so an unhandled exception will be logged but will **not** crash OF-Scraper.

| Method | Status | When it is called |
| :--- | :--- | :--- |
| `on_load()` | **Active** | Right after the plugin is instantiated. Use for initialisation. |
| `on_ui_setup(main_window)` | **Active (GUI only)** | After the PyQt6 main window is fully built. |
| `on_item_downloaded(item_data, file_path)` | **Active** | Each time a media file is successfully saved to disk. Fires in both GUI and CLI mode. |
| `on_scrape_start(config, models)` | **Reserved** | Defined but not yet dispatched. Override now for future compatibility. |
| `on_scrape_complete(stats)` | **Reserved** | Defined but not yet dispatched. Override now for future compatibility. |
| `on_unload()` | **Reserved** | Defined but not yet dispatched. |

### `on_item_downloaded(item_data, file_path)`

`item_data` is an ofscraper `Media` object — **not a plain dict**. The most useful properties:

| Property | Type | Description |
| :--- | :--- | :--- |
| `item_data.id` | `int` | Unique media ID from OnlyFans |
| `item_data.post_id` | `int` | ID of the parent post |
| `item_data.username` | `str` | Creator username |
| `item_data.mediatype` | `str` | `"Images"`, `"Videos"`, `"Audios"`, or `"Forced_skipped"` |
| `item_data.responsetype` | `str` | Source content type: `"Timeline"`, `"Archived"`, `"Stories"`, `"Highlights"`, `"Messages"`, `"Profile"` |
| `item_data.url` | `str \| None` | Direct download URL (`None` for DRM-protected content) |
| `item_data.filename` | `str \| None` | Base filename derived from the URL |
| `item_data.text` | `str` | Caption text from the parent post |
| `item_data.date` | `str` | Media creation date (ISO format) |
| `item_data.downloadtype` | `str` | `"Normal"` or `"Protected"` (DRM) |

`file_path` is the **absolute path string** of the saved file on disk.

```python
def on_item_downloaded(self, item_data, file_path):
    if item_data.mediatype == "Images":
        self.log.info(
            "New image from @%s — post %s: %s",
            item_data.username, item_data.post_id, file_path
        )
```

### `on_ui_setup(main_window)`

Called after the PyQt6 main window is built. `main_window` is the `QMainWindow` instance. See the **Adding a Sidebar Page** section below for the full pattern.

---

## Adding a Sidebar Page (`on_ui_setup`)

The most common GUI integration is adding a new page to the left navigation bar:

```python
def on_ui_setup(self, main_window):
    from PyQt6.QtCore import Qt
    from ofscraper.gui.widgets.styled_button import NavButton

    # 1. Create your page widget
    self.my_tab = MyTabWidget(self)

    # 2. Register it with the stacked page area
    main_window._add_page("my_plugin_page", self.my_tab)

    # 3. Create a navigation button and register it
    btn = NavButton("🔧 My Plugin")
    main_window._nav_group.addButton(btn)
    main_window._nav_buttons["my_plugin_page"] = btn

    # 4. Insert the button above the expanding stretch in the nav layout
    nav_layout = main_window._nav_frame.layout()
    stretch_idx = -1
    for i in range(nav_layout.count()):
        item = nav_layout.itemAt(i)
        if item and item.spacerItem() is not None:
            if item.expandingDirections() & Qt.Orientation.Vertical:
                stretch_idx = i
                break
    if stretch_idx >= 0:
        nav_layout.insertWidget(stretch_idx, btn)
    else:
        nav_layout.addWidget(btn)

    # 5. Connect the button to navigate to your page
    btn.clicked.connect(lambda checked: main_window._navigate("my_plugin_page"))
```

### Injecting widgets into existing pages

You can also inject widgets (e.g. a compact command bar) directly into existing pages:

```python
from PyQt6.QtWidgets import QFrame

def on_ui_setup(self, main_window):
    action_page = getattr(main_window, "action_page", None)
    if action_page:
        layout = action_page.layout()
        bar = MyCommandBar(self, parent=action_page)
        sep = QFrame(parent=action_page)
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.insertWidget(0, sep)
        layout.insertWidget(0, bar)
```

---

## Multi-File Plugin Layout

For anything beyond a trivial plugin, split your code across multiple files the same way the built-in plugins do. Since the folder is registered as a package, all relative imports resolve correctly:

```text
plugins/
└── my_plugin/
    ├── main.py          # Plugin class + hook implementations
    ├── gui.py           # PyQt6 widgets (tab pages, dialogs, etc.)
    ├── database.py      # Persistence layer (e.g. peewee ORM models)
    ├── engine.py        # Heavy processing / AI model logic
    ├── settings.json    # Runtime config written by the GUI
    └── requirements.txt # Python dependencies
```

```python
# inside main.py
from .gui import MyTab
from .database import init_db, MediaItem
from .engine import MyModel
```

---

## Plugin Dependencies (`requirements.txt`)

If your plugin imports a package that is not installed, Python raises `ModuleNotFoundError`. The Plugin Manager catches this and:

1. Checks whether a `requirements.txt` exists in your plugin folder.
2. If it does, shows a GUI dialog listing the missing package with a one-click install button.
3. Detects the active install method (pip / pipx / uv) automatically and runs the appropriate command.
4. Shows a progress dialog while installing, then reports success or failure.

Include a `requirements.txt` listing all non-standard dependencies:

```text
torch>=2.0.0
Pillow>=9.0.0
peewee>=3.16.0
open_clip_torch
```

> **Note:** The install dialog only appears when the GUI (`QApplication`) is running. In headless CLI mode, the `ModuleNotFoundError` is logged but no prompt is shown.

---

## Accessing OF-Scraper Internals

Plugins run in the same Python process as OF-Scraper and can import any internal module:

```python
# Read the Discord webhook URL from ofscraper config
import ofscraper.utils.config.data as config_data
webhook_url = config_data.get_discord()

# Read per-run download counters (reset to 0 at the start of each scrape)
import ofscraper.commands.scraper.actions.utils.globals as cg
videos_this_run  = cg.video_count
photos_this_run  = cg.photo_count
audios_this_run  = cg.audio_count
skipped_this_run = cg.skipped
```

Use internal imports carefully — these APIs can change between OF-Scraper versions. Where possible, rely on the hook arguments rather than reaching into internals directly.

---

## Settings Persistence

Plugins are responsible for their own settings. The recommended pattern is a `settings.json` file inside `self.plugin_dir`:

```python
import json
from pathlib import Path

def on_load(self):
    self.settings_path = Path(self.plugin_dir) / "settings.json"
    self.settings = {"my_option": True}
    if self.settings_path.exists():
        self.settings.update(json.loads(self.settings_path.read_text()))

def save_settings(self):
    self.settings_path.write_text(json.dumps(self.settings, indent=2))
```

---

## Included Plugins

Three plugins ship with OF-Scraper GUI as references:

### Intelligent AI Tagger (`ai_tagger`)
Automatically tags every downloaded image using a local computer-vision model. Supports WD14 (Danbooru tags), OpenCLIP ViT-B-32 (zero-shot label matching), Florence-2 (generative captions), and custom fine-tuned `.safetensors` checkpoints. Adds a **Smart Gallery** sidebar page with tag search, semantic similarity search, and smart folder organisation.
- Uses `on_load` to initialise the model and a SQLite database (via `peewee`).
- Uses `on_ui_setup` to inject the Smart Gallery page into the sidebar and add a help button to the main Help page.
- Uses `on_item_downloaded` to run inference on each new image immediately after it is saved. Fires in both GUI and CLI mode.
- Dependencies: `torch`, `open_clip_torch`, `transformers`, `peewee`, `timm`, `Pillow`.

### JoyCaption Tagger (`joycaption_tagger`)
Sends downloaded images to a [JoyCaption](https://github.com/fpgaminer/joycaption) node running inside ComfyUI (local or Docker) and stores the returned captions in a SQLite database. Caption style and length are user-configurable in the settings panel.
- Uses `on_ui_setup` to add a settings/gallery page to the sidebar.
- Uses `on_item_downloaded` to submit each new image to the ComfyUI HTTP API. Fires in both GUI and CLI mode.
- Requires: a running ComfyUI server with JoyCaption custom nodes installed (see `docker/comfyui-joycaption/`).

### LLM Assistant (`llm_assistant`)
Adds a natural-language chat panel (**🤖 AI Assistant**) to the sidebar. Type plain English commands; a locally-running GGUF model (via `llama-cpp-python`) translates them into GUI actions such as setting usernames, toggling filters, and starting downloads. Also injects a compact command bar into the action and area pages.
- Uses `on_ui_setup` to add the full chat tab, inject compact bars into existing pages, and handle first-run model selection and download flow.
- Uses `on_unload` to release the loaded GGUF model on exit.
- No Ollama, no cloud API, no internet required at runtime.
- Dependencies: `llama-cpp-python` (auto-prompted on first launch).

---

## Complete `main.py` Template

```python
# main.py
# Enabled 1 / Disabled 0 — default is 1 if this line is absent
plugin_enabled = 1

import json
from pathlib import Path
from ofscraper.plugins.base import BasePlugin


class Plugin(BasePlugin):
    """
    Replace this docstring with your plugin's description.
    The Plugin Manager instantiates this class once on startup,
    then calls on_load(). All other hooks are called as events occur.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_load(self):
        """
        Initialise resources.
        self.metadata, self.plugin_dir, and self.log are available here.
        """
        self.data_dir = Path(self.plugin_dir)
        self.settings_path = self.data_dir / "settings.json"
        self.settings = {}
        if self.settings_path.exists():
            try:
                self.settings = json.loads(self.settings_path.read_text())
            except Exception as e:
                self.log.error("Failed to load settings: %s", e)

        self.log.info(
            "%s v%s loaded",
            self.metadata["name"],
            self.metadata.get("version", "?"),
        )

    def on_unload(self):
        """
        Reserved — not yet dispatched by the Plugin Manager.
        Implement now for future compatibility; use for releasing
        model weights, DB connections, threads, etc.
        """
        pass

    # ------------------------------------------------------------------
    # GUI integration (only called when running with --gui)
    # ------------------------------------------------------------------

    def on_ui_setup(self, main_window):
        """
        Called after the PyQt6 main window is built.
        Add sidebar pages, inject widgets, connect signals, etc.
        Not called in headless/CLI mode.
        """
        pass

    # ------------------------------------------------------------------
    # Download hook (called in both GUI and CLI mode)
    # ------------------------------------------------------------------

    def on_item_downloaded(self, item_data, file_path):
        """
        Called every time a media file is saved to disk.

        item_data  — ofscraper Media object. Key properties:
            .id           int     Media ID
            .post_id      int     Parent post ID
            .username     str     Creator username
            .mediatype    str     "Images" | "Videos" | "Audios" | "Forced_skipped"
            .responsetype str     "Timeline" | "Archived" | "Stories" | "Highlights" | "Messages" | "Profile"
            .url          str|None  Download URL (None for DRM content)
            .filename     str|None  Base filename
            .text         str     Post caption
            .date         str     Media creation date (ISO)
            .downloadtype str     "Normal" | "Protected"

        file_path  — absolute path string of the saved file on disk.
        """
        self.log.debug(
            "Downloaded %s from @%s: %s",
            item_data.mediatype,
            item_data.username,
            file_path,
        )

    # ------------------------------------------------------------------
    # Reserved hooks (defined but not yet dispatched)
    # ------------------------------------------------------------------

    def on_scrape_start(self, config, models):
        """
        Reserved — not yet dispatched.
        Will be called before the download queue begins.
        Must return the models list (possibly modified).
        """
        return models

    def on_scrape_complete(self, stats):
        """
        Reserved — not yet dispatched.
        Will be called when a scraping session finishes completely.
        """
        pass
```
