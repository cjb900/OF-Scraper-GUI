# PR #23: fix(docker): copy the GUI patches from the repo root

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/23
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/docker-patch-paths` → `main`
- **Created:** 2026-10-23T03:10:13Z  ·  **Updated:** 2026-10-23T03:10:13Z
- **Draft:** False
- **Changes:** 2 files, +5 / -6

## Description

`docker compose build` fails on a fresh clone:

```
COPY OF-Scraper-3.14.5/patch_ofscraper_3.14.5_gui.py ./
ERROR: failed to compute cache key: "/OF-Scraper-3.14.5/patch_ofscraper_3.14.5_gui.py": not found
```

The Dockerfile copies `OF-Scraper-X.X.X/patch_ofscraper_X.X.X_gui.py` for every version. Only 3.14.7 has a copy in its folder (identical to the root one). The 3.12.9, 3.14.3 and 3.14.5 patches have only ever been committed at the repo root. Builds that have those files locally work; a clone doesn't.

## Change
- Copy `patch_ofscraper_*_gui.py` from the repo root, which is where the README runs the patches from.
- Update the matching comments in the Dockerfile and `docker-compose.yml`.

## Tested
- Built from a fresh clone of `main`: it fails as above.
- Built with this change: it succeeds and logs `Applied GUI patch: 20260829_gui_3_14_7_v365`. The GUI starts and is reachable over noVNC.

## Files changed

- `docker-compose.yml`
- `docker/Dockerfile`

## Code changes (full diff)

```diff
diff --git a/docker-compose.yml b/docker-compose.yml
index 15f54d3..ec1b549 100644
--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ -5,7 +5,7 @@ services:
       dockerfile: docker/Dockerfile
       args:
         # Which GUI patch version to use at build time.
-        # Must match one of the OF-Scraper-X.X.X/patch_ofscraper_X.X.X_gui.py files.
+        # Must match one of the patch_ofscraper_X.X.X_gui.py files in the repo root.
         # Available: 3.12.9, 3.14.3, 3.14.5, 3.14.7
         GUI_PATCH_VERSION: "3.14.7"
     container_name: ofscraper-gui
diff --git a/docker/Dockerfile b/docker/Dockerfile
index 8c9e3ee..031c8a1 100644
--- a/docker/Dockerfile
+++ b/docker/Dockerfile
@@ -1,7 +1,7 @@
 FROM ubuntu:24.04
 
 # Build arg: which version of ofscraper + GUI patch to use.
-# Must match one of the OF-Scraper-X.X.X/patch_ofscraper_X.X.X_gui.py files.
+# Must match one of the patch_ofscraper_X.X.X_gui.py files in the repo root.
 ARG GUI_PATCH_VERSION=3.14.7
 
 ENV DEBIAN_FRONTEND=noninteractive \
@@ -57,10 +57,9 @@ RUN pip install --no-cache-dir ofscraper==${GUI_PATCH_VERSION}
 
 # ── Copy all available GUI patches and apply the selected one ─────────────────
 WORKDIR /opt/ofscraper-gui
-COPY OF-Scraper-3.12.9/patch_ofscraper_3.12.9_gui.py ./
-COPY OF-Scraper-3.14.3/patch_ofscraper_3.14.3_gui.py ./
-COPY OF-Scraper-3.14.5/patch_ofscraper_3.14.5_gui.py ./
-COPY OF-Scraper-3.14.7/patch_ofscraper_3.14.7_gui.py ./
+# The patches live at the repo root; only 3.14.7 also has a copy in its
+# OF-Scraper-X.X.X folder.
+COPY patch_ofscraper_*_gui.py ./
 
 RUN python patch_ofscraper_${GUI_PATCH_VERSION}_gui.py -y --skip-pyqt6 \
     && python -c "from ofscraper.gui.patch_version import PATCH_ID; print(f'Applied GUI patch: {PATCH_ID}')"
```
