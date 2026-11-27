"""What the MCP server can do in the GUI: see its windows and controls, read
tables and text, click, type, tick, choose, go to a page, take a screenshot.

Everything here runs on the Qt main thread (bridge.py). Controls are named
by a handle ("c12") from list_controls, or by their text. Actions are queued
(QTimer.singleShot) rather than done inside the call: a click that opens a
modal dialog would otherwise hold the call until the dialog closed.
"""

from __future__ import annotations

import base64
import re

from PyQt6 import sip
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTabBar,
    QTableView,
    QTableWidget,
    QTextEdit,
    QWidget,
)

# Like / Unlike act on the logged-in account
_ACCOUNT_ACTION = re.compile(r"\b(un)?like(s|d)?\b", re.IGNORECASE)
_KINDS = {
    "button": (QAbstractButton,),
    "input": (QLineEdit, QAbstractSpinBox, QComboBox, QSlider),
    "table": (QTableView,),
    "text": (QPlainTextEdit, QTextEdit),
    "list": (QListWidget,),
    "tabs": (QTabBar,),
    "label": (QLabel,),
}
MAX_TEXT = 200


class ToolError(Exception):
    """A tool couldn't do what was asked; the message says why."""


def _alive(w) -> bool:
    try:
        return w is not None and not sip.isdeleted(w)
    except Exception:
        return False


def _short(text, limit=MAX_TEXT) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# login territory: the Authentication pages and the login / cookie windows
_SECRET_AREA = re.compile(r"Auth|Login|Cookie")
# a field named or labelled as holding a secret
_SECRET_NAME = re.compile(
    r"token|cookie|\bsess\b|session|password|passwd|secret|webhook|bearer|"
    r"x-bc|api.?key|private.?key|client.?id|auth",
    re.IGNORECASE,
)
_TEXT_FIELDS = (QLineEdit, QPlainTextEdit, QTextEdit)


def _form_label(w) -> str:
    """The text of the label a form layout shows beside this field."""
    from PyQt6.QtWidgets import QFormLayout

    parent = w.parentWidget()
    while parent is not None:
        layout = parent.layout()
        if isinstance(layout, QFormLayout):
            label = layout.labelForField(w)
            if label is not None and hasattr(label, "text"):
                return label.text()
        parent = parent.parentWidget()
    return ""


def is_secret(w) -> bool:
    """A text field whose contents must not leave the GUI: anything on the
    Authentication pages or in a login or cookie window, and any field named,
    labelled or described as a token, cookie, password, webhook or key."""
    if not isinstance(w, _TEXT_FIELDS):
        return False
    if isinstance(w, QLineEdit) and w.echoMode() != QLineEdit.EchoMode.Normal:
        return True
    node = w
    while node is not None:
        if _SECRET_AREA.search(type(node).__name__):
            return True
        node = node.parentWidget()
    hints = " ".join(
        str(x or "")
        for x in (
            w.objectName(),
            w.toolTip(),
            w.accessibleName(),
            getattr(w, "placeholderText", lambda: "")(),
            _form_label(w),
        )
    )
    return bool(_SECRET_NAME.search(hints))


def _masked(text) -> str:
    return f"set ({len(text)} characters)" if text else "empty"


def _kind(w) -> str | None:
    for name, classes in _KINDS.items():
        if isinstance(w, classes):
            return name
    return None


def _label(w) -> str:
    """What a person would read on the control (a secret only as "set (N
    characters)": see is_secret)."""
    if is_secret(w):
        return _masked(w.text() if isinstance(w, QLineEdit) else w.toPlainText())
    if isinstance(w, QAbstractButton):
        return w.text().replace("&", "")
    if isinstance(w, QLineEdit):
        return w.text()
    if isinstance(w, QComboBox):
        return w.currentText()
    if isinstance(w, QAbstractSpinBox):
        return w.text()
    if isinstance(w, QLabel):
        return w.text()
    if isinstance(w, QTabBar):
        return " | ".join(w.tabText(i).replace("&", "") for i in range(w.count()))
    if isinstance(w, QPlainTextEdit):
        return w.toPlainText()[-MAX_TEXT:]
    if isinstance(w, QTextEdit):
        return w.toPlainText()[-MAX_TEXT:]
    if isinstance(w, QSlider):
        return str(w.value())
    return ""


