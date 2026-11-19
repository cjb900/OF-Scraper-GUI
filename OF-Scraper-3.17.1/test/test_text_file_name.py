"""Text-only file names don't repeat the post text.

A text post has no media file, so {filename} (and {file_name},
{only_filename}, ...) stands for the post text. With a File Format that also
has {text}, such as "{date} {filename} {text}.{ext}", every .txt name held the
text twice ("2021-09-26 Hey babes! Hey babes!.txt"). The file name
placeholders are now the post id when the format has {text}, as a media
file's {filename} is its media id.
"""

import asyncio

import pytest

import ofscraper.classes.of.posts as posts_
import ofscraper.classes.placeholder as placeholder

from test_undated_posts import names_env  # noqa: F401  (fixture)

POST = {"id": 8, "text": "Hey babes!", "price": 0, "isOpened": True,
        "responseType": "message", "createdAt": "2021-09-26T10:00:00+00:00"}


def text_name(monkeypatch, file_format):
    monkeypatch.setattr(placeholder.data, "get_fileformat", lambda *a, **k: file_format)
    item = posts_.Post(dict(POST), 1, "u", "messages")
    return asyncio.run(placeholder.Textholders(item, "txt").createfilename())


@pytest.mark.parametrize("file_format, expected", [
    ("{date} {filename} {text}.{ext}", "2021-09-26 8 Hey babes!.txt"),
    ("{date} {file_name} {text}.{ext}", "2021-09-26 8 Hey babes!.txt"),
    ("{only_filename}_{text}.{ext}", "8_Hey babes!.txt"),
])
def test_text_is_not_repeated(names_env, monkeypatch, file_format, expected):  # noqa: F811
    assert text_name(monkeypatch, file_format) == expected


@pytest.mark.parametrize("file_format, expected", [
    # without {text}, the file name placeholders still give the post text
    ("{date} {filename}.{ext}", "2021-09-26 Hey babes!.txt"),
    ("{file_name}.{ext}", "Hey babes!.txt"),
    ("{media_id}.{ext}", "8.txt"),
    ("{date} {text}.{ext}", "2021-09-26 Hey babes!.txt"),
])
def test_formats_without_both_are_unchanged(names_env, monkeypatch, file_format, expected):  # noqa: F811
    assert text_name(monkeypatch, file_format) == expected


def test_format_fields():
    import ofscraper.utils.config.data as data

    cases = {
        "{date} {filename} {text}.{ext}": {"date", "filename", "text", "ext"},
        "{args.username}/{text!s:.10}.{ext}": {"args", "text", "ext"},
        "{config[x]}.{ext}": {"config", "ext"},
        "{{text}}.{ext}": {"ext"},
    }
    original = data.get_fileformat
    try:
        for fmt, fields in cases.items():
            data.get_fileformat = lambda fmt=fmt: fmt
            assert placeholder.text_format_fields() == fields, fmt
        data.get_fileformat = lambda: "{broken"
        assert placeholder.text_format_fields() == set()
    finally:
        data.get_fileformat = original
