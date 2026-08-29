"""GUI/CLI-facing config validation (SubScraper ConfigValidationService-style).

Checks filename uniqueness tokens and that path templates stay under the
save root before config save or scrape start.
"""
from __future__ import annotations

import logging
import os
import pathlib
import string
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

log = logging.getLogger("shared")

# Placeholders that make filenames unique across media in a post (see placeholder._needs_count).
_UNIQUE_FILE_TOKENS = frozenset(
    {
        "filename",
        "file_name",
        "only_file_name",
        "onlyfilename",
        "only_filename",
        "original_filename",
        "originalfilename",
        "media_id",
        "mediaid",
    }
)

_UNIQUE_TOKEN_HELP = (
    "File Format must include a uniqueness token such as {filename}, {media_id}, "
    "or {original_filename} to avoid overwriting files from the same post."
)

# Sample values for probing path templates without touching the filesystem for media.
_SAMPLE_VARS: dict[str, Any] = {
    "config_path": "C:/ofscraper_config" if os.name == "nt" else "/tmp/ofscraper_config",
    "configpath": "C:/ofscraper_config" if os.name == "nt" else "/tmp/ofscraper_config",
    "profile": "main_profile",
    "site_name": "Onlyfans",
    "save_location": "C:/Downloads/OF" if os.name == "nt" else "/tmp/Downloads/OF",
    "my_id": "1",
    "my_username": "me",
    "root": "C:/Downloads/OF" if os.name == "nt" else "/tmp/Downloads/OF",
    "username": "creator",
    "user_name": "creator",
    "model_username": "creator",
    "model_id": "1001",
    "first_letter": "C",
    "responsetype": "Posts",
    "response_type": "Posts",
    "mediatype": "Videos",
    "media_type": "Videos",
    "post_id": "2002",
    "media_id": "3003",
    "mediaid": "3003",
    "value": "Free",
    "date": "2026-01-01",
    "label": "none",
    "download_type": "protected",
    "quality": "source",
    "file_name": "sample_source",
    "filename": "sample_source",
    "original_filename": "sample",
    "originalfilename": "sample",
    "only_file_name": "sample",
    "onlyfilename": "sample",
    "only_filename": "sample",
    "text": "hello",
    "ext": "mp4",
    "number": "1",
    "id": "2002",
}


