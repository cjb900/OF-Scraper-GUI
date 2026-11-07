import re

import arrow
import cloup as click


class ArrowType(click.ParamType):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def convert(self, value, param, ctx):
        out = super().convert(value, param, ctx)
        if not out:
            return out
        # ParserError is a ValueError. A plain ValueError means the text looked
        # like a date but isn't one, such as 25/12/2024 for MM/DD/YYYY.
        try:
            return arrow.get(str(out))
        except ValueError:
            pass
        try:
            # --before/--after document MM/DD/YYYY, which arrow.get() doesn't parse
            return arrow.get(str(out), ["MM/DD/YYYY", "M/D/YYYY"])
        except ValueError:
            pass
        x = str(out)
        x = re.sub("\\byear\\b", "years", x)
        x = re.sub("\\bday\\b", "days", x)
        x = re.sub("\\bmonth\\b", "months", x)
        x = re.sub("\\bweek\\b", "weeks", x)
        x = re.sub("\\bhour\\b", "hours", x)
        x = re.sub("\\bminute\\b", "minutes", x)
        x = re.sub("\\bsecond\\b", "seconds", x)
        try:
            return arrow.now().dehumanize(x)
        except ValueError:
            self.fail(
                f"{out!r} isn't a date. Use MM/DD/YYYY, YYYY-MM-DD or a relative "
                "date such as '2 days ago'.",
                param,
                ctx,
            )

    @property
    def name(self):
        return "Arrow"
