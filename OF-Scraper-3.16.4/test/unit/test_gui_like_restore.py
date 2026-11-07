"""The corrective second like/unlike request decides the result (fork #212),
also in the GUI's per-post status table.

test/test_like_restore.py covers the scraper's result; these also check
that a failed second request shows as "Failed" in the GUI, not as the
status of the first request.
"""

import contextlib

import pytest

import ofscraper.commands.scraper.actions.like.like as like

pytestmark = pytest.mark.unit


class Response:
    def __init__(self, favorite):
        self.favorite = favorite

    def json_(self):
        if self.favorite == "bad":
            raise ValueError("not JSON")
        return {"isFavorite": self.favorite, "id": 123}


class Session:
    """Replies to each request in turn with the next isFavorite value."""

    def __init__(self, *favorites):
        self.favorites = list(favorites)
        self.calls = 0

    @contextlib.contextmanager
    def requests(self, *args, **kwargs):
        self.calls += 1
        yield Response(self.favorites.pop(0))


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


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(like.time, "sleep", lambda *_: None)


@pytest.fixture
def tracker(monkeypatch):
    # the GUI's per-post status table
    status = {}
    monkeypatch.setattr(like, "_GUI_LIKE_TRACKER", status)
    return status


# (first reply, second reply) for a like: the first toggle unliked an already-liked post
@pytest.mark.parametrize("second", ["bad", False])
def test_like_fails_when_the_second_request_does_not_relike(second, tracker):
    post, session = Post(), Session(False, second)
    assert like._toggle_like_requests(session, post, 456) == 3
    assert post.results == [False]
    assert session.calls == 2
    assert tracker == {123: "Failed"}


def test_like_restored(tracker):
    post, session = Post(), Session(False, True)
    assert like._toggle_like_requests(session, post, 456) == 2
    assert post.results == [True]
    assert tracker == {123: "Liked"}


@pytest.mark.parametrize("second", ["bad", True])
def test_unlike_fails_when_the_second_request_does_not_unlike(second, tracker):
    post, session = Post(), Session(True, second)
    assert like._toggle_unlike_requests(session, post, 456) == 3
    assert post.results == [False]
    assert session.calls == 2
    assert tracker == {123: "Failed"}


def test_unlike_restored(tracker):
    post, session = Post(), Session(True, False)
    assert like._toggle_unlike_requests(session, post, 456) == 2
    assert post.results == [True]
    assert tracker == {123: "Unliked"}
