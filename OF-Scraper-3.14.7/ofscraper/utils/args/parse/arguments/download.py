import cloup as click
from humanfriendly import parse_size

no_auto_resume_option = click.option(
    "-ar",
    "--no-auto-resume",
    help="Cleanup temp .part files (removes resume ability)",
    default=False,
    is_flag=True,
)

show_download_bars_option = click.option(
    "-db",
    "--downloadbars",
    "--download-bars",
    "--download-bar",
    "downloadbars",
    help="Show individual download progress bars",
    default=False,
    is_flag=True,
)

download_sem_option = click.option(
    "-sd",
    "--downloadsem",
    "--downloadsems",
    "--download-sems"
    "--download-sem",
    "--sems",
    "--sem",
    "download_sem",
    help="Number of concurrent downloads per thread",
    default=None,
    type=int,
)

download_limit_option = click.option(
    "-dl",
    "--download-limit",
    "download_limit",
    help="""
    \b
    Maximum download speed per second
    can parse Human readable string '10MB' or int representing bytes per second
    """,
    default=None,
    type=parse_size,
)

allow_dupe_downloads_option = click.option(
    "-ad",
    "--allow-dupe-downloads",
    "--allow-dupes",
    "allow_dupe_downloads",
    help="Allow duplicates (do NOT skip duplicates; treat reposts as new items)",
    default=False,
    is_flag=True,
)

keep_message_purchased_dupes_option = click.option(
    "--keep-message-purchased-dupes",
    "keep_message_purchased_dupes",
    help=(
        "With --allow-dupe-downloads: also keep the same media from both Messages "
        "and Purchased. Default is to keep Messages only for that overlap."
    ),
    default=False,
    is_flag=True,
)
