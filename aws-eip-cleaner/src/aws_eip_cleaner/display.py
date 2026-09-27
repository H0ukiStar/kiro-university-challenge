"""aws-eip-cleaner の未利用 EIP 一覧の整形と出力を提供するモジュール。

``format_eip_list`` は AWS API に依存しない純粋ロジック層の関数であり、未利用 EIP の
リストを 1 件 1 行の明細と合計件数を含む文字列へ整形する。``print_eip_list`` はその
整形結果を標準出力へ書き出す I/O を担う。整形と出力を分離することで、整形ロジックを
副作用なくテストできるようにしている。
"""

from aws_eip_cleaner.models import UnusedEip

# association_id が None（いずれのリソースにも関連付けられていない）の未利用 EIP に
# 対し、一覧上で関連付け状態として表示する文言。通常・dry-run モードで共通に用いる。
_NO_ASSOCIATION_LABEL = "関連付けなし"


def format_eip_list(eips: list[UnusedEip]) -> str:
    """未利用 EIP の一覧を整形する。

    各 EIP を Allocation_ID・パブリック IP・リージョン・関連付け状態を含む 1 件 1 行の
    明細として整形し、末尾に合計件数の行を付す。件数の打ち切りは行わず、入力の全件を明細
    として出力する。``association_id`` が None の EIP は関連付け状態を「関連付けなし」
    として整形する。

    Parameters
    ----------
    eips : list[UnusedEip]
        整形対象の未利用 EIP のリスト。空リストも許容する。

    Returns
    -------
    str
        各 EIP の明細行と合計件数行を改行で連結した文字列。
    """
    lines: list[str] = []
    for eip in eips:
        association = (
            eip.association_id
            if eip.association_id is not None
            else _NO_ASSOCIATION_LABEL
        )
        lines.append(
            f"Allocation ID: {eip.allocation_id}, "
            f"Public IP: {eip.public_ip}, "
            f"Region: {eip.region}, "
            f"関連付け状態: {association}"
        )
    lines.append(f"合計: {len(eips)} 件")
    return "\n".join(lines)


def print_eip_list(eips: list[UnusedEip]) -> None:
    """未利用 EIP の一覧を整形して標準出力へ書き出す。

    Parameters
    ----------
    eips : list[UnusedEip]
        表示対象の未利用 EIP のリスト。
    """
    print(format_eip_list(eips))
