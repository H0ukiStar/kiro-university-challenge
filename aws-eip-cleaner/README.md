# aws-eip-cleaner

AWS アカウント上の未利用 Elastic IP（EIP）を検出して解放する CLI ツール。

コマンドラインオプションで調査対象リージョンや認証プロファイルを指定でき、複数リージョンを
並列に調査する。削除対象を一覧化したうえで、対話的な確認・ドライラン・一括解放によって
EIP を整理できる。

> 本 README は土台整備段階のプレースホルダです。ツールの概要・クイックスタート・
> オプション要約・ドキュメントへのリンクは後続タスクで整備します。

## 開発

環境・パッケージ管理には [uv](https://docs.astral.sh/uv/) を使用する。

```sh
uv sync          # 依存をインストール
uv run pytest    # テスト実行
uv run mypy      # 型検査（strict）
uv run ruff check # リント
uv run ruff format # フォーマット
```
