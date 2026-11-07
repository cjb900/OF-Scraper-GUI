import arrow
import pytest
from click.exceptions import BadParameter

from ofscraper.utils.args.types.arrow import ArrowType


@pytest.mark.parametrize("value", ["2021-05-01", "05/01/2021", "5/1/2021"])
def test_absolute_dates_parse_including_the_documented_format(value):
    # --before/--after document MM/DD/YYYY
    assert ArrowType().convert(value, None, None).date() == arrow.get("2021-05-01").date()


@pytest.mark.parametrize(
    "value, shift",
    [
        ("1 minute ago", {"minutes": -1}),
        ("2 minutes ago", {"minutes": -2}),
        ("1 second ago", {"seconds": -1}),
        ("3 weeks ago", {"weeks": -3}),
        ("1 day ago", {"days": -1}),
    ],
)
def test_relative_dates_parse(value, shift):
    expected = arrow.now().shift(**shift)
    result = ArrowType().convert(value, None, None)
    # generous tolerance: the two clocks are read a moment apart
    assert abs((result - expected).total_seconds()) < 30


@pytest.mark.parametrize(
    "value, shift",
    [("1 hour ago", {"hours": -1}), ("2 hours ago", {"hours": -2})],
)
def test_relative_hours_parse(value, shift):
    expected = arrow.now().shift(**shift)
    result = ArrowType().convert(value, None, None)
    assert abs((result - expected).total_seconds()) < 30


@pytest.mark.parametrize(
    "value",
    ["25/12/2024", "13/01/2021", "02/30/2024", "2021-13-01", "yesterday", "garbage"],
)
def test_bad_dates_give_a_usage_error_not_a_crash(value):
    with pytest.raises(BadParameter) as info:
        ArrowType().convert(value, None, None)
    assert "MM/DD/YYYY" in str(info.value.message)
