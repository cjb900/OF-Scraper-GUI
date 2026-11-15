import logging

from aiolimiter import AsyncLimiter
import ofscraper.utils.settings as settings

CHUNK_SIZE = 10 * 1024 * 1024
# Older GUI versions saved the KB/s number as typed, but the setting is in bytes
# per second. Nothing used the limit back then, so it went unnoticed. A number
# saved that way can't be told apart from a real limit, so warn about low ones.
LOW_LIMIT_WARNING_BYTES = 100_000
_warned_low_limit = False


def warn_if_limit_looks_too_low():
    """Warn once per run about a low limit from the config, not from the
    command line, where it was chosen on purpose."""
    global _warned_low_limit
    limit = settings.get_settings().download_limit
    if _warned_low_limit or not 0 < limit < LOW_LIMIT_WARNING_BYTES:
        return
    if getattr(settings.get_args(), "download_limit", None):
        return
    _warned_low_limit = True
    logging.getLogger("shared").warning(
        f"The download speed limit is {max(1, round(limit / 1000))} KB/s, so "
        "downloads will be slow. Older GUI versions saved this setting in the "
        "wrong unit, so a limit set back then may now be far lower than you "
        "meant. Check Download Speed Limit in Configuration, under Performance, "
        "or download_limit in config.json. Ignore this if the limit is what "
        "you want."
    )


class LeakyBucket(AsyncLimiter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def acquire(self, amount: float = 1):
        if settings.get_settings().download_limit <= 0:
            return
        amount = amount or CHUNK_SIZE
        # AsyncLimiter refuses more than one period's worth at once, and a
        # chunk can be bigger than the limit (metadata reads 30 MB chunks)
        while amount > self.max_rate:
            await super().acquire(self.max_rate)
            amount -= self.max_rate
        await super().acquire(amount)