class _SafeFormatMap(dict):
    """format_map helper that leaves unknown placeholders intact."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@dataclass
class ValidationIssue:
    field: str
    message: str


@dataclass
class ValidationResult:
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    def format_errors(self) -> str:
        return "\n".join(f"• {i.field}: {i.message}" for i in self.errors)

    def format_warnings(self) -> str:
        return "\n".join(f"• {i.field}: {i.message}" for i in self.warnings)


def _nested_get(config: Mapping[str, Any], section: str, key: str, default="") -> Any:
    if key in config and config.get(key) not in (None, ""):
        return config.get(key)
    section_data = config.get(section) or {}
    if isinstance(section_data, Mapping):
        return section_data.get(key, default)
    return default


def _placeholder_names(template: str) -> set[str]:
    names: set[str] = set()
    if not template:
        return names
    try:
        from ofscraper.utils.string import parse_safe

        raw = parse_safe(template)
        names = {n for n in raw if n}
    except Exception:
        for _, name, _, _ in string.Formatter().parse(template):
            if name:
                names.add(name)
    return names


def file_format_has_unique_token(file_format: str) -> bool:
    names = {n.lower() for n in _placeholder_names(file_format or "")}
    # Also accept literal SubScraper-style {mediaId} casing via parse names.
    return bool(names & {t.lower() for t in _UNIQUE_FILE_TOKENS})


def _format_template(template: str, extra: Optional[Mapping[str, Any]] = None) -> str:
    vars_map = dict(_SAMPLE_VARS)
    if extra:
        vars_map.update(extra)
    try:
        return (template or "").format_map(_SafeFormatMap(vars_map))
    except Exception as e:
        raise ValueError(f"Invalid template syntax: {e}") from e


def _template_escapes_root(template: str, root: pathlib.Path) -> Optional[str]:
    """Return an error message if template can escape save root; else None."""
    text = (template or "").strip()
    if not text:
        return None
    try:
        formatted = _format_template(text)
    except ValueError as e:
        return str(e)

    probe = pathlib.Path(formatted)
    if probe.is_absolute():
        return (
            "Resolves to an absolute path. Use a path relative to Save Location "
            "(do not start with a drive letter or /)."
        )

    # Mirror placeholder.getmediadir join + normpath behavior.
    joined = pathlib.Path(os.path.normpath(f"{str(root)}/{str(probe)}"))
    try:
        root_res = root.expanduser().resolve(strict=False)
        joined_res = joined.expanduser().resolve(strict=False)
        joined_res.relative_to(root_res)
    except ValueError:
        return (
            "Escapes Save Location after normalization (often caused by '..' segments). "
            "Keep the template under the save root."
        )
    except OSError:
        if ".." in pathlib.PurePath(os.path.normpath(str(probe))).parts:
            return "Contains '..' path segments that can escape Save Location."
    return None


def validate_config(config: Optional[Mapping[str, Any]] = None) -> ValidationResult:
    """Validate file/path-related config. Loads disk config when ``config`` is None."""
    result = ValidationResult()
    try:
        if config is None:
            import ofscraper.utils.config.file as config_file

            config = config_file.open_config() or {}
    except Exception as e:
        result.errors.append(
            ValidationIssue("config", f"Could not read configuration: {e}")
        )
        return result

    cfg: Mapping[str, Any] = config or {}
    file_opts = cfg.get("file_options") if isinstance(cfg.get("file_options"), Mapping) else {}
    file_opts = file_opts or {}

    save_location = str(
        _nested_get(cfg, "file_options", "save_location", "") or ""
    ).strip()
    dir_format = str(_nested_get(cfg, "file_options", "dir_format", "") or "").strip()
    file_format = str(_nested_get(cfg, "file_options", "file_format", "") or "").strip()
    metadata = str(cfg.get("metadata") or "").strip()

    if not save_location:
        result.errors.append(
            ValidationIssue("Save Location", "Save Location is required.")
        )
        root = pathlib.Path(_SAMPLE_VARS["save_location"])
    else:
        root = pathlib.Path(save_location).expanduser()
        try:
            root = root.resolve(strict=False)
        except OSError:
            pass
        if "\0" in save_location:
            result.errors.append(
                ValidationIssue("Save Location", "Path contains invalid characters.")
            )

    if not file_format:
        result.errors.append(
            ValidationIssue("File Format", "File Format is required.")
        )
    elif not file_format_has_unique_token(file_format):
        result.errors.append(ValidationIssue("File Format", _UNIQUE_TOKEN_HELP))

    if not dir_format:
        result.warnings.append(
            ValidationIssue(
                "Directory Format",
                "Directory Format is empty — files may all land in Save Location root.",
            )
        )
    else:
        esc = _template_escapes_root(dir_format, root)
        if esc:
            result.errors.append(ValidationIssue("Directory Format", esc))

    if metadata:
        # Metadata often uses {configpath}/{profile}/... — confine under config home when possible.
        try:
            import ofscraper.utils.paths.common as common_paths

            meta_root = common_paths.get_config_home()
        except Exception:
            meta_root = pathlib.Path(_SAMPLE_VARS["config_path"])
        # Only flag obvious escapes / absolute custom paths that leave config home via ..
        if ".." in metadata.replace("{", " ").replace("}", " "):
            esc_meta = _template_escapes_root(metadata, meta_root)
            if esc_meta and "absolute" not in esc_meta.lower():
                result.warnings.append(
                    ValidationIssue(
                        "Metadata Path",
                        "Metadata template may leave the config home directory.",
                    )
                )
        try:
            formatted_meta = _format_template(
                metadata,
                {
                    "configpath": str(meta_root),
                    "config_path": str(meta_root),
                },
            )
            meta_path = pathlib.Path(formatted_meta)
            if meta_path.is_absolute():
                try:
                    meta_path.resolve(strict=False).relative_to(
                        meta_root.expanduser().resolve(strict=False)
                    )
                except ValueError:
                    result.warnings.append(
                        ValidationIssue(
                            "Metadata Path",
                            "Absolute metadata path is outside the usual config home.",
                        )
                    )
        except ValueError as e:
            result.errors.append(ValidationIssue("Metadata Path", str(e)))

    # Content filter sanity
    content = cfg.get("content_filter_options") if isinstance(cfg.get("content_filter_options"), Mapping) else {}
    content = content or {}
    try:
        length_min = int(content.get("length_min") or 0)
        length_max = int(content.get("length_max") or 0)
        if length_min > 0 and length_max > 0 and length_min > length_max:
            result.errors.append(
                ValidationIssue(
                    "Length filters",
                    f"Min Length ({length_min}) is greater than Max Length ({length_max}).",
                )
            )
    except (TypeError, ValueError):
        result.warnings.append(
            ValidationIssue("Length filters", "Could not parse length min/max values.")
        )

    # Download filter empty
    download_opts = cfg.get("download_options") if isinstance(cfg.get("download_options"), Mapping) else {}
    filt = (download_opts or {}).get("filter")
    if isinstance(filt, list) and len(filt) == 0:
        result.warnings.append(
            ValidationIssue(
                "Download Filter",
                "No media types are enabled — scrapes may download nothing.",
            )
        )

    # FFmpeg path if set
    binary = cfg.get("binary_options") if isinstance(cfg.get("binary_options"), Mapping) else {}
    ffmpeg = str((binary or {}).get("ffmpeg") or "").strip()
    if ffmpeg:
        ff = pathlib.Path(ffmpeg).expanduser()
        if not ff.is_file():
            result.warnings.append(
                ValidationIssue(
                    "FFmpeg Path",
                    f"Configured path does not exist as a file: {ffmpeg}",
                )
            )

    return result


def show_config_validation_dialog(
    parent,
    result: ValidationResult,
    *,
    context: str = "save",
) -> bool:
    """Show errors/warnings. Return True if the caller should proceed.

    ``context`` is ``save`` or ``scrape`` (wording only).
    """
    from PyQt6.QtWidgets import QMessageBox

    action = "save configuration" if context == "save" else "start scraping"

    if result.errors:
        QMessageBox.critical(
            parent,
            "Configuration Invalid",
            f"Cannot {action} until these issues are fixed:\n\n"
            f"{result.format_errors()}\n\n"
            "Open Configuration and update File Options (Save Location, "
            "Directory Format, File Format).",
        )
        return False

    if result.warnings:
        reply = QMessageBox.warning(
            parent,
            "Configuration Warnings",
            f"These warnings were found before trying to {action}:\n\n"
            f"{result.format_warnings()}\n\n"
            "Continue anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    return True


def confirm_config_for_scrape(parent=None) -> bool:
    """Validate on-disk config before starting a scrape. Returns False to abort."""
    result = validate_config()
    if result.ok and not result.has_warnings:
        return True
    try:
        from PyQt6.QtWidgets import QApplication

        parent = parent or QApplication.activeWindow()
    except Exception:
        parent = None
    return show_config_validation_dialog(parent, result, context="scrape")