def _window_title(w) -> str:
    top = w.window()
    return top.windowTitle() or type(top).__name__


class GuiTools:
    def __init__(self, window, settings_getter):
        self.window = window
        self._settings = settings_getter
        self._by_handle = {}
        self._handle_of = {}
        self._next = 1

    # --- handles ----------------------------------------------------------------

    def _handle(self, w) -> str:
        key = id(w)
        handle = self._handle_of.get(key)
        if handle is None or self._by_handle.get(handle) is not w:
            handle = f"c{self._next}"
            self._next += 1
            self._handle_of[key] = handle
            self._by_handle[handle] = w
        return handle

    def _windows(self):
        """The visible top-level windows, the active modal one first."""
        found = []
        modal = QApplication.activeModalWidget()
        if _alive(modal) and modal.isVisible():
            found.append(modal)
        for w in QApplication.topLevelWidgets():
            if _alive(w) and w.isVisible() and w not in found and isinstance(
                w, (QMainWindow, QDialog, QMessageBox)
            ):
                found.append(w)
        if _alive(self.window) and self.window not in found:
            found.append(self.window)
        return found

    def _controls(self, kinds=None):
        for top in self._windows():
            for w in [top, *top.findChildren(QWidget)]:
                if not _alive(w) or not w.isVisible():
                    continue
                kind = _kind(w)
                if kind is None or (kinds and kind not in kinds):
                    continue
                # a QLineEdit inside a spin box or combo box is part of it
                if isinstance(w, QLineEdit) and isinstance(w.parent(), (QAbstractSpinBox, QComboBox)):
                    continue
                if kind == "label" and not w.text().strip():
                    continue
                yield w, kind

    def _find(self, control: str):
        """A control by handle, else by its text (exact, then contained)."""
        control = str(control or "").strip()
        if not control:
            raise ToolError("no control given")
        w = self._by_handle.get(control)
        if w is not None:
            if not _alive(w) or not w.isVisible():
                raise ToolError(f"{control} is no longer on screen; list the controls again")
            return w
        wanted = control.lower()
        exact, partial = [], []
        for w, kind in self._controls():
            text = _short(_label(w), 500).lower()
            if text == wanted:
                exact.append(w)
            elif wanted in text and kind != "label":
                partial.append(w)
        matches = exact or partial
        # a button beats the label beside it
        if len(matches) > 1:
            buttons = [w for w in matches if isinstance(w, QAbstractButton)]
            matches = buttons or matches
        if not matches:
            raise ToolError(f"no visible control matches {control!r}; use list_controls")
        if len(matches) > 1:
            shown = ", ".join(f"{self._handle(w)} {type(w).__name__} {_short(_label(w), 40)!r}" for w in matches[:8])
            raise ToolError(f"{control!r} matches {len(matches)} controls: {shown}. Use a handle.")
        return matches[0]

    def _guard_account_action(self, w, extra_text=""):
        if self._settings().get("account_actions"):
            return
        # the control's own text: a tooltip can say "like" in plain English
        text = f"{_label(w)} {extra_text}"
        if _ACCOUNT_ACTION.search(text):
            raise ToolError(
                "Like / Unlike act on the account and are turned off for test control. "
                "Allow them in the Developer panel to use them."
            )

    def _describe(self, w, kind):
        item = {
            "handle": self._handle(w),
            "kind": kind,
            "type": type(w).__name__,
            "text": _short(_label(w)),
            "window": _short(_window_title(w), 60),
        }
        if w.objectName():
            item["name"] = w.objectName()
        if is_secret(w):
            item["secret"] = True
        if not w.isEnabled():
            item["enabled"] = False
        if isinstance(w, QAbstractButton) and w.isCheckable():
            item["checked"] = w.isChecked()
        if isinstance(w, QComboBox):
            item["options"] = [w.itemText(i) for i in range(min(w.count(), 30))]
        if isinstance(w, QTabBar):
            item["current"] = w.tabText(w.currentIndex()).replace("&", "")
        if isinstance(w, QTableView) and w.model() is not None:
            item["rows"] = w.model().rowCount()
        tip = w.toolTip()
        if tip:
            item["tooltip"] = _short(tip, 120)
        return item

    # --- seeing -------------------------------------------------------------------

    def status(self):
        win = self.window
        out = {}
        try:
            from ofscraper.gui.patch_version import PATCH_ID

            out["patch"] = PATCH_ID
        except Exception:
            pass
        try:
            from ofscraper.gui import site_context

            out["site"] = site_context.current_site()
        except Exception:
            pass
        pages = getattr(win, "_pages", {}) or {}
        current = win.stack.currentWidget() if hasattr(win, "stack") else None
        out["page"] = next((pid for pid, p in pages.items() if p is current), None)
        out["pages"] = list(pages)
        bar = getattr(win, "status_bar", None)
        if bar is not None:
            out["status_bar"] = bar.currentMessage()
        try:
            from ofscraper.gui.utils import crash_diagnostics as cd

            out["scraping"] = cd.is_scrape_active()
            out["loading_models"] = cd.is_model_fetch_active()
        except Exception:
            pass
        out["windows"] = [_short(_window_title(w), 60) for w in self._windows()]
        modal = QApplication.activeModalWidget()
        if _alive(modal):
            out["modal_dialog"] = _short(modal.windowTitle() or type(modal).__name__, 60)
        return out

    def list_controls(self, kinds=None, text=None, limit=150):
        kinds = [k for k in (kinds or []) if k in _KINDS] or None
        wanted = str(text or "").lower()
        items = []
        for w, kind in self._controls(kinds):
            if wanted and wanted not in _label(w).lower() and wanted not in w.toolTip().lower():
                continue
            items.append(self._describe(w, kind))
            if len(items) >= limit:
                break
        return {"count": len(items), "controls": items}

    def read(self, control, offset=0, max_rows=50):
        w = self._find(control)
        if isinstance(w, QTableView):
            model = w.model()
            if model is None:
                return {"rows": []}
            cols = model.columnCount()
            headers = [str(model.headerData(c, Qt.Orientation.Horizontal) or "") for c in range(cols)]
            shown = [c for c in range(cols) if not w.isColumnHidden(c)]
            rows, skipped = [], 0
            for r in range(model.rowCount()):
                if w.isRowHidden(r):  # left out by the table's filters
                    continue
                if skipped < offset:
                    skipped += 1
                    continue
                rows.append({headers[c] or str(c): _short(model.index(r, c).data() or "", 120) for c in shown})
                if len(rows) >= max_rows:
                    break
            visible = sum(1 for r in range(model.rowCount()) if not w.isRowHidden(r))
            return {"total_rows": model.rowCount(), "visible_rows": visible, "offset": offset, "rows": rows}
        if isinstance(w, (QPlainTextEdit, QTextEdit)):
            if is_secret(w):
                return {"secret": True, "text": _label(w)}
            lines = w.toPlainText().splitlines()
            return {"lines": len(lines), "text": "\n".join(lines[-max(1, int(max_rows)):])}
        if isinstance(w, QListWidget):
            return {"items": [w.item(i).text() for i in range(w.count())]}
        return self._describe(w, _kind(w) or type(w).__name__)

    def read_log(self, lines=60):
        from ofscraper.gui.widgets.console_log import ConsoleLogWidget

        for top in self._windows():
            for log_widget in top.findChildren(ConsoleLogWidget):
                if _alive(log_widget) and log_widget.isVisible():
                    text = log_widget.text_edit.toPlainText().splitlines()
                    return {"text": "\n".join(text[-max(1, int(lines)):])}
        raise ToolError("no log panel is on screen (it shows on the Scraper page)")

    def page_text(self, needle):
        """Whether text is on screen in any visible control or window title."""
        needle = str(needle).lower()
        for top in self._windows():
            if needle in (top.windowTitle() or "").lower():
                return True
        for w, _kind_name in self._controls():
            if needle in _label(w).lower():
                return True
            if isinstance(w, QTableView) and w.model() is not None:
                model = w.model()
                for r in range(min(model.rowCount(), 500)):
                    if w.isRowHidden(r):
                        continue
                    for c in range(model.columnCount()):
                        if needle in str(model.index(r, c).data() or "").lower():
                            return True
        return False

    def screenshot(self, window=None, max_width=1600):
        if not self._settings().get("screenshots"):
            raise ToolError(
                "Screenshots are turned off. A screenshot leaves the computer with whatever "
                "the window shows; turn them on in the Developer panel to use this."
            )
        target = None
        if window:
            for w in self._windows():
                if str(window).lower() in (w.windowTitle() or type(w).__name__).lower():
                    target = w
                    break
            if target is None:
                raise ToolError(f"no open window is called {window!r}")
        else:
            target = self._windows()[0]
        reason = self._secret_on_screen(target)
        if reason:
            raise ToolError(f"No screenshot: {reason}. Use list_controls or read instead.")
        pixmap = target.grab()
        if pixmap.width() > max_width:
            pixmap = pixmap.scaledToWidth(int(max_width), Qt.TransformationMode.SmoothTransformation)
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        buf.close()
        return {
            "image": base64.b64encode(bytes(data)).decode("ascii"),
            "title": _window_title(target),
            "size": f"{pixmap.width()}x{pixmap.height()}",
        }

    def _secret_on_screen(self, top):
        """Why a screenshot of this window would show a secret, or ""."""
        pages = getattr(self.window, "_pages", {}) or {}
        if top is self.window and hasattr(self.window, "stack"):
            if self.window.stack.currentWidget() is pages.get("auth"):
                return "the Authentication page is open"
        if _SECRET_AREA.search(type(top).__name__):
            return "this is a login window"
        for w in top.findChildren(QWidget):
            if not (_alive(w) and w.isVisible() and isinstance(w, _TEXT_FIELDS) and is_secret(w)):
                continue
            if isinstance(w, QLineEdit) and w.echoMode() != QLineEdit.EchoMode.Normal:
                continue  # shown as dots
            text = w.text() if isinstance(w, QLineEdit) else w.toPlainText()
            if text:
                return "a token, cookie, password or webhook is shown in plain text"
        return ""

    # --- acting (queued; see the module docstring) -------------------------------

    @staticmethod
    def _later(fn):
        QTimer.singleShot(0, fn)

    def click(self, control):
        w = self._find(control)
        if not w.isEnabled():
            raise ToolError(f"{self._handle(w)} {_short(_label(w), 60)!r} is disabled")
        if isinstance(w, QAbstractButton):
            self._guard_account_action(w)
            self._later(w.click)
            return f"clicked {self._handle(w)} {_short(_label(w), 60)!r}"
        raise ToolError(f"{type(w).__name__} isn't a button; use select, set_text or set_checked")

    def set_checked(self, control, checked=True):
        w = self._find(control)
        if not (isinstance(w, QAbstractButton) and w.isCheckable()):
            raise ToolError(f"{type(w).__name__} {_short(_label(w), 60)!r} can't be ticked")
        if not w.isEnabled():
            raise ToolError(f"{_short(_label(w), 60)!r} is disabled")
        checked = bool(checked)
        if checked:
            self._guard_account_action(w)
        if w.isChecked() != checked:
            # click(), not setChecked(): runs the control's handlers as a person would
            if isinstance(w, QRadioButton) and not checked:
                raise ToolError("a radio button is cleared by choosing another one")
            self._later(w.click)
        return f"{'ticked' if checked else 'unticked'} {_short(_label(w), 60)!r}"

    def set_text(self, control, text):
        w = self._find(control)
        if not w.isEnabled():
            raise ToolError(f"{self._handle(w)} is disabled")
        text = "" if text is None else str(text)
        if isinstance(w, QLineEdit):
            def go():
                w.setFocus()
                w.setText(text)
                w.editingFinished.emit()
            self._later(go)
        elif isinstance(w, QPlainTextEdit):
            self._later(lambda: w.setPlainText(text))
        elif isinstance(w, QTextEdit):
            self._later(lambda: w.setPlainText(text))
        elif isinstance(w, (QSpinBox, QSlider)):
            self._later(lambda: w.setValue(int(float(text))))
        elif isinstance(w, QDoubleSpinBox):
            self._later(lambda: w.setValue(float(text)))
        elif isinstance(w, QDateEdit):
            from PyQt6.QtCore import QDate

            date = QDate.fromString(text, "yyyy-MM-dd")
            if not date.isValid():
                raise ToolError("a date is written YYYY-MM-DD")
            self._later(lambda: w.setDate(date))
        elif isinstance(w, QComboBox) and w.isEditable():
            self._later(lambda: w.setCurrentText(text))
        else:
            raise ToolError(f"{type(w).__name__} doesn't take text")
        # the value itself isn't repeated: it can be a password or a cookie
        return f"set the text of {self._handle(w)} ({len(text)} characters)"

    def select(self, control, option):
        w = self._find(control)
        option_l = str(option).lower()
        if isinstance(w, QComboBox):
            texts = [w.itemText(i) for i in range(w.count())]
            idx = next((i for i, t in enumerate(texts) if t.lower() == option_l), None)
            if idx is None:
                idx = next((i for i, t in enumerate(texts) if option_l in t.lower()), None)
            if idx is None:
                raise ToolError(f"{option!r} isn't one of: {', '.join(texts[:30])}")
            self._guard_account_action(w, texts[idx])
            self._later(lambda: w.setCurrentIndex(idx))
            return f"chose {texts[idx]!r}"
        if isinstance(w, QTabBar):
            texts = [w.tabText(i).replace("&", "") for i in range(w.count())]
            idx = next((i for i, t in enumerate(texts) if option_l in t.lower()), None)
            if idx is None:
                raise ToolError(f"{option!r} isn't one of the tabs: {', '.join(texts)}")
            self._later(lambda: w.setCurrentIndex(idx))
            return f"opened the {texts[idx]!r} tab"
        if isinstance(w, QListWidget):
            for i in range(w.count()):
                if option_l in w.item(i).text().lower():
                    self._later(lambda i=i: w.setCurrentRow(i))
                    return f"chose {w.item(i).text()!r}"
            raise ToolError(f"{option!r} isn't in the list")
        if isinstance(w, QTableWidget):
            try:
                row = int(option)
            except (TypeError, ValueError):
                raise ToolError("for a table, give the row number (from 0, as read returns them)")
            self._later(lambda: w.selectRow(row))
            return f"selected row {row}"
        raise ToolError(f"{type(w).__name__} has nothing to choose from")

    def navigate(self, page):
        pages = getattr(self.window, "_pages", {}) or {}
        page = str(page).lower().strip()
        if page not in pages:
            raise ToolError(f"no page {page!r}; pages: {', '.join(pages)}")
        self._later(lambda: self.window._navigate(page))
        return f"went to the {page} page"

    def press_key(self, key, control=None):
        from PyQt6.QtGui import QKeySequence
        from PyQt6.QtTest import QTest

        seq = QKeySequence(str(key))
        if seq.isEmpty():
            raise ToolError(f"unknown key {key!r} (e.g. Return, Escape, Ctrl+A)")
        combo = seq[0]
        target = self._find(control) if control else (QApplication.focusWidget() or self._windows()[0])
        self._later(lambda: QTest.keyClick(target, combo.key(), combo.keyboardModifiers()))
        return f"pressed {key}"


