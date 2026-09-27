"""終了コード決定（``determine_exit_code``）に対するプロパティテスト。

未利用 EIP のリストと、各 EIP に対し成功/失敗をランダムに返す解放関数から集計
（``ReleaseSummary``）を構築し、集計の非負性・合計整合性、および解放結果に応じた
終了コードの決定を Hypothesis で検証する。プロパティは 100 反復で評価する。
"""

from collections.abc import Callable

from hypothesis import given, settings
from hypothesis import strategies as st

from aws_eip_cleaner.cli import determine_exit_code
from aws_eip_cleaner.models import ReleaseSummary, UnusedEip

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

_UNUSED_EIP = st.builds(
    lambda allocation_id, public_ip, region: UnusedEip(
        allocation_id=allocation_id, public_ip=public_ip, region=region
    ),
    _ALLOCATION_ID,
    _PUBLIC_IP,
    _REGION_NAME,
)


def _summarize_releases(
    eips: list[UnusedEip], release_fn: Callable[[UnusedEip], bool]
) -> ReleaseSummary:
    """各 EIP に対する成功/失敗判定から解放集計を構築する。

    実際の解放オーケストレーション（``runner``）を模したヘルパで、``release_fn`` が
    True を返した EIP を成功、False を返した EIP を失敗として数え上げる。終了コードの
    決定は本物の ``determine_exit_code`` に委ねる。

    Parameters
    ----------
    eips : list[UnusedEip]
        解放対象の未利用 EIP の一覧。
    release_fn : Callable[[UnusedEip], bool]
        各 EIP の解放が成功したかどうかを返す関数。True なら成功、False なら失敗。

    Returns
    -------
    ReleaseSummary
        成功件数と失敗件数を集計した結果。
    """
    succeeded = 0
    failed = 0
    for eip in eips:
        if release_fn(eip):
            succeeded += 1
        else:
            failed += 1
    return ReleaseSummary(succeeded=succeeded, failed=failed)


# Feature: aws-eip-cleaner, Property 9: 解放集計は非負かつ合計整合で、失敗があるときのみ非ゼロ終了する  # noqa: E501
@settings(max_examples=100)
@given(
    eips=st.lists(_UNUSED_EIP, max_size=30),
    outcomes=st.lists(st.booleans(), max_size=30),
)
def test_release_summary_is_nonnegative_and_exit_code_reflects_failures(
    eips: list[UnusedEip], outcomes: list[bool]
) -> None:
    """集計の非負性・合計整合と、失敗有無に応じた終了コードを検証する。

    成功/失敗をランダムに返す解放関数から集計を構築したとき、``succeeded`` と
    ``failed`` はいずれも 0 以上であり、その和は処理件数（EIP の件数）に一致する。
    さらに調査失敗なしを前提に、``determine_exit_code`` は ``failed > 0`` のときのみ
    非ゼロを返し、``failed == 0`` のとき 0 を返す。

    Validates: Requirements 8.8, 9.4, 10.6

    Parameters
    ----------
    eips : list[UnusedEip]
        解放対象の未利用 EIP の一覧。
    outcomes : list[bool]
        各 EIP の解放成否をランダムに定める真偽値の一覧。EIP と同数になるよう調整する。
    """
    # 解放関数が各 EIP に対して安定した成否を返すよう、EIP と同数の判定列を用意する。
    decisions = [
        outcomes[i % len(outcomes)] if outcomes else True for i in range(len(eips))
    ]
    outcome_by_index = dict(enumerate(decisions))
    order: list[int] = []

    def release_fn(_eip: UnusedEip) -> bool:
        index = len(order)
        order.append(index)
        return outcome_by_index.get(index, True)

    summary = _summarize_releases(eips, release_fn)

    # 集計は非負であり、その和は処理件数（EIP の件数）に一致する（合計整合）。
    assert summary.succeeded >= 0
    assert summary.failed >= 0
    assert summary.total == len(eips)
    assert summary.succeeded + summary.failed == len(eips)

    # 調査失敗なしを前提に、終了コードは解放失敗の有無のみで決まる。
    exit_code = determine_exit_code(summary, scan_failed=False)
    if summary.failed > 0:
        assert exit_code != 0
    else:
        assert exit_code == 0
