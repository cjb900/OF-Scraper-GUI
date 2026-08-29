from typing import Iterable
import copy
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
        # Internal dictionary to store posts, using post_id as the key for de-duplication
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

    @property
    def all_unique_media(self) -> list:
        """
        Takes ALL media from the collection and applies a specific, short
        sequence of download-related filters.

        Returns:
            list: A list of unique Media objects.
        """
        log.info("Filtering all media with specific download filter sequence...")

        # Start with every piece of media in the collection
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
        added_posts_list = []
        for item in items:
            # Call the single-item processor
            post = self._process_and_add_post(item, actions, overwrite)
            if post:  # You can track how many were successfully added
                new_posts_added += 1
                added_posts_list.append(post)

        if new_posts_added > 0:
            log.info(f"Added {new_posts_added} posts to the collection")
            try:
                from ofscraper.plugins.manager import plugin_manager
                plugin_manager.dispatch_event("on_posts_collected", added_posts_list, self.username)
            except Exception as e:
                log.warning(f"Failed to dispatch on_posts_collected to plugins: {e}")

    def get_media_to_download(self) -> list:
        """
        Gets the final, filtered list of media for DOWNLOAD mode.
        """
        filtersettings = settings.get_settings().mediatypes
        log.debug(f"filtering Media to {','.join(filtersettings)}")

        all_media = self._get_prepared_media_from_download_candidates()

        log.info("Applying final 'download' mode filters to media list...")
        all_media = helpers.seperate_self(all_media)
        # When allow_dupe_downloads is on, skip full media_id collapse so reposts
        # are preserved — but still optionally drop Messages↔Purchased overlap.
        allow_dupes = bool(getattr(settings.get_settings(), "allow_dupe_downloads", False))
        if not allow_dupes:
            all_media = helpers.dupefiltermedia(all_media)
        else:
            all_media = helpers.apply_allow_dupe_media_policy(all_media)
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
        all_media = helpers.seperate_self(all_media)
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

        # --- NEW LOGIC: Strict Media Linkage ---
        # By default, mediatypes contains all 3: ['Images', 'Audios', 'Videos']
        # If the length is less than 3, the user explicitly filtered for a specific media type.
        # We drop any posts that don't actually contain surviving media matching their filter!
        active_media_types = settings.get_settings().mediatypes or []
        if len(active_media_types) < 3:
            posts_for_text = [p for p in posts_for_text if len(p.media) > 0]

        posts_for_text = helpers.final_post_sort(posts_for_text)

        log.info(
            f"Found {len(posts_for_text)} posts for text download after final filtering."
        )
        return posts_for_text

    def get_rows_for_gui_table(self) -> list:
        """
        Build GUI table row dicts from this collection's media list.
        Shows ALL rows including duplicates (same media appearing in multiple API
        areas like Timeline + Archived) and locked/paid items that won't download.
        Also computes the duplicate count and stores it in the postcollection module
        so the Scrape Summary can report it as "| duplicates: N".
        Delegates to the GUI workflow builder; returns [] when GUI is not active.
        """
        try:
            from ofscraper.gui.utils.workflow import _build_media_rows
            global _gui_duplicate_count
            raw = self.raw_all_media
            # Compute duplicate count for Scrape Summary (raw rows minus unique by media_id)
            seen = set()
            unique_count = 0
            for m in raw:
                mid = getattr(m, "id", None)
                key = mid if mid is not None else id(m)
                if key not in seen:
                    seen.add(key)
                    unique_count += 1
            _gui_duplicate_count = len(raw) - unique_count
            return _build_media_rows(raw, self.username or "")
        except Exception as e:
            log.debug(f"get_rows_for_gui_table failed: {e}")
            return []


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

        When allow_dupe_downloads is True, ``raw_posts`` is used so the same
        *media_id* on different posts (true reposts) can generate separate
        download entries (``_dup_seq`` avoids temp-name collisions).

        The same post_id is often appended to ``raw_posts`` once per API area
        (e.g. Messages + Purchased). Those are not real reposts — they must not
        create a second download of the identical (media_id, post_id) pair.
        """
        allow_dupes = bool(getattr(settings.get_settings(), "allow_dupe_downloads", False))
        keep_msg_paid = bool(
            getattr(settings.get_settings(), "keep_message_purchased_dupes", False)
        )
        if allow_dupes:
            candidate_posts = [
                post for post in self.raw_posts if post.is_download_candidate
            ]
            # Same post_id scraped from multiple areas lands in raw_posts repeatedly
            # (often as the *same* Post object). Unless the user explicitly wants
            # Messages+Purchased copies, collapse to one post per id before media
            # aggregation — otherwise Allow duplicates double-downloads into the
            # first area's folder (usually Messages).
            if not keep_msg_paid:
                seen_post_ids = set()
                unique_posts = []
                for post in candidate_posts:
                    pid = getattr(post, "id", None)
                    if pid is not None and pid in seen_post_ids:
                        continue
                    if pid is not None:
                        seen_post_ids.add(pid)
                    unique_posts.append(post)
                candidate_posts = unique_posts
        else:
            candidate_posts = [post for post in self.posts if post.is_download_candidate]
        log.info(f"Found {len(candidate_posts)} posts marked as download candidates.")

        prepared_ids = set()
        for post in candidate_posts:
            if id(post) not in prepared_ids:
                post.prepare_media_for_download()
                prepared_ids.add(id(post))

        from ofscraper.filters.media.message_purchased_dupes import media_response_bucket

        seen_media_ids = set()
        seen_media_post_pairs = set()
        all_media = []
        skipped_exact = 0
        for post in candidate_posts:
            for media in post.media_to_download:
                media_key = media.id if media.id is not None else id(media)
                post_id = getattr(media, "post_id", None)
                # When keeping Messages+Purchased copies, distinguish by area bucket
                # so the same post_id can download once per area folder.
                if keep_msg_paid:
                    pair = (
                        media_key,
                        post_id,
                        media_response_bucket(getattr(media, "responsetype", None)),
                    )
                else:
                    pair = (media_key, post_id)
                if pair in seen_media_post_pairs:
                    skipped_exact += 1
                    continue
                seen_media_post_pairs.add(pair)

                if media_key not in seen_media_ids:
                    seen_media_ids.add(media_key)
                    all_media.append(media)
                else:
                    if not (getattr(media, "url", None) or getattr(media, "mpd", None)):
                        continue
                    dup = copy.copy(media)
                    dup._dup_seq = len(all_media)
                    all_media.append(dup)
        if skipped_exact:
            log.debug(
                f"Skipped {skipped_exact} exact (media_id, post_id) duplicate(s) "
                f"from multi-area raw_posts"
            )
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
            log.info(f"Skipping item because it's missing an 'id': {post_to_process}")
            return None

        # Perform the core logic of adding/updating the post
        if post_id not in self._posts_map or overwrite:
            post_object = (
                post_to_process
                if isinstance(post_to_process, Post)
                else Post(post_to_process, self.model_id, self.username, mode=self.mode)
            )
            self._posts_map[post_id] = post_object

        existing_post = self._posts_map[post_id]
        to_append = existing_post
        # Messages + Purchased often share the same post id. Keep the first Post in
        # _posts_map, but when the user opts to keep both area copies, also append
        # the incoming Post (different responsetype) to raw_posts for download.
        if (
            isinstance(post_to_process, Post)
            and post_to_process is not existing_post
        ):
            try:
                keep_both = bool(
                    getattr(
                        settings.get_settings(), "keep_message_purchased_dupes", False
                    )
                )
            except Exception:
                keep_both = False
            if keep_both:
                from ofscraper.filters.media.message_purchased_dupes import (
                    media_response_bucket,
                )

                in_b = media_response_bucket(post_to_process.responsetype)
                ex_b = media_response_bucket(existing_post.responsetype)
                if {in_b, ex_b} == {"messages", "purchased"}:
                    to_append = post_to_process

        self._raw_posts.append(to_append)

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


# Module-level counter written by get_rows_for_gui_table(); read by Scrape Summary.
_gui_duplicate_count = 0
