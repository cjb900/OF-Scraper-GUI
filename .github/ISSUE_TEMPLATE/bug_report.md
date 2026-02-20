---
name: Bug report
about: Report an issue with running the script
title: "# Clear Description of issue"
labels: ''
assignees: ''

---

---
name: Bug report
about: Report an issue with running OF-Scraper
title: "[BUG] Clear description of the issue"
labels: "bug"
assignees: ""
---

<!--
Issues will be closed if this template is not filled out completely.

For private reports or quick questions, you may use Discord instead.

BEFORE opening an issue:
  - Check that you are on the latest version of OF-Scraper
  - If using the GUI patch, make sure the patch was applied successfully (run with --dry-run first)
  - Search existing issues to see if this has already been reported
-->

## Describe the bug

A clear and concise description of what the bug is. Include any error messages shown on screen or in the log.

## Mode

Which mode were you running in?

- [ ] GUI (`ofscraper --gui`)
- [ ] CLI / Interactive (terminal prompts)
- [ ] CLI / Action mode (command-line flags, e.g. `ofscraper post -u username`)
- [ ] Daemon mode

## To Reproduce

Steps to reproduce the behavior. Include the exact command and arguments you ran.

**Command used:**
```
ofscraper <paste command here>
```

**Steps:**
1.
2.
3.

## Expected behavior

What did you expect to happen?

## Actual behavior

What actually happened? Paste the relevant portion of the log or error here.

## Screenshots / Logs

Logs are **required** for all bug reports (except pure setup/install issues).

- Logs must be at **least debug level** (`--log-level debug` on CLI, or set `log_level: "debug"` in config)
- GUI users: copy from the **Console** tab inside the GUI, or from the log file
- Use a paste site to keep the issue readable: [PrivateBin](https://privatebin.io/) or [Pastebin](https://pastebin.com/)

<details>
<summary>Log output (click to expand)</summary>

```
paste log here
```

</details>

## Config

Paste your `config.json` below. **Anonymize** any personal information before posting:
- Replace your home directory path with `~` or `<home>`
- Remove or mask your `key_db_path`, API keys, or auth tokens

<details>
<summary>config.json (click to expand)</summary>

```json
paste config here
```

</details>

## Installation Info

- **Install method:**
  - [ ] pip (`pip install ofscraper`)
  - [ ] pip + GUI patch (`patch_ofscraper_3.12.9_gui.py`)
  - [ ] pipx
  - [ ] pipx + GUI patch
  - [ ] Binary / standalone executable
  - [ ] Source / git clone

- **OF-Scraper version:** <!-- run `ofscraper --version` -->
- **GUI patch applied:** yes / no / N/A

## System Info

- **OS:** <!-- e.g. Windows 11, macOS 14.3, Ubuntu 22.04 -->
- **Python version:** <!-- run `python --version` -->
- **PyQt6 version (GUI users):** <!-- run `python -c "import PyQt6; print(PyQt6.QtCore.PYQT_VERSION_STR)"` -->
- **Architecture:** <!-- e.g. x86_64, arm64 -->

## Additional context

Any other context that might help: accounts being scraped (content type, subscription status), specific models or post types, network setup (VPN, proxy), etc.
