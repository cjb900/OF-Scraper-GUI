"""Fansly's text-size codes ([s], [slg], [sxl]) stay out of the post text."""

import pytest

from ofscraper.sites.fansly import normalize


@pytest.mark.parametrize("content, text", [
    ("[slg]BARELY LEGAL BUNDLE: JUST TURNED 18", "BARELY LEGAL BUNDLE: JUST TURNED 18"),
    ("[slg][slg]BIGGEST AND BEST 35", "BIGGEST AND BEST 35"),
    ("[sxl]WELCUM TO MY PAGE! 😍🎉[s]Hi there", "WELCUM TO MY PAGE! 😍🎉 Hi there"),
    ("[slg]Big[/slg] and [s]small[/s] words", "Big and small words"),
    ("no codes [18+] [hot] here", "no codes [18+] [hot] here"),
    ("[solo] [sex] [sexy] [stop] [sl]", "[solo] [sex] [sexy] [stop] [sl]"),
    ("[sxs]a[ssm]b[smd]c[sxxl]d", "a b c d"),
    ("", ""),
    (None, ""),
])
def test_plain_text(content, text):
    assert normalize.plain_text(content) == text


def test_posts_carry_the_plain_text():
    response = {"posts": [{"id": "1", "createdAt": 1760000000,
                           "content": "[slg]BARELY LEGAL #bundle"}]}
    post = normalize.posts(response)[0]
    assert post["text"] == "BARELY LEGAL #bundle"
    assert post["hashtags"] == ["bundle"]


def test_the_file_name_text_has_no_code():
    from ofscraper.classes.of.posts import Post

    response = {"posts": [{"id": "1", "createdAt": 1760000000,
                           "content": "[slg]BARELY LEGAL BUNDLE: JUST TURNED 18"}]}
    post = Post(normalize.posts(response)[0], 1, "outrageousone")
    assert "[" not in post.file_sanitized_text
