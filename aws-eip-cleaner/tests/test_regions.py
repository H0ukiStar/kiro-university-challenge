"""``regions`` モジュールの純粋ロジック層に対するプロパティテスト。

``normalize_regions`` / ``validate_regions`` の性質を Hypothesis で検証する。
各プロパティは 100 反復で評価する。
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from aws_eip_cleaner.errors import InvalidRegionError
from aws_eip_cleaner.regions import normalize_regions, validate_regions

# 実在するリージョン名に依存せず、重複や順序ばらつきを起こしやすい小さな候補集合を使う。
_REGION_TOKENS = st.sampled_from(
    ["us-east-1", "us-west-2", "eu-west-1", "ap-northeast-1", "sa-east-1"]
)


# Feature: aws-eip-cleaner, Property 1: リージョン正規化は一意集合と等価かつ冪等
@settings(max_examples=100)
@given(regions=st.lists(_REGION_TOKENS, max_size=20))
def test_normalize_regions_is_unique_set_equivalent_and_idempotent(
    regions: list[str],
) -> None:
    """正規化結果が一意集合と等価かつ冪等で初出順を保つことを検証する。

    Parameters
    ----------
    regions : list[str]
        重複・順序ばらつきを含みうる入力リージョンリスト。
    """
    normalized = normalize_regions(regions)

    # 集合として入力と等価であること（欠落も追加もない）。
    assert set(normalized) == set(regions)
    # 重複がないこと。
    assert len(normalized) == len(set(normalized))
    # 冪等性: 再度正規化しても結果が変わらない。
    assert normalize_regions(normalized) == normalized

    # 初出順が保たれること。
    expected_order: list[str] = []
    seen: set[str] = set()
    for region in regions:
        if region not in seen:
            seen.add(region)
            expected_order.append(region)
    assert normalized == expected_order


# Feature: aws-eip-cleaner, Property 2: リージョン検証は無効値を 1 つでも含めば拒否する
@settings(max_examples=100)
@given(
    available=st.sets(_REGION_TOKENS),
    regions=st.lists(_REGION_TOKENS, max_size=20),
)
def test_validate_regions_rejects_when_any_invalid(
    available: set[str],
    regions: list[str],
) -> None:
    """全要素が利用可能な場合のみ成功し、無効値があれば必ず拒否することを検証する。

    Parameters
    ----------
    available : set[str]
        利用可能なリージョン名の集合。
    regions : list[str]
        検証対象のリージョン名リスト。
    """
    if all(region in available for region in regions):
        # 全要素が利用可能なら例外を送出せず正常終了する。
        validate_regions(regions, available)
    else:
        with pytest.raises(InvalidRegionError):
            validate_regions(regions, available)
