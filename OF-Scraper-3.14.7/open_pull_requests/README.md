# Open Pull Requests — cjb900/OF-Scraper-GUI

Snapshot of 27 open PRs. Each PR has its own file with title, description, and full diff.

| # | Title | Author | Branch | Files | +/- |
|---|---|---|---|---|---|
| 2 | [fix(drm): request purchased wall posts' keys from the post endpoint](PR-002-fix-drm-request-purchased-wall-posts-keys-from-the-post-endp.md) | cloakedkeys | `fix/drm-license-paid-posts` | 2 | +46/-1 |
| 3 | [fix(ffmpeg): accept ffmpeg 8 and newer for DRM](PR-003-fix-ffmpeg-accept-ffmpeg-8-and-newer-for-drm.md) | cloakedkeys | `fix/ffmpeg-8-drm` | 4 | +180/-3 |
| 4 | [fix(download): don't treat the filename as a regex when hiding it in logs](PR-004-fix-download-don-t-treat-the-filename-as-a-regex-when-hiding.md) | cloakedkeys | `fix/url-log-regex` | 2 | +34/-1 |
| 5 | [fix(session): use one asyncio.Lock per event loop in SessionSleep](PR-005-fix-session-use-one-asyncio-lock-per-event-loop-in-sessionsl.md) | cloakedkeys | `fix/session-sleep-lock` | 2 | +69/-1 |
| 6 | [fix(console): replace unencodable characters instead of crashing](PR-006-fix-console-replace-unencodable-characters-instead-of-crashi.md) | cloakedkeys | `fix/console-encoding` | 2 | +58/-0 |
| 7 | [fix(naming): make textlength and text type settings take effect](PR-007-fix-naming-make-textlength-and-text-type-settings-take-effec.md) | cloakedkeys | `fix/textlength` | 4 | +103/-6 |
| 8 | [fix(download): don't fail finished downloads when a path can't be resolved](PR-008-fix-download-don-t-fail-finished-downloads-when-a-path-can-t.md) | cloakedkeys | `fix/resolve-network-drive` | 2 | +138/-37 |
| 9 | [fix(config): accept quoted CDM/ffmpeg paths and empty ffmpeg setting](PR-009-fix-config-accept-quoted-cdm-ffmpeg-paths-and-empty-ffmpeg-s.md) | cloakedkeys | `fix/quoted-paths` | 4 | +102/-5 |
| 10 | [fix(prompts): keep model selector prompts visible and stdout intact](PR-010-fix-prompts-keep-model-selector-prompts-visible-and-stdout-i.md) | cloakedkeys | `fix/model-selector-stdout` | 3 | +102/-36 |
| 11 | [fix(models): don't drop to the main menu after 'Yes Update Selection'](PR-011-fix-models-don-t-drop-to-the-main-menu-after-yes-update-sele.md) | cloakedkeys | `fix/update-selection-menu` | 3 | +44/-2 |
| 12 | [fix(paid): warn when a Purchases scan stops early](PR-012-fix-paid-warn-when-a-purchases-scan-stops-early.md) | cloakedkeys | `fix/paid-scan-warnings` | 2 | +111/-7 |
| 13 | [feat(paid): skip --excluded-username models during --scrape-paid](PR-013-feat-paid-skip-excluded-username-models-during-scrape-paid.md) | cloakedkeys | `feat/scrape-paid-excluded-username` | 4 | +188/-1 |
| 14 | [fix(metadata): stop passing mediatype to get_hash](PR-014-fix-metadata-stop-passing-mediatype-to-get-hash.md) | cloakedkeys | `fix/metadata-hash-arg` | 2 | +61/-4 |
| 15 | [fix(profile): skip the profile area for deleted accounts](PR-015-fix-profile-skip-the-profile-area-for-deleted-accounts.md) | cloakedkeys | `fix/profile-deleted-model` | 2 | +57/-0 |
| 16 | [fix(models): keep deleted-account placeholders out of the normal scrape](PR-016-fix-models-keep-deleted-account-placeholders-out-of-the-norm.md) | cloakedkeys | `fix/paid-placeholder-models` | 3 | +51/-3 |
| 17 | [fix(messages): keep pages that end a scan and stop re-paginating chunk 0](PR-017-fix-messages-keep-pages-that-end-a-scan-and-stop-re-paginati.md) | cloakedkeys | `fix/messages-chunk-boundary` | 2 | +154/-15 |
| 18 | [fix(daemon): stop on SIGTERM instead of waiting for SIGKILL](PR-018-fix-daemon-stop-on-sigterm-instead-of-waiting-for-sigkill.md) | cloakedkeys | `fix/daemon-sigterm` | 3 | +85/-1 |
| 19 | [fix(download): prevent filename collisions at the final move](PR-019-fix-download-prevent-filename-collisions-at-the-final-move.md) | cloakedkeys | `fix/filename-collisions` | 8 | +716/-21 |
| 20 | [fix(daemon): only mark a job done after taking it from the queue](PR-020-fix-daemon-only-mark-a-job-done-after-taking-it-from-the-que.md) | cloakedkeys | `fix/daemon-idle-task-done` | 4 | +192/-2 |
| 21 | [feat(daemon): trigger an idle scraping pass with SIGUSR1](PR-021-feat-daemon-trigger-an-idle-scraping-pass-with-sigusr1.md) | cloakedkeys | `feat/daemon-sigusr1` | 7 | +494/-10 |
| 22 | [feat(recovery): mark old filename collisions for re-download](PR-022-feat-recovery-mark-old-filename-collisions-for-re-download.md) | cloakedkeys | `feat/collision-recovery` | 10 | +1077/-21 |
| 23 | [fix(docker): copy the GUI patches from the repo root](PR-023-fix-docker-copy-the-gui-patches-from-the-repo-root.md) | cloakedkeys | `fix/docker-patch-paths` | 2 | +5/-6 |
| 24 | [fix(docker): pass docker stop on to the GUI instead of waiting for SIGKILL](PR-024-fix-docker-pass-docker-stop-on-to-the-gui-instead-of-waiting.md) | cloakedkeys | `fix/docker-graceful-stop` | 2 | +43/-7 |
| 25 | [fix(gui): cancel the scrape and quit cleanly on SIGTERM](PR-025-fix-gui-cancel-the-scrape-and-quit-cleanly-on-sigterm.md) | cloakedkeys | `fix/gui-sigterm-shutdown` | 3 | +203/-0 |
| 26 | [test: repair the legacy suite and retire tests for removed code](PR-026-test-repair-the-legacy-suite-and-retire-tests-for-removed-co.md) | cloakedkeys | `fix/legacy-tests` | 38 | +3553/-3181 |
| 27 | [ci: run the tests in the OF-Scraper-3.14.7 project with uv](PR-027-ci-run-the-tests-in-the-of-scraper-3-14-7-project-with-uv.md) | cloakedkeys | `ci/run-tests-with-uv` | 39 | +3570/-3190 |
| 28 | [chore: support Python 3.15 for source installs](PR-028-chore-support-python-3-15-for-source-installs.md) | cloakedkeys | `chore/python-3.15` | 24 | +2081/-685 |
