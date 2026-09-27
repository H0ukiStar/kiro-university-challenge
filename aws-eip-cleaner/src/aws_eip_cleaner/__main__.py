"""``python -m aws_eip_cleaner`` 実行時のエントリポイント。

CLI 本体（``aws_eip_cleaner.cli.main``）を呼び出し、その戻り値を終了コードとして
プロセスを終了する。``cli`` モジュールは後続タスクで実装されるため、現時点では未実装でも
モジュールの読み込み自体が壊れないよう ``main`` の解決を実行時まで遅延させている。
"""

import importlib
import logging

logger = logging.getLogger(__name__)


def _run() -> int:
    """CLI 本体を呼び出し、その終了コードを返す。

    ``aws_eip_cleaner.cli`` を実行時に動的解決して ``main`` を呼び出す。
    ``cli`` モジュールがまだ実装されていない段階では ``ImportError`` を捕捉し、
    未実装である旨を通知して非ゼロの終了コードを返す。

    Returns
    -------
    int
        プロセスの終了コード。CLI 本体の戻り値、または未実装時の非ゼロ値。
    """
    try:
        # cli.py は後続タスクで実装される。
        # 動的解決により未実装時も読み込みが壊れないようにする。
        cli = importlib.import_module("aws_eip_cleaner.cli")
    except ImportError:
        logger.error("CLI はまだ実装されていません。")
        return 1
    exit_code: int = cli.main()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(_run())
