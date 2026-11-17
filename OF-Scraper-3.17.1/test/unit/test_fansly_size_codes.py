"""Fansly's style codes ([s:lg], [c:blue] ... [/c], **bold**, *italic*) stay
out of the post text, so file names, the table and the database get the
text as Fansly shows it."""

import pytest

from ofscraper.sites.fansly import normalize

# texts as Fansly sends them (from a real scrape)
@pytest.mark.parametrize("content, text", [
    ("**[s:lg]BARELY LEGAL BUNDLE: JUST TURNED 18 [c:blue]👀‼️*(16 videos + 23 photos) *[/c]**\n\nI found",
     "BARELY LEGAL BUNDLE: JUST TURNED 18 👀‼️(16 videos + 23 photos)\n\nI found"),
    ("**[s:lg]WORKOUT GIRL CUMS AND SQUIRTS 25+ TIMES 👟💦 [c:blue]*(40 mins)* **[/c]\n\nIs it real",
     "WORKOUT GIRL CUMS AND SQUIRTS 25+ TIMES 👟💦 (40 mins)\n\nIs it real"),
    ("[s:lg]**[s:lg]BIGGEST AND BEST", "BIGGEST AND BEST"),
    ("[s:xl]**WELCUM TO MY PAGE!** 😍", "WELCUM TO MY PAGE! 😍"),
    ("**[c:blue]Bonus Offer:[/c] Unlock a Se", "Bonus Offer: Unlock a Se"),
    ("[c:green][c:pink]**I was thinking**[/c][/c]", "I was thinking"),
    ("***[c:blue]If you haven't[/c]***", "If you haven't"),
    ("*Hi everyone! ❤️*\nJust a little update", "Hi everyone! ❤️\nJust a little update"),
    ("what the f*ck", "what the f*ck"),
    ("no codes [18+] [solo] [s] [slg] here", "no codes [18+] [solo] [s] [slg] here"),
    ("", ""),
    (None, ""),
])
def test_plain_text(content, text):
    assert normalize.plain_text(content) == text


def test_posts_carry_the_plain_text():
    response = {"posts": [{"id": "1", "createdAt": 1760000000,
                           "content": "**[s:lg]BARELY LEGAL** #bundle"}]}
    post = normalize.posts(response)[0]
    assert post["text"] == "BARELY LEGAL #bundle"
    assert post["hashtags"] == ["bundle"]


def test_the_file_name_text_has_no_code():
    from ofscraper.classes.of.posts import Post

    response = {"posts": [{"id": "1", "createdAt": 1760000000,
                           "content": "**[s:lg]BARELY LEGAL BUNDLE: JUST TURNED 18 [c:blue]👀**[/c]"}]}
    post = Post(normalize.posts(response)[0], 1, "outrageousone")
    assert post.file_sanitized_text.startswith("BARELY LEGAL BUNDLE JUST TURNED 18")
