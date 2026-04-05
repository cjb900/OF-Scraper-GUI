from typing import Iterable
import logging
import ofscraper.filters.media.filters as helpers
import ofscraper.utils.settings as settings
from ofscraper.classes.of.posts import Post
from ofscraper.classes.of.media import Media


log = logging.getLogger("shared")


def _format_length_display(value):
    """Format duration into DD:HH:MM:SS for GUI display."""
    if value in (None, '', 'N/A'):
        return 'N/A'
    try:
        total_seconds = int(float(value))
    except Exception:
        return str(value)
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{days:02d}:{hours:02d}:{minutes:02d}:{seconds:02d}"


class PostCollection:
    """
    Manages a collection of Post objects for GUI/table building and downloads.

    Important: when GUI "allow duplicates" is enabled, we preserve repeated
    post instances for table/display purposes so reposts and paid/locked rows
    remain visible the way older GUI builds exposed them.
    """

    def __init__(self, model_id=None, username=None, mode="download"):
        """
        Initializes an empty collection for posts.

        Args:
            model_id (int, optional): The model's ID. Defaults to None.
            username (str, optional): The model's username. Defaults to None.
            mode (str, optional): The operating mode ('download' or 'metadata'). Defaults to 'download'.
        """
        self.username = username
        self.model_id = model_id
        self.mode = mode
        # Map of canonical posts by post_id for download/like pipelines.
        self._posts_map = {}
        # Ordered raw list preserving all added post instances for GUI/table use.
        self._raw_posts = []
        log.info(f"Initialized PostCollection for {username}")

    @property
    def posts(self) -> list[Post]:
        """Returns a list of the unique Post objects in the collection."""
        return list(self._posts_map.values())

    @property
    def raw_posts(self) -> list[Post]:
        """Returns posts in insertion order, preserving duplicates/reposts."""
        return list(self._raw_posts)

    @property
    def all_media(self) -> list:
        """
        Collects EVERY media item from EVERY unique post in the collection.
        This is the canonical list used by the core processing pipeline.
        """
        return [media for post in self.posts for media in post.all_media]

    @property
    def raw_all_media(self) -> list:
        """Collects media from all inserted posts, preserving duplicates/reposts."""
        return [media for post in self.raw_posts for media in post.all_media]


    def get_rows_for_gui_table(self) -> list[dict]:
        """Build GUI table rows directly from raw post/media payloads.

        This avoids relying on partially-normalized Media objects for table display.
        The GUI table is about *what was found*, not only the final download queue.
        """
        rows = []
        candidate_posts = [post for post in self.raw_posts if post.is_download_candidate]
        log.info(f"Found {len(candidate_posts)} raw posts marked as download candidates for GUI row building.")

        for post in candidate_posts:
            raw_post = getattr(post, '_post', {}) or {}
            raw_media_list = raw_post.get('media') or []
            responsetype = str(getattr(post, 'responsetype', '') or raw_post.get('responseType') or '')
            post_id = getattr(post, 'id', None) or raw_post.get('id') or ''
            text = getattr(post, 'db_sanitized_text', None) or getattr(post, 'text', None) or raw_post.get('text') or raw_post.get('rawText') or ''
            price = getattr(post, 'price', 0) or float(raw_post.get('price') or 0)
            preview = bool(getattr(post, 'preview', False) or raw_post.get('preview', False))
            opened = bool(getattr(post, 'opened', True) if getattr(post, 'opened', None) is not None else raw_post.get('isOpened', True))
            post_date = getattr(post, 'formatted_date', None) or raw_post.get('postedAt') or raw_post.get('createdAt') or ''
            post_media_count = len(raw_media_list)

            for raw_media in raw_media_list:
                media_id = raw_media.get('id') or ''
                canview = bool(raw_media.get('canView', True))
                downloaded = bool(raw_media.get('downloaded', False))
                media_type = str(raw_media.get('type') or raw_media.get('mediaType') or raw_media.get('mimetype') or 'unknown')
                media_type_lower = media_type.lower()
                source_url = str(
                    raw_media.get('source')
                    or raw_media.get('src')
                    or raw_media.get('files', {}).get('full', {}).get('url')
                    or raw_media.get('files', {}).get('preview', {}).get('url')
                    or ''
                )
                if media_type_lower in ('photo', 'image'):
                    media_type = 'Images'
                elif media_type_lower in ('video',):
                    media_type = 'Videos'
                elif media_type_lower in ('audio',):
                    media_type = 'Audios'
                elif source_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    media_type = 'Images'
                elif source_url.lower().endswith(('.mp4', '.m4v', '.mov', '.mpd', '.m3u8')):
                    media_type = 'Videos'
                elif source_url.lower().endswith(('.mp3', '.m4a', '.wav', '.ogg')):
                    media_type = 'Audios'
                else:
                    media_type = 'unknown'

                duration = raw_media.get('duration') or raw_media.get('sourceDuration') or 'N/A'

                if not canview:
                    cart_status = 'Locked'
                    dl_display = 'N/A'
                    ul_display = 'Locked'
                else:
                    cart_status = '[downloaded]' if downloaded else '[]'
                    dl_display = str(bool(downloaded))
                    if price > 0 and responsetype.lower() in ('message', 'messages') and not opened:
                        ul_display = 'Preview' if preview else 'Included'
                    else:
                        ul_display = 'Preview' if (preview and price > 0) else 'True'

                rows.append({
                    'index': len(rows),
                    'number': str(len(rows) + 1),
                    'download_cart': cart_status,
                    'username': self.username,
                    'downloaded': dl_display,
                    'unlocked': ul_display,
                    'other_posts_with_media': [],
                    'post_media_count': post_media_count,
                    'mediatype': media_type,
                    'post_date': post_date,
                    'length': _format_length_display(duration),
                    'responsetype': responsetype,
                    'price': 'Free' if price == 0 else '{:.2f}'.format(price),
                    'post_id': post_id,
                    'media_id': media_id,
                    'text': text,
                })

        log.info(f"Returning {len(rows)} raw GUI table rows from post/media payloads.")
        return rows

    @property
    def all_unique_media(self) -> list:
        """
        Takes ALL media from the collection and applies a specific, short
        sequence of download-related filters.

        Returns:
            list: A list of unique Media objects.
        """
        log.info("Filtering all media with specific download filter sequence...")

        # Keep the actual download/filter pipeline canonical and close to stock
        # 3.14.3 behavior. Raw-post handling is reserved for GUI table display.
        media_to_filter = self.all_media

        # Apply the exact filter sequence you requested
        filtered_media = helpers.dupefiltermedia(media_to_filter)
        log.info(f"Returning {len(filtered_media)} items after specific filtering.")
        return filtered_media

    def get_media_by_types(self, mediatypes: list[str] or str) -> list:
        """
        Filters all media in the collection by one or more media types.

        Args:
            mediatypes (list[str] or str): A string (e.g., 'videos') or a list of strings
                                        (e.g., ['images', 'gifs']) to filter by.

        Returns:
            list: A flat list of all Media objects that match the given type(s).
        """
        if isinstance(mediatypes, str):
            mediatypes = [mediatypes]

        # Use a set for efficient lookup, and normalize to lowercase for robust matching
        target_types = {t.lower() for t in mediatypes}

        all_media = self.all_media  # Use the existing property to get all media

        # Return a new list containing only media of the matching types
        return [media for media in all_media if media.mediatype.lower() in target_types]

    def add_post(self, item, actions: list[str] = None, overwrite=False):
        """
        Adds a single item (Post, Media, or dict) and returns the resulting Post object.
        """
        if isinstance(item, Iterable):
            raise Exception("item must not be a iteratable")
        return self._process_and_add_post(item, actions or [], overwrite=overwrite)

    def add_posts(self, items: list, actions: list[str] = None, overwrite=False):
        """
        Adds a list of items (Posts, Media, or dicts) to the collection.
        """
        if not isinstance(items, list):
            items = [items]
        actions = actions or []
        new_posts_added = 0
        for item in items:
            # Call the single-item processor
            post = self._process_and_add_post(item, actions, overwrite)
            if post:  # You can track how many were successfully added
                new_posts_added += 1

        if new_posts_added > 0:
            log.info(f"Added {new_posts_added} posts to the collection")

    def get_media_for_gui_table(self) -> list:
        """
        Returns media for GUI table display using normalized/canonical media
        objects so GUI columns keep rich metadata, while still preserving
        reposts/duplicates when requested.
        """
        candidate_posts = [post for post in self.posts if post.is_download_candidate]
        raw_candidate_posts = [post for post in self.raw_posts if post.is_download_candidate]
        log.info(f"Found {len(raw_candidate_posts)} raw posts marked as download candidates for GUI table.")

        for post in candidate_posts:
            try:
                post.prepare_media_for_download()
            except Exception:
                pass

        canonical_media = []
        for post in candidate_posts:
            canonical_media.extend(getattr(post, "post_media", []) or [])
        if not canonical_media:
            for post in candidate_posts:
                canonical_media.extend(getattr(post, "all_media", []) or [])

        allow_dupes = bool(getattr(settings.get_settings(), "allow_dupe_downloads", False))
        if allow_dupes:
            # Build duplicate-preserving display rows by replaying canonical media per raw post
            # using 3.14.x identifiers (`media.post_id`, `post.id`).
            by_key = {}
            for media in canonical_media:
                key = (
                    str(getattr(media, 'post_id', getattr(media, 'postid', ''))),
                    str(getattr(media, 'id', '')),
                    str(getattr(media, 'responsetype', '')),
                )
                by_key.setdefault(key, []).append(media)

            ordered_media = []
            for post in raw_candidate_posts:
                post_id = str(getattr(post, 'id', getattr(post, 'postid', '')))
                source_media = getattr(post, 'post_media', []) or getattr(post, 'all_media', []) or []
                for raw_media in source_media:
                    raw_post_id = str(getattr(raw_media, 'post_id', post_id))
                    key = (
                        raw_post_id,
                        str(getattr(raw_media, 'id', '')),
                        str(getattr(raw_media, 'responsetype', getattr(post, 'responsetype', ''))),
                    )
                    matches = by_key.get(key)
                    if matches:
                        ordered_media.append(matches[0])
                    else:
                        ordered_media.append(raw_media)
            media = ordered_media
        else:
            media = helpers.dupefiltermedia(canonical_media)

        media = helpers.ele_count_filter(media)
        media = helpers.final_media_sort(media)
        log.info(f"Returning {len(media)} media items for GUI table display.")
        return media

    def get_media_to_download(self) -> list:
        """
        Gets the final, filtered list of media for DOWNLOAD mode.
        """
        filtersettings = settings.get_settings().mediatypes
        log.debug(f"filtering Media to {','.join(filtersettings)}")

        all_media = self._get_prepared_media_from_download_candidates()

        log.info("Applying final 'download' mode filters to media list...")
        all_media = helpers.dupefiltermedia(all_media)
        all_media = helpers.previous_download_filter(
            all_media, username=self.username, model_id=self.model_id
        )
        all_media = helpers.ele_count_filter(all_media)
        all_media = helpers.final_media_sort(all_media)

        log.info(f"Returning {len(all_media)} final media items for download.")
        return all_media

    def get_media_for_metadata(self) -> list:
        """
        Gets the final, filtered list of media for METADATA mode.
        """
        all_media = self._get_prepared_media_for_metadata()

        log.info("Applying final 'metadata' mode filters to media list...")
        all_media = helpers.previous_download_filter(
            all_media, username=self.username, model_id=self.model_id
        )
        all_media = helpers.ele_count_filter(all_media)
        all_media = helpers.final_media_sort(all_media)

        log.info(f"Returning {len(all_media)} final media items for metadata.")
        return all_media

    def get_media_for_processing(self):
        if settings.get_settings().command == "metadata":
            return self.get_media_for_metadata()
        else:
            return self.get_media_to_download()

    def get_posts_to_like(self) -> list[Post]:
        """
        Gets the final, filtered list of posts to be liked. This method is now
        self-contained and includes the full preparation and filtering pipeline.
        """
        # 1. Determine the action type ('like' or 'unlike') from settings.
        like_action = None
        if "like" in settings.get_settings().actions:
            like_action = True
        elif "unlike" in settings.get_settings().actions:
            like_action = False
        else:
            # If neither action is specified, there's nothing to do.
            log.debug(
                "Skipping like filtering because 'like' or 'unlike' not in actions."
            )
            return []

        like_candidates = [post for post in self.posts if post.is_like_candidate]
        log.info(f"Found {len(like_candidates)} posts in areas eligible for liking.")

        actionable_posts = []
        for post in like_candidates:
            post.prepare_post_for_like(like_action=like_action)
            if post.is_actionable_like:
                actionable_posts.append(post)
        log.debug(f"{len(actionable_posts)} posts are actionable for liking.")

        final_posts_to_like = helpers.sort_by_date(actionable_posts)
        final_posts_to_like = helpers.dupefilterPost(final_posts_to_like)
        final_posts_to_like = helpers.temp_post_filter(final_posts_to_like)
        final_posts_to_like = helpers.final_post_sort(final_posts_to_like)

        log.info(f"Returning {len(final_posts_to_like)} final posts to be liked.")
        return final_posts_to_like

    def get_posts_for_text_download(self) -> list[Post]:
        """
        Filters the list of text candidates to get the final list of posts
        whose text should be downloaded.
        """
        if "download" not in settings.get_settings().actions:
            return []
        if not settings.get_settings().text:
            return []
        text_candidates = [post for post in self.posts if post.is_text_candidate]
        log.info(
            f"Found {len(text_candidates)} posts in areas eligible for text download."
        )

        posts_for_text = helpers.sort_by_date(text_candidates)
        posts_for_text = helpers.dupefilterPost(posts_for_text)
        posts_for_text = helpers.temp_post_filter(posts_for_text)
        posts_for_text = helpers.post_text_filter(posts_for_text)
        posts_for_text = helpers.post_neg_text_filter(posts_for_text)
        posts_for_text = helpers.mass_msg_filter(posts_for_text)
        posts_for_text = helpers.final_post_sort(posts_for_text)

        log.info(
            f"Found {len(posts_for_text)} posts for text download after final filtering."
        )
        return posts_for_text

    def update_info(self, username: str = None, model_id: str = None):
        if username:
            self.username = username
        if model_id:
            self.model_id = model_id

    def find_all_media_with_id(self, id):
        found = list(filter(lambda x: x.id == id, self.all_media))
        return found

    def times_media_id_found(self, id):
        return len(list(filter(lambda x: x.id == id, self.all_media)))

    def find_media_item(self, id):
        found = self.find_all_media_with_id(id)
        if len(found) > 0:
            return found[0]

    def posts_with_media_id(self, id):
        found = self.find_all_media_with_id(id)
        return list(set(map(lambda x: x.post_id, found)))

    def _get_prepared_media_from_download_candidates(self) -> list:
        """
        Private helper to get download candidates, run per-post filtering,
        and return the aggregated list of media before final filtering.
        """
        candidate_posts = [post for post in self.posts if post.is_download_candidate]
        log.info(f"Found {len(candidate_posts)} posts marked as download candidates.")

        for post in candidate_posts:
            post.prepare_media_for_download()

        all_media = [
            media for post in candidate_posts for media in post.media_to_download
        ]
        log.debug(f"Aggregated {len(all_media)} media items before final filtering.")
        return all_media

    def _get_prepared_media_for_metadata(self) -> list:
        """
        Private helper for getting METADATA candidates.
        """
        # This uses the specific metadata flag
        candidate_posts = [post for post in self.posts if post.is_metadata_candidate]
        log.info(f"Found {len(candidate_posts)} posts marked as metadata candidates.")
        for post in candidate_posts:
            post.prepare_media_for_metadata()

        all_media = [
            media for post in candidate_posts for media in post.media_for_metadata
        ]
        log.debug(f"Aggregated {len(all_media)} media items for metadata processing.")
        return all_media

    def _process_and_add_post(self, item, actions: list[str], overwrite: bool):
        """
        Processes a single item (Post, Media, or dict), adds it to the
        collection, and returns the definitive Post object. This is the
        core internal logic.
        """
        post_to_process, post_id = None, None

        # Resolve the item to its core Post data and ID
        if isinstance(item, Media):
            post_to_process = item.post
        elif isinstance(item, (Post, dict)):
            post_to_process = item
        else:
            log.info(f"Skipping item of invalid type: {type(item)}")
            return None

        post_id = (
            post_to_process.id
            if isinstance(post_to_process, Post)
            else post_to_process.get("id")
        )

        if not post_id:
            log.info(
                f"Skipping item because it's missing an 'id': {post_to_process}"
            )
            return None

        # Materialize a Post object for raw insertion tracking.
        incoming_post = (
            post_to_process
            if isinstance(post_to_process, Post)
            else Post(post_to_process, self.model_id, self.username, mode=self.mode)
        )
        self._raw_posts.append(incoming_post)

        # Perform the core logic of adding/updating the canonical post map.
        if post_id not in self._posts_map or overwrite:
            self._posts_map[post_id] = incoming_post

        existing_post = self._posts_map[post_id]

        # Set eligibility flags
        if "like" in actions:
            existing_post.is_like_candidate = True
        if "download" in actions:
            existing_post.is_download_candidate = True
        if "text" in actions:
            existing_post.is_text_candidate = True
        if "metadata" in actions:
            existing_post.is_metadata_candidate = True
        return existing_post
