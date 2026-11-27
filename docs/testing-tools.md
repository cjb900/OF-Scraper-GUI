[🏠 README](../README.md) · [Install](install.md) · [GUI guide](gui-guide.md) · [Docker](docker.md) · [PostgreSQL](postgresql.md) · [Plugins](plugins.md) · [Versions](versions.md) · [Troubleshooting](troubleshooting.md)

---

# Testing tools (developer install)

For testing the GUI. A normal install doesn't have any of this.

## Installing them

Run the patch with `--testing`:

```bash
python patch_ofscraper_3.18.1_gui.py --testing
```

This adds the developer tools on top of the normal patch: a **Test control** button in the sidebar (above the version button) and the test control server. Nothing extra is installed from the internet: the server uses only Python's standard library.

- **Update now** keeps them: it runs the next patch with `--testing` again.
- Running the patch **without** `--testing` removes them (a copy goes in that run's backup folder).

## Test control (MCP)

Test control is an [MCP](https://modelcontextprotocol.io) server that lets a client such as Claude Code see and use the GUI window: read its controls, tables and log, click, type, tick, choose, change page, and wait for something to show.

It's **off** until you turn it on:

1. Click **Test control: off** in the sidebar.
2. Tick **Allow test control while the GUI runs** and click **Save**.
3. Copy the command under **Add it to Claude Code** and run it once in a terminal, e.g.
   ```bash
   claude mcp add --transport http ofscraper-gui-onlyfans http://127.0.0.1:8765/mcp --header "Authorization: Bearer <token>"
   ```

The sidebar button then shows **Test control: on**, and **connected** while a client is using it. Every request is written to the log (the tool and which arguments, never typed text).

Each site's window has its own server: OnlyFans on port **8765**, Fansly on **8766** (both can be changed in the panel).

### What a client can and can't do

| | |
|---|---|
| Where it listens | `127.0.0.1` only: other computers can't connect |
| Access | the panel's token (`Authorization: Bearer …`); **New token** stops old clients |
| Web pages | refused (a request with a non-local `Origin`), so a site open in a browser can't use it |
| Screenshots | **off** until **Allow screenshots** is ticked. A screenshot is sent to the client, and from there to its AI service, with whatever the window shows. Privacy mode hides names in the window, not in pictures |
| Like / Unlike | refused until **Allow Like / Unlike** is ticked: they act on your account |
| Typed text | never logged (it can be a password or a cookie) |

### Tools

| Tool | Does |
|---|---|
| `gui_status` | site, patch, current page and the page ids, status bar, whether a scrape or model load runs, open windows and dialogs |
| `list_controls` | the visible controls (a modal dialog first) with a handle (`c12`), text and state; filter by kind or text |
| `read` | a table's visible rows, a text box's last lines, a list's items, any control's state |
| `read_log` | the Scraper page's log panel |
| `click`, `set_checked`, `set_text`, `select`, `press_key` | use a control, by handle or by its text |
| `navigate` | open a sidebar page by id (`scraper`, `auth`, `config`, `merge`, ...) |
| `wait_for` | wait until text shows, goes, or the GUI is idle |
| `screenshot` | a PNG of the window or a dialog (when allowed) |

Actions are queued in the GUI and the call returns at once, so a click that opens a dialog doesn't hold it: check the result with `list_controls`, `read` or `wait_for`.
