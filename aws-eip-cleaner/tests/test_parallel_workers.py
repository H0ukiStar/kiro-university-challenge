"""``parallel`` モジュールの ``compute_max_workers`` に対するユニットテスト。

デフォルトの並列度上限 16 のもとで、境界となるリージョン数について
``compute_max_workers`` が ``min(16, n)`` を返すことを検証する。
"""

import pytest

from aws_eip_cleaner.parallel import compute_max_workers


@pytest.mark.parametrize(
    ("region_count", "expected"),
    [
        (1, 1),
        (15, 15),
        (16, 16),
        (17, 16),
    ],
)
def test_compute_max_workers_returns_min_of_limit_and_count(
    region_count: int,
    expected: int,
) -> None:
    """デフォルト上限 16 で並列度が ``min(16, n)`` になることを境界値で検証する。

    Parameters
    ----------
    region_count : int
        調査対象リージョン数。境界値 1, 15, 16, 17 を与える。
    expected : int
        期待する並列度（``min(16, region_count)``）。
    """
    assert compute_max_workers(region_count) == expected
