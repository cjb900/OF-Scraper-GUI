# Legacy tests (not run)

These came from upstream OF-Scraper and were written for code that has since been removed or rewritten. They're kept for reference and excluded from the run by `--ignore=test/legacy` in `pyproject.toml`.

Tests from the same files that still work against today's code were repaired in place (new import paths, moved constants, `config=` keyword for config getters) and are run as normal.

The tests here fail because they:

- mock functions or attributes that no longer exist (`args2.args.getargs`, `Placeholders.databasePathHelper`, `classes.posts.config`);
- call the old database layer, whose operations now take a model id and username and find the database themselves;
- test removed options (`mp4decrypt`, `file_size_limit`, `get_filesize_limit`) or the removed `ofscraper.download` package;
- expect older behaviour, e.g. lower-case response and media types (`'images'`, `'post'`) where the code now uses `'Images'`, `'Timeline'`, or `0`/`False` where it now returns a different falsy value.

Rewriting them means re-deriving each expectation from current code, so it's left for whoever changes the code they cover.

## Whole files

- `db/archive_test.py`
- `db/highlights_test.py`
- `db/media_test.py`
- `db/message_test.py`
- `db/pinned_test.py`
- `db/post_test.py`
- `db/profile_test.py`
- `db/stories_test.py`
- `general/filter_test.py`
- `general/like_test.py`
- `general/path_test.py`
- `general/profile_folder_test.py`

## Individual tests moved out of files that otherwise still run

- `general/config_test.py` (8): `test_filesize`, `test_filesize2`, `test_filesize3`, `test_filter2`, `test_mp4decrypt`, `test_mp4decrypt2`, `test_mp4decrypt3`, `test_new_config_location`
- `general/misc_test.py` (2): `test_args`, `test_args_change`
- `general/profile_scrape_test.py` (4): `test_me`, `test_parse_profile`, `test_parse_profile2`, `test_parse_profile3`
- `post/archived_post_test.py` (16): `test_archived_archived`, `test_archived_text_lettertruncate`, `test_archived_text_lettertruncate2`, `test_archived_text_lettertruncate3`, `test_archived_text_lettertruncate4`, `test_archived_text_lettertruncate5`, `test_archived_text_lettertruncate6`, `test_archived_text_wordtruncate`, `test_archived_text_wordtruncate2`, `test_archived_text_wordtruncate3`, `test_archived_text_wordtruncate4`, `test_archived_text_wordtruncate5`, `test_archived_text_wordtruncate6`, `test_medialinked_archived`, `test_mediatype_archived`, `test_ogresponse_archived`
- `post/highlight_post_test.py` (20): `test_archived_highlights`, `test_highlight_text_lettertruncate`, `test_highlight_text_lettertruncate2`, `test_highlight_text_lettertruncate3`, `test_highlight_text_lettertruncate4`, `test_highlight_text_lettertruncate5`, `test_highlight_text_lettertruncate6`, `test_highlight_text_wordtruncate`, `test_highlight_text_wordtruncate2`, `test_highlight_text_wordtruncate3`, `test_highlight_text_wordtruncate4`, `test_highlight_text_wordtruncate5`, `test_highlight_text_wordtruncate6`, `test_media_id_highlights`, `test_mediaclass_highlights`, `test_medialinked_highlights`, `test_mediatype_highlights`, `test_mediaurl_highlights`, `test_ogresponse_highlights`, `test_paid_highlights`
- `post/messages_post_test.py` (16): `test_archived_messages`, `test_medialinked_messages`, `test_mediatype_messages`, `test_messages_text_lettertruncate`, `test_messages_text_lettertruncate2`, `test_messages_text_lettertruncate3`, `test_messages_text_lettertruncate4`, `test_messages_text_lettertruncate5`, `test_messages_text_lettertruncate6`, `test_messages_text_wordtruncate`, `test_messages_text_wordtruncate2`, `test_messages_text_wordtruncate3`, `test_messages_text_wordtruncate4`, `test_messages_text_wordtruncate5`, `test_messages_text_wordtruncate6`, `test_ogresponse_messages`
- `post/paid_post_test.py` (16): `test_archived_paid`, `test_medialinked_paid`, `test_mediatype_paid`, `test_ogresponse_paid`, `test_paid_text_lettertruncate`, `test_paid_text_lettertruncate2`, `test_paid_text_lettertruncate3`, `test_paid_text_lettertruncate4`, `test_paid_text_lettertruncate5`, `test_paid_text_lettertruncate6`, `test_paid_text_wordtruncate`, `test_paid_text_wordtruncate2`, `test_paid_text_wordtruncate3`, `test_paid_text_wordtruncate4`, `test_paid_text_wordtruncate5`, `test_paid_text_wordtruncate6`
- `post/pinned_post_test.py` (16): `test_archived_pinned`, `test_medialinked_pinned`, `test_mediatype_pinned`, `test_ogresponse_pinned`, `test_pinned_text_lettertruncate`, `test_pinned_text_lettertruncate2`, `test_pinned_text_lettertruncate3`, `test_pinned_text_lettertruncate4`, `test_pinned_text_lettertruncate5`, `test_pinned_text_lettertruncate6`, `test_pinned_text_wordtruncate`, `test_pinned_text_wordtruncate2`, `test_pinned_text_wordtruncate3`, `test_pinned_text_wordtruncate4`, `test_pinned_text_wordtruncate5`, `test_pinned_text_wordtruncate6`
- `post/stories_post_test.py` (20): `test_archived_stories`, `test_mediaclass_stories`, `test_medialinked_stories`, `test_mediatype_stories`, `test_mediaurl_stories`, `test_ogresponse_stories`, `test_paid_stories`, `test_stories_text_lettertruncate`, `test_stories_text_lettertruncate2`, `test_stories_text_lettertruncate3`, `test_stories_text_lettertruncate4`, `test_stories_text_lettertruncate5`, `test_stories_text_lettertruncate6`, `test_stories_text_wordtruncate`, `test_stories_text_wordtruncate2`, `test_stories_text_wordtruncate3`, `test_stories_text_wordtruncate4`, `test_stories_text_wordtruncate5`, `test_stories_text_wordtruncate6`, `test_text_stories2`
- `post/timeline_post_test.py` (16): `test_archived_timeline`, `test_medialinked_timeline`, `test_mediatype_timeline`, `test_ogresponse_timeline`, `test_timeline_text_lettertruncate`, `test_timeline_text_lettertruncate2`, `test_timeline_text_lettertruncate3`, `test_timeline_text_lettertruncate4`, `test_timeline_text_lettertruncate5`, `test_timeline_text_lettertruncate6`, `test_timeline_text_wordtruncate`, `test_timeline_text_wordtruncate2`, `test_timeline_text_wordtruncate3`, `test_timeline_text_wordtruncate4`, `test_timeline_text_wordtruncate5`, `test_timeline_text_wordtruncate6`
