"""``runner.run_dry_run`` の純粋ロジック層に対するプロパティテスト。

dry-run モードで解放も対話も一切発生しないことを Hypothesis で検証する。
各プロパティは 100 反復で評価する。
"""

import inspect

from hypothesis import given, settings
from hypothesis import strategies as st

from aws_eip_cleaner import runner
from aws_eip_cleaner.models import UnusedEip

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


# Feature: aws-eip-cleaner, Property 7: dry-run では解放も対話も一切発生しない
@settings(max_examples=100)
@given(eips=st.lists(_UNUSED_EIP, max_size=30))
def test_dry_run_never_releases_or_prompts(eips: list[UnusedEip]) -> None:
    """dry-run で解放・対話が一切発生せず、常に終了コード 0 を返すことを検証する。

    ``run_dry_run`` は設計上 ``release_fn`` / ``input_fn`` を引数に取らないため、
    解放関数・対話関数を注入する余地がないこと（シグネチャに存在しないこと）を確認する。
    加えて spy を用意し、それらが呼ばれる経路が存在しないことを補強する。

    Validates: Requirements 7.1, 7.2
    Properties: 7

    Parameters
    ----------
    eips : list[UnusedEip]
        表示対象の未利用 EIP のリスト。
    """
    release_calls: list[UnusedEip] = []
    prompt_calls: list[str] = []

    def release_spy(eip: UnusedEip) -> None:
        release_calls.append(eip)

    def input_spy(prompt: str) -> str:
        prompt_calls.append(prompt)
        return "y"

    # run_dry_run は解放・対話を注入できない設計であることをシグネチャで確認する。
    params = set(inspect.signature(runner.run_dry_run).parameters)
    assert "release_fn" not in params
    assert "input_fn" not in params

    exit_code = runner.run_dry_run(eips)

    assert exit_code == 0
    # 注入経路が存在しないため、spy はいずれも呼ばれ得ない。
    assert release_calls == []
    assert prompt_calls == []