# --- MCP descriptions ---------------------------------------------------------------

_CONTROL = {"type": "string", "description": "A handle from list_controls (e.g. \"c12\"), or the control's visible text"}

TOOL_SPECS = [
    {
        "name": "gui_status",
        "description": "The GUI's state: site, patch, current page and the pages there are, status bar text, whether a scrape or model load is running, open windows and any modal dialog.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_controls",
        "description": "The visible controls in the GUI's windows (a modal dialog first): handle, kind, text, enabled/checked state, combo options, table row counts. Filter by kind (button, input, table, text, list, tabs, label) or by text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kinds": {"type": "array", "items": {"type": "string", "enum": list(_KINDS)}},
                "text": {"type": "string", "description": "Only controls whose text or tooltip contains this"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 150},
            },
        },
    },
    {
        "name": "read",
        "description": "Read a control: a table's visible rows (as the filters leave them), a text box's last lines, a list's items, or any other control's state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control": _CONTROL,
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "max_rows": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
            },
            "required": ["control"],
        },
    },
    {
        "name": "read_log",
        "description": "The last lines of the Scraper page's log panel.",
        "inputSchema": {"type": "object", "properties": {"lines": {"type": "integer", "minimum": 1, "maximum": 2000, "default": 60}}},
    },
    {
        "name": "click",
        "description": "Click a button, checkbox or nav entry. Queued: check the result with gui_status, list_controls or wait_for.",
        "inputSchema": {"type": "object", "properties": {"control": _CONTROL}, "required": ["control"]},
    },
    {
        "name": "set_checked",
        "description": "Tick or untick a checkbox (or choose a radio button), as a click would.",
        "inputSchema": {
            "type": "object",
            "properties": {"control": _CONTROL, "checked": {"type": "boolean", "default": True}},
            "required": ["control"],
        },
    },
    {
        "name": "set_text",
        "description": "Type into a text field, number box or date (YYYY-MM-DD). The value isn't logged.",
        "inputSchema": {
            "type": "object",
            "properties": {"control": _CONTROL, "text": {"type": "string"}},
            "required": ["control", "text"],
        },
    },
    {
        "name": "select",
        "description": "Choose an option in a drop-down, a tab in a tab bar, an item in a list, or a row (number) in a table.",
        "inputSchema": {
            "type": "object",
            "properties": {"control": _CONTROL, "option": {"type": "string"}},
            "required": ["control", "option"],
        },
    },
    {
        "name": "navigate",
        "description": "Go to a sidebar page by its id (gui_status lists them: scraper, auth, config, drm, profiles, merge, plugins, help).",
        "inputSchema": {"type": "object", "properties": {"page": {"type": "string"}}, "required": ["page"]},
    },
    {
        "name": "press_key",
        "description": "Press a key (Return, Escape, Tab, Ctrl+A, ...) in a control, or in the focused one.",
        "inputSchema": {
            "type": "object",
            "properties": {"key": {"type": "string"}, "control": _CONTROL},
            "required": ["key"],
        },
    },
    {
        "name": "wait_for",
        "description": "Wait until text is on screen, or gone, or the GUI is idle (no scrape or model load), up to timeout seconds. Returns how it ended.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Wait until this text is visible"},
                "gone": {"type": "string", "description": "Wait until this text is no longer visible"},
                "idle": {"type": "boolean", "description": "Wait until no scrape or model load runs"},
                "timeout": {"type": "number", "minimum": 0.5, "maximum": 1800, "default": 30},
            },
        },
    },
    {
        "name": "screenshot",
        "description": "A PNG of a window (the modal dialog, else the main window; or one named by title). Only when screenshots are turned on in the Developer panel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "description": "Part of the window's title"},
                "max_width": {"type": "integer", "minimum": 320, "maximum": 3840, "default": 1600},
            },
        },
    },
]
