"""``runner.run_auto_approve`` の純粋ロジック層に対するプロパティテスト。

yes モードが全対象に対し解放を 1 回ずつ試行し、対話が発生しないことを Hypothesis で
検証する。各プロパティは 100 反復で評価する。
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from aws_eip_cleaner.models import UnusedEip
from aws_eip_cleaner.runner import run_auto_approve

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
_REGION = st.sampled_from(
    ["us-east-1", "us-west-2", "eu-west-1", "ap-northeast-1", "sa-east-1"]
)
_UNUSED_EIP = st.builds(
    UnusedEip,
    allocation_id=_ALLOCATION_ID,
    public_ip=_PUBLIC_IP,
    region=_REGION,
    association_id=st.none(),
)


# Feature: aws-eip-cleaner, Property 8: yes モードは全対象に対し解放を 1 回ずつ試行する
@settings(max_examples=100)
@given(eips=st.lists(_UNUSED_EIP, max_size=30))
def test_auto_approve_releases_each_eip_exactly_once(eips: list[UnusedEip]) -> None:
    """各 EIP に対し解放が 1 回ずつ試行され、対話が発生しないことを検証する。

    ``run_auto_approve`` は ``input_fn`` を引数に取らないため対話は構造的に発生しない。
    解放関数の呼び出し回数が件数と一致し、各 EIP がちょうど 1 回渡されることを確認する。

    Validates: Requirements 9.1
    Properties: 8

    Parameters
    ----------
    eips : list[UnusedEip]
        解放対象の未利用 EIP のリスト。
    """
    release_calls: list[UnusedEip] = []

    def release_fn(eip: UnusedEip) -> None:
        release_calls.append(eip)

    run_auto_approve(eips, release_fn)

    # 合計試行回数が件数と一致し、各 EIP がちょうど 1 回ずつ渡されること。
    assert len(release_calls) == len(eips)
    assert release_calls == eips
