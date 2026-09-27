"""``scanner`` モジュールの純粋ロジック層に対するプロパティテスト。

``extract_unused_eips`` の性質を Hypothesis で検証する。
各プロパティは 100 反復で評価する。
"""

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from aws_eip_cleaner.scanner import extract_unused_eips

# Association_ID の有無・空文字を混在させるため、有効値・空文字・キー欠損を作り分ける。
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
# 関連付け状態: 有効な Association_ID / 空文字 / キー欠損（None）を混在させる。
_ASSOCIATION_ID = st.one_of(
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12
    ).map(lambda s: f"eipassoc-{s}"),
    st.just(""),
    st.none(),
)
_REGION = st.sampled_from(
    ["us-east-1", "us-west-2", "eu-west-1", "ap-northeast-1", "sa-east-1"]
)


@st.composite
def _address(draw: st.DrawFn) -> dict[str, Any]:
    """``AddressTypeDef`` 相当のアドレス dict を 1 件生成する。

    Parameters
    ----------
    draw : st.DrawFn
        Hypothesis の描画関数。

    Returns
    -------
    dict[str, Any]
        AllocationId・PublicIp を持ち、AssociationId は有効値・空文字・欠損のいずれか。
    """
    address: dict[str, Any] = {
        "AllocationId": draw(_ALLOCATION_ID),
        "PublicIp": draw(_PUBLIC_IP),
    }
    association_id = draw(_ASSOCIATION_ID)
    # None のときは AssociationId キー自体を持たせず、実 API の欠損状態を再現する。
    if association_id is not None:
        address["AssociationId"] = association_id
    return address


def _is_unused(address: dict[str, Any]) -> bool:
    """アドレスが未利用（AssociationId が未設定または空）かを返す。

    Parameters
    ----------
    address : dict[str, Any]
        判定対象のアドレス dict。

    Returns
    -------
    bool
        AssociationId が未設定または空なら True。
    """
    return not address.get("AssociationId")


# Feature: aws-eip-cleaner, Property 3: 未利用 EIP 抽出は Association_ID 非保持の EIP と厳密一致しフィールドを保持する  # noqa: E501
@settings(max_examples=100)
@given(addresses=st.lists(_address(), max_size=20), region=_REGION)
def test_extract_unused_eips_matches_unassociated_and_preserves_fields(
    addresses: list[dict[str, Any]],
    region: str,
) -> None:
    """抽出結果が未関連付けアドレスと厳密一致し、各フィールドを保持することを検証する。

    Validates: Requirements 5.2, 5.3, 5.4

    Parameters
    ----------
    addresses : list[dict[str, Any]]
        AssociationId の有無・空文字が混在するアドレス集合。
    region : str
        アドレスが属するリージョン。
    """
    result = extract_unused_eips(addresses, region)  # type: ignore[arg-type]

    expected_unused = [addr for addr in addresses if _is_unused(addr)]

    # 未利用アドレスと抽出結果が件数・順序で厳密に一致すること。
    assert len(result) == len(expected_unused)

    for eip, addr in zip(result, expected_unused, strict=True):
        assert eip.allocation_id == addr["AllocationId"]
        assert eip.public_ip == addr["PublicIp"]
        assert eip.region == region
        assert eip.association_id is None


# Feature: aws-eip-cleaner, Property 3: 未利用 EIP 抽出は Association_ID 非保持の EIP と厳密一致しフィールドを保持する  # noqa: E501
@settings(max_examples=100)
@given(region=_REGION)
def test_extract_unused_eips_returns_empty_for_empty_input(region: str) -> None:
    """空入力に対して空出力を返すことを検証する。

    Validates: Requirements 5.2, 5.3, 5.4

    Parameters
    ----------
    region : str
        アドレスが属するリージョン。
    """
    assert extract_unused_eips([], region) == []
