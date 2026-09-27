"""``parallel`` モジュールの ``aggregate`` に対するプロパティテスト。

成功・失敗が混在するリージョン調査結果の集約について、分類の網羅性と
成功リージョンの EIP 保持を Hypothesis で検証する。プロパティは 100 反復で評価する。
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from aws_eip_cleaner.models import RegionScanResult, UnusedEip
from aws_eip_cleaner.parallel import aggregate

_ALLOCATION_ID = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12
).map(lambda s: f"eipalloc-{s}")
_PUBLIC_IP = st.builds(
    lambda a, b, c, d: f"{a}.{b}.{c}.{d}",
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
)
_REGION_NAME = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=20
)
# 失敗時の error は非空文字列とし、成功（None）との判別を明確にする。
_ERROR_MESSAGE = st.text(min_size=1, max_size=40)


# リージョンに依存しない未利用 EIP。region は結果生成時に付け替える。
_UNUSED_EIP = st.builds(
    lambda allocation_id, public_ip: UnusedEip(
        allocation_id=allocation_id, public_ip=public_ip, region=""
    ),
    _ALLOCATION_ID,
    _PUBLIC_IP,
)


def _build_result(
    region: str, eips: list[UnusedEip], error: str | None
) -> RegionScanResult:
    """調査結果を組み立てる。EIP のリージョンは所属リージョンに揃える。

    Parameters
    ----------
    region : str
        調査対象リージョン。
    eips : list[UnusedEip]
        未利用 EIP（``region`` は未設定のため付け替える）。
    error : str | None
        失敗時のエラー内容。成功時は None。

    Returns
    -------
    RegionScanResult
        成功時は与えられた EIP を、失敗時は空の EIP を持つ調査結果。
    """
    if error is not None:
        return RegionScanResult(region=region, unused_eips=[], error=error)
    scoped = [
        UnusedEip(allocation_id=e.allocation_id, public_ip=e.public_ip, region=region)
        for e in eips
    ]
    return RegionScanResult(region=region, unused_eips=scoped, error=None)


# 成功・失敗いずれかの調査結果。error が None なら成功、非空なら失敗とする。
_REGION_SCAN_RESULT = st.builds(
    _build_result,
    _REGION_NAME,
    st.lists(_UNUSED_EIP, max_size=5),
    st.one_of(st.none(), _ERROR_MESSAGE),
)

# リージョン名が一意な調査結果リスト。分類検証を容易にするため重複を排除する。
_REGION_SCAN_RESULTS = st.lists(
    _REGION_SCAN_RESULT, max_size=12, unique_by=lambda r: r.region
)


# Feature: aws-eip-cleaner, Property 4: 集約は全リージョンを漏れなく分類し成功結果の EIP を保持する  # noqa: E501
@settings(max_examples=100)
@given(results=_REGION_SCAN_RESULTS)
def test_aggregate_partitions_regions_and_preserves_successful_eips(
    results: list[RegionScanResult],
) -> None:
    """集約が全リージョンを漏れなく分類し、成功分の EIP のみを保持することを検証する。

    Validates: Requirements 4.3, 4.4, 4.5

    Parameters
    ----------
    results : list[RegionScanResult]
        成功・失敗が混在する、リージョン名が一意な調査結果の一覧。
    """
    aggregated = aggregate(results)

    all_regions = {result.region for result in results}
    succeeded = set(aggregated.succeeded_regions)
    failed = set(aggregated.failed_regions.keys())

    # 成功集合と失敗集合は重複せず、その和が入力の全リージョンに一致する（直和分割）。
    assert succeeded.isdisjoint(failed)
    assert succeeded | failed == all_regions

    # 失敗集合のキーは error を持つ結果と一致し、値は対応する error 文字列と一致する。
    expected_failed = {
        result.region: result.error for result in results if result.error is not None
    }
    assert failed == set(expected_failed.keys())
    assert aggregated.failed_regions == expected_failed

    # 統合された EIP は成功リージョンの EIP のすべて、かつそれのみを含む。
    expected_eips = [
        eip for result in results if result.succeeded for eip in result.unused_eips
    ]
    assert aggregated.unused_eips == expected_eips
