---
name: Bug report
about: Report an issue with running the script
title: "# Clear Description of issue"
labels: ''
assignees: ''

---

---
name: Bug report
about: Report an issue with the OF-Scraper 3.12.9 GUI patch
title: "[BUG] Clear description of the issue"
labels: "bug"
assignees: ""
---

<!--
This issue tracker is for bugs in the OF-Scraper 3.12.9 GUI patch only.

For bugs in the base ofscraper CLI/TUI, please report upstream:
  https://github.com/datawhores/OF-Scraper/issues

For quick questions, you may use Discord instead.

BEFORE opening an issue:
  - Confirm you are running ofscraper 3.12.9 (run `ofscraper --version`)
  - Confirm the GUI patch was applied successfully (re-run `python patch_ofscraper_3.12.9_gui.py --dry-run` to check)
  - Search existing issues to see if this has already been reported
  - Issues will be closed if this template is not filled out completely
-->

## Describe the bug

A clear and concise description of what the bug is. Include any error messages shown on screen or in the GUI console.

## GUI Mode

Which GUI mode were you using when the bug occurred?

- [ ] GUI scraper (`ofscraper --gui`, scraping content)
- [ ] GUI daemon mode (scheduled/repeated scrapes)
- [ ] GUI settings / config editor
- [ ] GUI auth editor
- [ ] Other (describe below)

## To Reproduce

Steps to reproduce the behavior.

**Steps:**
1.
2.
3.

## Expected behavior

What did you expect to happen?

## Actual behavior

What actually happened?

## Screenshots / Logs

Logs are **required** for all bug reports.

- Set log level to debug: open **Settings** in the GUI and set Log Level to `debug`, then reproduce the issue
- Copy the log from the **Console** tab in the GUI, or from the log file on disk
- Use a paste site to keep the issue readable: [PrivateBin](https://privatebin.io/) or [Pastebin](https://pastebin.com/)

<details>
<summary>Log output (click to expand)</summary>

```
paste log here
```

</details>

## Config

Paste your `config.json` below. **Anonymize** before posting:
- Replace your home directory path with `~` or `<home>`

<details>
<summary>config.json (click to expand)</summary>

```json
paste config here
```

</details>

## Installation Info

- **ofscraper Install method:**
  - [ ] pip + GUI patch
  - [ ] pipx + GUI patch
  - [ ] uv + GUI patch

- **ofscraper version:** 3.12.9 <!-- confirm with `ofscraper --version` — issues for other versions will be closed -->
- **Patch script version:** <!-- first line of `patch_ofscraper_3.12.9_gui.py`, e.g. `# Patch ID: abc1234` -->
- **PyQt6 version:** <!-- run `python -c "import PyQt6; print(PyQt6.QtCore.PYQT_VERSION_STR)"` -->

## System Info

- **OS:** <!-- e.g. Windows 11 23H2, Ubuntu 22.04, Linux Mint 22.3 etc.  -->
- **Python version:** <!-- run `python --version` -->
- **Architecture:** <!-- e.g. x86_64, arm64 -->

## Additional context

Any other context that might help: specific models, content types, network setup (VPN/proxy), etc.
