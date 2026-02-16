# OF-Scraper GUI Help / README

This is an in-app guide to what each GUI page/section does and how to use it.

Tip: the small **(?)** buttons next to sections will jump you to the matching section in this README.

---

## Table of contents

- [Left navigation](#nav-left)
- [Scraper workflow](#scraper-workflow)
- [Select Content Areas & Filters](#sca-root)
  - [Content Areas](#sca-content-areas)
  - [Additional Options](#sca-additional-options)
  - [Advanced Scrape Options](#sca-advanced-options)
  - [Daemon Mode](#sca-daemon-mode)
  - [Filters (embedded)](#sca-filters)
- [Select Models](#models-root)
  - [Model Filters (right sidebar)](#models-filters-root)
- [Configuration (config.json)](#config-root)
- [Table / Scraping page](#table-root)
  - [Toolbar buttons](#table-toolbar)
  - [Progress + logs](#table-progress)
- [Filters (Table page + embedded)](#filters-root)
- [Table columns](#table-columns)
- [Merge DBs](#merge-dbs)
- [Troubleshooting notes](#troubleshooting)

---

<a id="nav-left"></a>
## Left navigation

- **Scraper**: Main workflow for scraping/downloading/liking.
- **Authentication**: Enter cookies/headers (stored in your profile `auth.json`).
- **Configuration**: Edit `config.json` settings (save location, formats, performance, CDM, etc.).
- **Profiles**: Manage profiles (each profile has separate auth + `.data`).
- **Merge DBs**: Merge `user_data.db` files into a single database.
- **Help / README**: This page.

---

<a id="scraper-workflow"></a>
## Scraper workflow (Scraper →)

<a id="action-select"></a>
### 1) Select Action

- **Download content from a user**: Scrape content and build the table.
- **Like / Unlike**: Perform like/unlike actions (limited to supported areas).
- **Download + Like / Unlike**: Do both.

---

<a id="sca-root"></a>
## Select Content Areas & Filters

This page decides **what to scan** and (optionally) provides **filters** that affect what you see/queue later.

<a id="sca-content-areas"></a>
### Content Areas

These are the sources to scan (depending on action):

- **Profile**: Profile/media feed.
- **Timeline**: Standard posts.
- **Pinned**: Posts pinned on the profile.
- **Archived**: Archived posts.
- **Highlights**: Highlight stories.
- **Stories**: Stories feed.
- **Messages**: Message media (this is where many PPV-related entries appear).
- **Purchased**: Explicit “purchased content” area (when applicable).
- **Streams**: Streams/live-related media.
- **Labels**: Content gathered via labels.

Example:
- If you only care about messages, uncheck everything except **Messages** to speed up scraping.

<a id="sca-additional-options"></a>
### Additional Options

<a id="sca-scrape-paid"></a>
#### Scrape entire paid page (slower but more comprehensive)
Attempts to enumerate paid items more thoroughly. This can be slower.

When to use:
- If you suspect paid/PPV items aren’t being discovered.

<a id="sca-scrape-labels"></a>
#### Scrape labels
Pulls content via labels when available.

When to use:
- If you organize creators by labels and want label-based coverage.

<a id="sca-discord-updates"></a>
#### Send updates to Discord (requires webhook URL in Config → General)
If enabled, the GUI will post log updates to Discord using your configured webhook.

Important:
- This only works if **Config → General → Discord Webhook URL** is set.
- Internally this enables the equivalent of running with `--discord NORMAL`.

<a id="sca-advanced-options"></a>
### Advanced Scrape Options

<a id="sca-allow-dupes"></a>
#### Allow duplicates (do NOT skip duplicates; treat reposts as new items)
Disables duplicate-skipping logic. Useful if reposts should be treated as separate items.

Example:
- A creator reposts the same media across Timeline and Pinned and you want both.

<a id="sca-rescrape-all"></a>
#### Rescrape everything (ignore cache / scan from the beginning)
Forces a full history scan and disables “start after last seen” behavior.

When to use:
- After changing filters/config and you want a complete rebuild.
- When you suspect cached state is hiding items.

<a id="sca-delete-db"></a>
#### Delete model DB before scraping (resets downloaded/unlocked history)
Deletes the model DB folder so the run starts “fresh”.

Important:
- The DB will be recreated during scraping.

<a id="sca-delete-downloads"></a>
#### Also delete existing downloaded files for selected models
Deletes already-downloaded files under your save location for the selected model(s).

Tip:
- If you enable file deletion, the GUI also enables DB deletion to avoid stale state.

<a id="sca-examples"></a>
### Example setups

- **Fast “new items only”**:
  - Leave **Rescrape everything** unchecked.
  - Choose only the areas you want (e.g., Timeline + Messages).

- **Full reset / rebuild**:
  - Enable **Rescrape everything**
  - Enable **Delete model DB**
  - Optionally enable **Delete downloaded files** (careful!)

<a id="sca-daemon-mode"></a>
### Daemon Mode (Auto-Repeat Scraping)

<a id="sca-daemon-enable"></a>
#### Enable daemon mode
Automatically re-runs scraping on a schedule.

<a id="sca-daemon-interval"></a>
#### Interval
Minutes between runs.

<a id="sca-daemon-notify"></a>
#### System notification when scraping starts
Shows a desktop notification at the start of each daemon run.

<a id="sca-daemon-sound"></a>
#### Sound alert when scraping starts
Plays a short beep at the start of each daemon run (best-effort on Windows).

<a id="sca-filters"></a>
### Filters (on this page)

This page contains an embedded version of the same filter panel used on the Table page.
See the **Filters** section below for full details.

---

<a id="models-root"></a>
## Select Models

Select which creators/models to process. The list is populated from the API.

Tips:
- Search supports comma-separated terms (e.g. `alice, bob, charlie`).
- Use **Select All / Deselect All / Toggle** for bulk selection.

<a id="models-filters-root"></a>
### Model Filters (right sidebar)

<a id="models-filters-subscription"></a>
#### Subscription Type
- **Renewal**: Filter by renewal on/off.
- **Status**: Filter active vs expired.

<a id="models-filters-flags"></a>
#### Flags
- **Promo**: Whether the model has claimable promos.
- **Free Trial**: Filter models that have free trials.
- **Last Seen**: Visible/Hidden state.

<a id="models-filters-price"></a>
#### Price Range
Filter models by price (min/max).

<a id="models-filters-sort"></a>
#### Sort
Controls how models are ordered (Name, Last Seen, Price, etc.) and Descending.

---

<a id="config-root"></a>
## Configuration (config.json)

This page edits `config.json` through a set of tabs. Changes are written to disk when you click **Save**.

For deeper background documentation, see the official docs: [OF-Scraper GitBook](https://of-scraper.gitbook.io/of-scraper).

<a id="config-general"></a>
### General

- **Main Profile (`main_profile`)**: The default profile to use when no profile is specified.
- **Metadata Path (`metadata`)**: Where model metadata/DB files live (supports placeholders).
- **Discord Webhook URL (`discord`)**: Optional webhook for notifications.
  - To send updates to Discord using webhooks, follow the setup guide at `https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks`.
  - You’ll need to add the URL provided in the setup into the config under **General**.
  - After adding it, you can enable Discord updates from **Select Content Areas & Filters → Additional Options**.

Example:
- `main_profile`: `main_profile`
- `metadata`: `{configpath}/{profile}/.data/{model_id}`

<a id="config-file-options"></a>
### File Options

Controls where downloaded content is saved and how folders/files are named.

- **Save Location (`file_options.save_location`)**: Root download directory.
  - Example (Windows): `E:\\Downloads\\OnlyFans`
- **Directory Format (`file_options.dir_format`)**: Folder structure under the save location.
  - Example: `{model_username}/{responsetype}/{mediatype}/`
- **File Format (`file_options.file_format`)**: Filename template.
  - Example: `{filename}.{ext}`
- **Text Length (`file_options.textlength`)**: How much “Text” to keep.
- **Space Replacer (`file_options.space_replacer`)**: Replace spaces in filenames.
- **Date Format (`file_options.date`)**: Date formatting string used in some templates.
  - This uses the **Arrow** date formatting syntax (`arrow.get(...).format(...)`), which is Moment-style tokens (case-sensitive).
  - There is **no whitelist** in the codebase — whatever string you enter is passed straight through to `arrow.format()`.
  - If you use unknown tokens, they generally appear literally in the output.
  - Avoid characters that are invalid in Windows filenames (e.g. `:`, `/`, `\\`, `*`, `?`, `"`).
  - **Examples**:
    - `MM-DD-YYYY` (default in this repo)
    - `YYYY-MM-DD`
    - `YYYY-MM-DD_HH-mm-ss`
    - `YYYY.MM.DD`
    - `ddd_YYYY-MM-DD` (weekday + date)
    - `MMMM-DD-YYYY` (month name + day + year)
    - `YYYY-[W]WW` (ISO week)
  - **Common tokens** (partial list):
    - Year: `YYYY`, `YY`
    - Month: `MM`, `M`, `MMM`, `MMMM`
    - Day: `DD`, `D`, `ddd`, `dddd`
    - Time: `HH`, `H`, `hh`, `h`, `mm`, `m`, `ss`, `s`
    - Timezone: `ZZ`, `Z`
- **Text Type (`file_options.text_type_default`)**: Whether text-length is measured by letters or words.
- **Enable Truncation (`file_options.truncation_default`)**: Whether long names are truncated.

#### File path / directory format placeholders

These placeholders can be used in **Directory Format** and **File Format**.

- `{response_type}`: Posts, Messages, Paid, etc.
- `{post_id}`: ID of post.
- `{media_id}`: ID of media.

- `{file_name}`: The filename; videos will include the quality (e.g., `source`, `720`).
- `{only_file_name}`: The filename; videos will not include quality.
- `{original_filename}`: Filename as sent by OnlyFans (may or may not include `source`).

- `{media_type}`: Images, Audios, Videos.
- `{quality}`: Quality of the media; non-videos will always be `source`.

- `{value}`: The content's value: whether it's categorized as Paid or Free.

- `{model_id}`: Unique identification number for model.
- `{first_letter}`: First letter of model's username.

- `{site_name}`: OnlyFans.
- `{text}`: The text within the media. Truncation of file names has been tested to fit within OS limits; still it's advisable to establish a text length limit.
- `{date}`: The date of the post, output in the config date format.

- `{model_username}`: The model's username.
- `{username}`: The model's username.
- `{profile}`: The currently active profile.
- `{my_username}`: The authorized account's username.
- `{my_id}`: The identification number for the authorized account.
- `{label}`: The label assigned to the post, if available.
- `{download_type}`: Indication of whether it's protected or normal, determined by the necessity for decryption.

- `{current_price}`: Free if current price is 0 dollars else paid.
- `{regular_price}`: Free if regular price is 0 dollars else paid.
- `{promo_price}`: Free if promo price is 0 dollars else paid.
- `{renewal_price}`: Free if renewal price is 0 dollars else paid.

- `{args}`: The passed arguments namespace; keys can be access with the dot (`.`) syntax.
- `{config}`: The config arguments dictionary; keys can be access with the `[]` syntax.
- `{modelObj}`: Model data class via `class` folder; properties can be access via the dot (`.`) syntax.
- `{configPath}`: Path to current config directory.

<a id="config-download"></a>
### Download

- **Min Free Space (MB) (`download_options.system_free_min`)**: Don’t download if disk space is below this.
- **Auto Resume (`download_options.auto_resume`)**: Resume partial downloads when possible.
- **Max Post Count (`download_options.max_post_count`)**: Limit posts to scan (0 = unlimited).

#### FFmpeg (important)
- **FFmpeg Path (`binary_options.ffmpeg`)**: Needed to merge some DRM-protected audio/video streams after decryption.
  - Recommended: **FFmpeg 7.1.1 or lower** from `https://www.gyan.dev/ffmpeg/builds`

Scripts:
- **Post-Download Script (`scripts_options.post_download_script`)**
- **Post Script (`scripts_options.post_script`)**

<a id="config-performance"></a>
### Performance

- **Thread Count (`performance_options.thread_count`)**: Download threads.
- **Download Semaphores (`performance_options.download_sems`)**: Limits concurrency inside the downloader.
- **Download Speed Limit (KB/s) (`performance_options.download_limit`)**: 0 = unlimited.

<a id="config-content"></a>
### Content

Content filtering settings:
- **Block Ads (`content_filter_options.block_ads`)**
- **Max/Min File Size (`content_filter_options.file_size_max` / `file_size_min`)**
  - Examples: `500MB`, `2GB`, or `0` for no limit
- **Max/Min Length (seconds) (`content_filter_options.length_max` / `length_min`)**

<a id="config-cdm"></a>
### CDM

These settings impact DRM-protected content.

- **Key Mode (`cdm_options.key-mode-default`)**:
  - `cdrm`, `cdrm2`, `keydb`, or `manual`
- **KeyDB (`cdm_options.keydb_api`)**:
  - **Status**: **currently not working** (no info on when/if it will become available again).
  - The KeyDB API key field remains in the config for compatibility, but **KeyDB mode should be avoided** for now.
- **Client ID File (`cdm_options.client-id`)** and **Private Key File (`cdm_options.private-key`)**:
  - Required for **manual** CDM keys (DRM scraping)
  - Guide: `https://github.com/FoxRefire/wvg/wiki/How-to-dump-CDM-key-pair-from-AVD`

<a id="config-advanced"></a>
### Advanced

Power-user settings. These options mostly affect **network/signing**, **cache behavior**, and **CLI/automation** flows.

- **Dynamic Mode (`advanced_options.dynamic-mode-default`)**: Controls which source provides the **request-signing rules** used to talk to OnlyFans.
  - If the OnlyFans API changes (auth/signature errors, 401/403 loops), switching this is one of the first things to try.
  - **Valid values** (from code): `datawhores`, `digitalcriminals` (aliases: `dc`, `digital`, `digitals`), `xagler`, `rafa`, `generic`, `manual`
  - **Default fallback**: if an unknown value is set, the app falls back to the default rule source.
  - **Notes**:
    - `manual` expects an embedded dynamic rule (advanced/power-user).
    - `generic` requires a configured generic rules URL in constants (typically used by developers).

- **Backend (`advanced_options.backend`)**: HTTP client library used for network requests.
  - `aio`: aiohttp (async-only)
  - `httpx`: httpx (async + sync in some codepaths)
  - If you see odd connection/proxy/TLS issues, switching backends can help.

- **Cache Mode (`advanced_options.cache-mode`)**: Storage backend for the local cache.
  - **Valid values** (from code): `sqlite`, `json`, `disabled`
  - `sqlite` is generally the best choice for larger caches.
  - `disabled` attempts to turn caching off (useful for troubleshooting), but can reduce performance and may increase API calls.
  - Tip: for “fresh scrape” behavior, the GUI’s “ignore cache / rescrape” options are usually a better fit than disabling the cache globally.

- **Code Execution (`advanced_options.code-execution`)**: Enables `eval()` for certain placeholder “custom values”.
  - **Security warning**: do not enable this if you paste untrusted placeholder content.

- **Download Bars (`advanced_options.downloadbars`)**: Shows per-download progress bars in console output.
  - Can reduce performance at higher thread counts; turn off if the UI/console feels sluggish.

- **Append Log (`advanced_options.appendlog`)**: If enabled, logs append into a single daily file (per profile).
  - If disabled, OF-Scraper writes per-run log files.

- **Sanitize Text (`advanced_options.sanitize_text`)**: Cleans post/message text before inserting it into the database.
  - Helps avoid DB issues caused by unusual characters.
  - This affects what is stored as “text” metadata (and can affect text-based filtering/searching).

- **Remove Hash Match (`advanced_options.remove_hash_match`)**: Controls optional file hashing + duplicate cleanup.
  - `None`: do not hash files (fastest)
  - `False`: hash files, but **do not delete** duplicates
  - `True`: hash files and **remove duplicate files** (deletes extra copies of identical content)
  - Warning: deletion is permanent; use carefully.

- **Enable Auto After (`advanced_options.enable_auto_after`)**: Speeds up future scrapes by automatically setting an “after” cutoff based on previous scans.
  - Requires caching/DB information; turning this off forces more full-history scans.
  - If you feel you’re missing older content, disable it temporarily and run a full scan.

- **Temp Directory (`advanced_options.temp_dir`)**: Optional directory to store temporary download files.
  - Leave empty to use the default temp/save location behavior.

- **Infinite Loop (Action Mode) (`advanced_options.infinite_loop_action_mode`)**: When enabled, “action mode” runs can loop and prompt to continue.
  - Mostly affects CLI automation flows (running actions repeatedly without restarting the program).

- **Default User List / Black List (`advanced_options.default_user_list` / `default_black_list`)**: Default model lists to include/exclude when retrieving creators.
  - Format: comma-separated list names (case-insensitive)
  - Built-ins: `main`, `active`, `expired` (also supports `ofscraper.main`, etc.)

<a id="config-response-type"></a>
### Response Type

Maps internal response types to display names / aliases.

---

<a id="table-root"></a>
## Table / Scraping page

This is where scraped rows appear, filters are applied, and downloads are queued.

<a id="table-toolbar"></a>
### Toolbar buttons
- **Filters**: Show/hide the left filter sidebar.
- **Reset**: Reset filters.
- **Apply Filters**: Apply the current filter state.
- **Start Scraping >>**: Begin scraping the selected areas/models.
- **New Scrape**: Return to the beginning.
  - If scraping is active, you’ll be asked if you want to cancel first.
- **Stop Daemon**: Stops daemon mode if enabled.
- **Select All / Deselect All**: Controls the download cart selection.
- **>> Send Downloads**: Queues selected rows for downloading.

<a id="table-progress"></a>
### Progress + logs
- The **overall progress bar** is shown in the footer at the bottom.
- The console area shows detailed logs and trace output.

<a id="filters-root"></a>
## Filters (Table page + embedded on Areas page)

<a id="filters-text-search"></a>
### Text Search
- **Search text content…**: Filters rows based on the “Text” column.
- **Full string match**: Uses a full-match (regex-style) match instead of substring search.

Example:
- Search `promo` to show only rows whose text contains “promo”.

<a id="filters-media-type"></a>
### Media Type
Filter rows by media type: **Audios**, **Images**, **Videos**.

<a id="filters-response-type"></a>
### Response Type
Filter rows by where they came from: **Pinned**, **Archived**, **Timeline**, **Stories**, **Highlights**, **Streams**.

<a id="filters-status"></a>
### Status (Downloaded / Unlocked)

#### Downloaded
- **True**: File is downloaded.
- **False**: Not downloaded.
- **No (Paid)**: Not downloadable as-is (often paywalled).

<a id="unlocked-meanings"></a>
#### Unlocked (important)
The **Unlocked** column is not a direct 1:1 match with “purchased”.

- **Locked**: Not viewable (paywalled).
- **Preview**: Viewable teaser/preview media for a priced item.
- **Included**: Viewable media inside a priced message **without purchasing** (e.g., teaser media that OnlyFans still marks as viewable even though the message is priced).
- **True**: Treated as fully unlocked/accessible (typically purchased / opened content).
- **False**: Known to be not-unlocked in the data source/DB.

<a id="filters-date-range"></a>
### Post Date Range
Enable and choose From/To to filter by post date.

<a id="filters-duration"></a>
### Duration (Length)
Enable and choose min/max to filter by video length.

<a id="filters-price"></a>
### Price Range
Filter by min/max price. “Free” items typically show as `Free`.

<a id="filters-id"></a>
### ID Filters
Exact-match filters for:
- **Media ID**
- **Post ID**
- **Post Media Count**
- **Other Posts w/ Media**

<a id="filters-username"></a>
### Username
Filter rows by model username.

Tips:
- Search supports comma-separated terms (e.g. `alice, bob, charlie`).

---

<a id="table-columns"></a>
## Table columns (what each one means)

The table is a flattened view of scraped media rows.

<a id="table-col-number"></a>
### Number
Row index.

<a id="table-col-download-cart"></a>
### Download Cart
State of the row in the download queue/cart.

<a id="download-cart-meanings"></a>
Possible values:
- `[]`: not selected
- `[added]`: queued for download
- `[downloading]`: currently downloading
- `[downloaded]`: finished
- `[failed]`: download failed

Tip:
- Click the **Download Cart** cell to toggle selection.

<a id="table-col-username"></a>
### UserName
The creator/model username.

<a id="table-col-downloaded"></a>
### Downloaded
Whether the file is already downloaded (`True`/`False`) or not applicable (`N/A`).

<a id="table-col-unlocked"></a>
### Unlocked
See **Unlocked (important)** above for label meanings.

<a id="table-col-other-posts"></a>
### other posts with media
Count/indicator related to other posts that also contain this media.

<a id="table-col-length"></a>
### Length
Media duration (videos), otherwise `N/A`.

<a id="table-col-mediatype"></a>
### Mediatype
`videos`, `images`, or `audios`.

<a id="table-col-post-date"></a>
### Post Date
Date/time for the post/message entry.

<a id="table-col-post-media-count"></a>
### Post Media Count
How many media items are attached to that post/message.

<a id="table-col-responsetype"></a>
### Responsetype
Source type (e.g., `timeline`, `message`, `pinned`, etc.).

<a id="table-col-price"></a>
### Price
Price of the post/message (often `Free` or a number).

<a id="table-col-post-id"></a>
### Post ID
ID of the post/message container.

<a id="table-col-media-id"></a>
### Media ID
ID of the specific media item.

<a id="table-col-text"></a>
### Text
Text/description associated with the post/message (may be truncated).

---

<a id="merge-dbs"></a>
## Merge DBs

1. Pick a **Source Folder** containing one or more `user_data.db` files.
2. Pick a **Destination** folder for the merged output.
3. Click **Start Merge** (back up first).

---

<a id="troubleshooting"></a>
## Troubleshooting notes

- If you purge files/DB and immediately start a download scrape, folders/databases may be recreated right away.
- For some message/PPV entries, “viewable/unlocked” may not map 1:1 to “purchased”.

