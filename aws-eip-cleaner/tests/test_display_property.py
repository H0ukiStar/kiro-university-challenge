"""``display`` モジュールの純粋ロジック層に対するプロパティテスト。

``format_eip_list`` の性質を Hypothesis で検証する。
各プロパティは 100 反復で評価する。
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from aws_eip_cleaner.display import format_eip_list
from aws_eip_cleaner.models import UnusedEip

# allocation_id は eipalloc- + 英数。明細行の識別に用いるため一意性は保証しないが、
# 各行に固有プレフィックスが現れることの検証には十分。
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
# 未利用 EIP は定義上 association_id が None だが、整形ロジックの網羅性を高めるため
# None / 非 None の双方を生成する。
_ASSOCIATION_ID = st.one_of(
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12
    ).map(lambda s: f"eipassoc-{s}"),
    st.none(),
)
_REGION = st.sampled_from(
    ["us-east-1", "us-west-2", "eu-west-1", "ap-northeast-1", "sa-east-1"]
)

_UNUSED_EIP = st.builds(
    UnusedEip,
    allocation_id=_ALLOCATION_ID,
    public_ip=_PUBLIC_IP,
    region=_REGION,
    association_id=_ASSOCIATION_ID,
)

# format_eip_list が association_id is None に対して用いる関連付けなし文言。
_NO_ASSOCIATION_LABEL = "関連付けなし"


# Feature: aws-eip-cleaner, Property 5: 一覧整形は全対象を 1 行ずつ全項目付きで表示し件数を含め打ち切らない  # noqa: E501
@settings(max_examples=100)
@given(eips=st.lists(_UNUSED_EIP, max_size=30))
def test_format_eip_list_shows_all_items_without_truncation(
    eips: list[UnusedEip],
) -> None:
    """全対象が 1 行ずつ全項目付きで表示され、件数を含め打ち切られないことを検証する。

    Validates: Requirements 6.1, 6.2, 6.4, 6.5, 7.1, 7.4

    Parameters
    ----------
    eips : list[UnusedEip]
        整形対象の未利用 EIP のリスト（association_id は None / 非 None を混在）。
    """
    output = format_eip_list(eips)
    lines = output.splitlines()

    # 明細行は "Allocation ID: " プレフィックスで識別する。合計行や項目値と衝突しない
    # 固定ラベルのため、偽陽性・偽陰性なく明細行数を数えられる。
    detail_lines = [line for line in lines if line.startswith("Allocation ID: ")]

    # 明細行数が入力件数と一致すること（件数によらず打ち切らない）。
    assert len(detail_lines) == len(eips)

    for eip, line in zip(eips, detail_lines, strict=True):
        # 各明細行に対応する 4 項目がすべて含まれること。
        assert eip.allocation_id in line
        assert eip.public_ip in line
        assert eip.region in line
        expected_association = (
            eip.association_id
            if eip.association_id is not None
            else _NO_ASSOCIATION_LABEL
        )
        assert expected_association in line

    # 出力に合計件数（リスト長）の表示が含まれること。
    assert f"合計: {len(eips)} 件" in output


# Feature: aws-eip-cleaner, Property 5: 一覧整形は全対象を 1 行ずつ全項目付きで表示し件数を含め打ち切らない  # noqa: E501
@settings(max_examples=100)
@given(
    eips=st.lists(
        st.builds(
            UnusedEip,
            allocation_id=_ALLOCATION_ID,
            public_ip=_PUBLIC_IP,
            region=_REGION,
            association_id=st.none(),
        ),
        min_size=1,
        max_size=30,
    )
)
def test_format_eip_list_uses_no_association_label_when_none(
    eips: list[UnusedEip],
) -> None:
    """association_id が None の EIP に「関連付けなし」文言が含まれることを検証する。

    Validates: Requirements 6.1, 6.2, 6.4, 6.5, 7.1, 7.4

    Parameters
    ----------
    eips : list[UnusedEip]
        すべて association_id が None の未利用 EIP のリスト。
    """
    output = format_eip_list(eips)
    detail_lines = [
        line for line in output.splitlines() if line.startswith("Allocation ID: ")
    ]

    assert len(detail_lines) == len(eips)
    for line in detail_lines:
        assert _NO_ASSOCIATION_LABEL in line
