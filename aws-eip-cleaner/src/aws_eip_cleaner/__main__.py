"""``python -m aws_eip_cleaner`` 実行時のエントリポイント。

CLI 本体（``aws_eip_cleaner.cli.main``）を呼び出し、その戻り値を終了コードとして
プロセスを終了する。
"""

from aws_eip_cleaner.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
