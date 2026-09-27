"""``parallel`` モジュールの ``scan_regions`` に対するユニットテスト。

擬似的な ``scan_fn`` を注入し、全 future 完了後に ``aggregate`` された集約結果が
返ること、および 1 リージョンの失敗が他リージョンへ波及せず成功分が集約に含まれることを
検証する。boto3 には依存しない。
"""

import threading

from aws_eip_cleaner.models import AggregatedResult, RegionScanResult, UnusedEip
from aws_eip_cleaner.parallel import scan_regions


def _make_unused_eip(region: str) -> UnusedEip:
    """テスト用の未利用 EIP を生成する。

    Parameters
    ----------
    region : str
        EIP が属するリージョン。

    Returns
    -------
    UnusedEip
        リージョン名から一意に定まる未利用 EIP。
    """
    return UnusedEip(
        allocation_id=f"eipalloc-{region}",
        public_ip=f"203.0.113.{len(region)}",
        region=region,
    )


def test_scan_regions_aggregates_all_results() -> None:
    """全 future 完了後に集約結果（AggregatedResult）が返ることを検証する。

    Validates: Requirements 4.2
    """
    regions = ["us-east-1", "us-west-2", "ap-northeast-1"]

    def scan_fn(region: str) -> RegionScanResult:
        return RegionScanResult(region=region, unused_eips=[_make_unused_eip(region)])

    aggregated = scan_regions(scan_fn, regions)

    assert isinstance(aggregated, AggregatedResult)
    assert set(aggregated.succeeded_regions) == set(regions)
    assert aggregated.failed_regions == {}
    # 各リージョンの EIP がすべて集約に含まれる（順序は完了順に依存するため集合比較）。
    assert {eip.region for eip in aggregated.unused_eips} == set(regions)
    assert len(aggregated.unused_eips) == len(regions)


def test_scan_regions_waits_for_all_futures() -> None:
    """集約前にすべての future の調査が完了していることを検証する。

    各 ``scan_fn`` 呼び出しの完了をカウントし、集約結果に含まれる成功・失敗リージョン
    数の合計が全リージョン数と一致することで、全 future の完了を待ってから集約された
    ことを確認する。

    Validates: Requirements 4.2
    """
    regions = [f"region-{i}" for i in range(20)]
    completed = 0
    lock = threading.Lock()

    def scan_fn(region: str) -> RegionScanResult:
        nonlocal completed
        with lock:
            completed += 1
        return RegionScanResult(region=region, unused_eips=[])

    aggregated = scan_regions(scan_fn, regions)

    assert completed == len(regions)
    total_classified = len(aggregated.succeeded_regions) + len(
        aggregated.failed_regions
    )
    assert total_classified == len(regions)


def test_scan_regions_isolates_single_region_failure() -> None:
    """1 リージョンが失敗しても他リージョンの調査が継続され集約されることを検証する。

    Validates: Requirements 4.4, 4.5
    """
    regions = ["us-east-1", "us-west-2", "ap-northeast-1"]
    failing_region = "us-west-2"

    def scan_fn(region: str) -> RegionScanResult:
        if region == failing_region:
            return RegionScanResult(
                region=region, unused_eips=[], error="describe_addresses に失敗"
            )
        return RegionScanResult(region=region, unused_eips=[_make_unused_eip(region)])

    aggregated = scan_regions(scan_fn, regions)

    # 失敗リージョンは failed_regions に隔離され、エラー内容が保持される。
    assert set(aggregated.failed_regions.keys()) == {failing_region}
    assert aggregated.failed_regions[failing_region] == "describe_addresses に失敗"

    # 成功リージョンは継続して集約に含まれる。
    expected_succeeded = set(regions) - {failing_region}
    assert set(aggregated.succeeded_regions) == expected_succeeded
    assert {eip.region for eip in aggregated.unused_eips} == expected_succeeded
