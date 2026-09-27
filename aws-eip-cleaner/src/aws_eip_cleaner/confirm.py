"""解放実行前のユーザ確認入力を解釈するモジュール。

対話プロンプトで受け取った 1 文字入力を、承認・拒否・無効のいずれかへ分類する
純粋ロジックを提供する。実際の入力受付や再プロンプトなどの I/O は上位層が担い、
本モジュールは入力文字列の解釈のみに責務を限定する。
"""

import enum
from collections.abc import Callable

from aws_eip_cleaner.models import UnusedEip


class ConfirmDecision(enum.Enum):
    """確認入力の解釈結果。

    Attributes
    ----------
    APPROVE : str
        承認（解放を実行する）。
    REJECT : str
        拒否（解放を中止する）。
    INVALID : str
        承認・拒否のいずれとも解釈できない無効な入力。
    """

    APPROVE = "approve"
    REJECT = "reject"
    INVALID = "invalid"


def interpret_input(raw: str) -> ConfirmDecision:
    """1 文字入力を解釈する。

    前後の空白を除去し小文字化したうえで、``"y"`` を承認、``"n"`` を拒否、
    それ以外を無効として分類する。大文字小文字は区別しない。副作用を持たない
    純粋関数であり、プロパティベーステストの対象とする。

    Parameters
    ----------
    raw : str
        ユーザから受け取った生の入力文字列。

    Returns
    -------
    ConfirmDecision
        入力の解釈結果。``"y"`` なら APPROVE、``"n"`` なら REJECT、
        それ以外は INVALID。
    """
    normalized = raw.strip().lower()
    if normalized == "y":
        return ConfirmDecision.APPROVE
    if normalized == "n":
        return ConfirmDecision.REJECT
    return ConfirmDecision.INVALID


def prompt_decision(
    eip: UnusedEip,
    input_fn: Callable[[str], str],
    max_retries: int = 3,
) -> ConfirmDecision:
    """1 件の EIP について承認/拒否を得る。

    割り当て ID とパブリック IP アドレスを提示し、承認（``y``）または拒否（``n``）の
    1 文字入力を求める。無効な入力の場合は入力が無効である旨を提示したうえで同一 EIP に
    ついて再度入力を求め、無効入力が ``max_retries`` 回連続した場合は拒否として扱う。

    ``EOFError``（入力ストリームの終端）は中断を示すため捕捉せず呼び出し側へ再送出する。

    Parameters
    ----------
    eip : UnusedEip
        承認/拒否を問う対象の未利用 EIP。
    input_fn : Callable[[str], str]
        プロンプト文字列を受け取り入力文字列を返す関数。標準入力の代わりに
        テストで擬似入力を注入できるよう注入可能とする。
    max_retries : int, optional
        同一 EIP について入力を求める最大試行回数。既定値は 3。この回数すべてが
        無効だった場合は REJECT を返す。

    Returns
    -------
    ConfirmDecision
        承認なら APPROVE、拒否なら REJECT。無効入力が ``max_retries`` 回連続した
        場合も REJECT を返す。

    Raises
    ------
    EOFError
        入力ストリームが終端に達した場合。中断として扱うため再送出する。
    """
    prompt = (
        f"解放しますか? allocation_id={eip.allocation_id} "
        f"public_ip={eip.public_ip} [y/n]: "
    )
    for _ in range(max_retries):
        raw = input_fn(prompt)
        decision = interpret_input(raw)
        if decision is ConfirmDecision.APPROVE or decision is ConfirmDecision.REJECT:
            return decision
        print("無効な入力です。y（承認）または n（拒否）を入力してください。")
    return ConfirmDecision.REJECT
