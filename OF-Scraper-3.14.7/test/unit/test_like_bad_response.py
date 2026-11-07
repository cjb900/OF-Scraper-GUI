"""An unreadable like/unlike response marks the post failed (fork #205)."""

import contextlib

import pytest

import ofscraper.commands.scraper.actions.like.like as like

pytestmark = pytest.mark.unit


class Response:
    def json_(self):
        raise ValueError("not JSON")


class Session:
    @contextlib.contextmanager
    def requests(self, *args, **kwargs):
        yield Response()


class Post:
    id = 123

    def __init__(self):
        self.results = []

    def mark_like_attempt(self):
        pass

    def mark_post_liked(self, success=True):
        self.results.append(success)

    def mark_post_unliked(self, success=True):
        self.results.append(success)


@pytest.fixture
def tracker(monkeypatch):
    # the GUI's per-post status table
    status = {}
    monkeypatch.setattr(like, "_GUI_LIKE_TRACKER", status)
    return status


@pytest.mark.parametrize("toggle", [like._toggle_like_requests, like._toggle_unlike_requests])
def test_an_unreadable_response_marks_the_post_failed(toggle, tracker):
    post = Post()
    # 3 is the "failed" result; before the fix this raised a TypeError
    assert toggle(Session(), post, 456) == 3
    assert post.results == [False]
    assert tracker == {123: "Failed"}
