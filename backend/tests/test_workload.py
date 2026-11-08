import pytest

from workload import get_load_level


@pytest.mark.parametrize(
    ("lesson_count", "expected_level"),
    [
        (0, None),
        (1, 4),
        (2, 4),
        (3, 4),
        (4, 3),
        (5, 2),
        (6, 1),
        (7, 0),
        (8, 0),
        (9, 0),
    ],
)
def test_get_load_level(lesson_count, expected_level):
    assert get_load_level(lesson_count) == expected_level


def test_get_load_level_rejects_negative_lesson_count():
    with pytest.raises(ValueError):
        get_load_level(-1)
