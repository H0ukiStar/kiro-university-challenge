"""``confirm`` モジュールの純粋ロジック層に対するプロパティテスト。

``interpret_input`` の性質を Hypothesis で検証する。
各プロパティは 100 反復で評価する。
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from aws_eip_cleaner.confirm import ConfirmDecision, interpret_input


def _expected_decision(raw: str) -> ConfirmDecision:
    """オラクルとして期待される解釈結果を返す。

    ``interpret_input`` とは独立に、正規化後（トリム・小文字化）が ``"y"`` なら
    APPROVE、``"n"`` なら REJECT、それ以外を INVALID とみなす参照実装。

    Parameters
    ----------
    raw : str
        解釈対象の生の入力文字列。

    Returns
    -------
    ConfirmDecision
        期待される解釈結果。
    """
    normalized = raw.strip().lower()
    if normalized == "y":
        return ConfirmDecision.APPROVE
    if normalized == "n":
        return ConfirmDecision.REJECT
    return ConfirmDecision.INVALID


# Feature: aws-eip-cleaner, Property 6: 確認入力の解釈は y/n（大小無視）以外をすべて無効とする  # noqa: E501
@settings(max_examples=100)
@given(raw=st.text())
def test_interpret_input_matches_normalization_oracle(raw: str) -> None:
    """任意 Unicode 文字列の解釈がオラクルと一致することを検証する。

    Validates: Requirements 8.2, 8.3, 8.4

    Parameters
    ----------
    raw : str
        特殊文字・空文字・空白を含みうる任意の Unicode 文字列。
    """
    # 正規化後が "y" なら APPROVE、"n" なら REJECT、それ以外はすべて INVALID。
    assert interpret_input(raw) is _expected_decision(raw)


# y/n の周辺に前後空白・大小文字を織り交ぜた入力を構成し、それぞれ確実に APPROVE /
# REJECT へ分類されることを補強する。正規化後の値が "y" / "n" となる入力空間に
# 限定した賢い生成器を用いる。
_SURROUNDING_WHITESPACE = st.text(alphabet=" \t\n\r\f\v", max_size=5)
_Y_VARIANT = st.sampled_from(["y", "Y"])
_N_VARIANT = st.sampled_from(["n", "N"])


# Feature: aws-eip-cleaner, Property 6: 確認入力の解釈は y/n（大小無視）以外をすべて無効とする  # noqa: E501
@settings(max_examples=100)
@given(
    leading=_SURROUNDING_WHITESPACE,
    core=_Y_VARIANT,
    trailing=_SURROUNDING_WHITESPACE,
)
def test_interpret_input_approves_padded_y(
    leading: str, core: str, trailing: str
) -> None:
    """前後空白・大文字を含む y 系入力が APPROVE に分類されることを検証する。

    Validates: Requirements 8.2, 8.4

    Parameters
    ----------
    leading : str
        コアの前に付与する空白文字列。
    core : str
        大小いずれかの ``y``。
    trailing : str
        コアの後に付与する空白文字列。
    """
    assert interpret_input(f"{leading}{core}{trailing}") is ConfirmDecision.APPROVE


# Feature: aws-eip-cleaner, Property 6: 確認入力の解釈は y/n（大小無視）以外をすべて無効とする  # noqa: E501
@settings(max_examples=100)
@given(
    leading=_SURROUNDING_WHITESPACE,
    core=_N_VARIANT,
    trailing=_SURROUNDING_WHITESPACE,
)
def test_interpret_input_rejects_padded_n(
    leading: str, core: str, trailing: str
) -> None:
    """前後空白・大文字を含む n 系入力が REJECT に分類されることを検証する。

    Validates: Requirements 8.3, 8.4

    Parameters
    ----------
    leading : str
        コアの前に付与する空白文字列。
    core : str
        大小いずれかの ``n``。
    trailing : str
        コアの後に付与する空白文字列。
    """
    assert interpret_input(f"{leading}{core}{trailing}") is ConfirmDecision.REJECT
