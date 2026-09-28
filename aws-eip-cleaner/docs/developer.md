# aws-eip-cleaner 開発者向けドキュメント

本ドキュメントは `aws-eip-cleaner` の開発に参加する人向けに、開発環境の構築、プロジェクト構成、テスト・型検査・リントの実行方法、アーキテクチャの概要、コントリビュート手順をまとめたものである。利用者向けの使い方は `docs/usage.md`、概要は `README.md` を参照。

## 開発環境セットアップ

環境・パッケージ管理には [uv](https://docs.astral.sh/uv/) を使用する。Python は 3.14 以上が必要（`pyproject.toml` の `requires-python = ">=3.14"`）。

### 依存のインストール

`uv.lock` に固定された依存（本体・開発用の双方）を仮想環境へ一括でインストールする。

```sh
uv sync
```

### 依存の追加

依存を追加する場合は `uv add`、開発用の依存（テスト・型検査・リントなど）は `uv add --dev` を使用する。`pip install` や手動での `pyproject.toml` 編集は行わず、uv 経由で管理して `uv.lock` を更新する。

```sh
uv add <パッケージ名>                 # 実行時依存
uv add --dev <パッケージ名>           # 開発用依存
uv add "boto3-stubs[ec2]"            # extras 付きの追加例
```

現在の主な依存は以下の通り（`pyproject.toml`）。

- 実行時依存: `boto3`、`boto3-stubs[ec2]`（型スタブ。EC2 の extras を指定）
- 開発用依存: `pytest`、`hypothesis`、`moto`、`mypy`、`ruff`

### コマンドの実行

すべてのツール実行は `uv run` を通して行い、プロジェクトの仮想環境で実行する。

```sh
uv run python -m aws_eip_cleaner --help   # CLI の実行
uv run pytest                             # テスト
uv run mypy                               # 型検査
uv run ruff check                         # リント
uv run ruff format                        # フォーマット
```

## プロジェクト構成

uv の標準的な src レイアウトを採用する。ソースは `src/aws_eip_cleaner/` に、テストは `tests/` に配置する。

```
aws-eip-cleaner/
├── pyproject.toml            # プロジェクト定義・依存・ruff/mypy 設定
├── uv.lock                   # 依存のロックファイル
├── README.md
├── docs/
│   ├── developer.md          # 本ドキュメント
│   └── usage.md              # 利用者向けドキュメント
├── src/
│   └── aws_eip_cleaner/
│       ├── __init__.py
│       ├── __main__.py       # python -m aws_eip_cleaner のエントリポイント
│       ├── py.typed          # 型情報を提供するマーカ
│       ├── cli.py
│       ├── runner.py
│       ├── parallel.py
│       ├── scanner.py
│       ├── release.py
│       ├── regions.py
│       ├── credentials.py
│       ├── confirm.py
│       ├── display.py
│       ├── models.py
│       └── errors.py
└── tests/                    # pytest / Hypothesis / moto によるテスト
```

### 各モジュールの責務

| モジュール | 層 | 責務 |
| --- | --- | --- |
| `cli` | オーケストレーション | `argparse` による引数解析（`build_parser` / `parse_args`）、オプション検証（`validate_options`）、認証解決から並列調査・一覧表示・モード分岐・解放までの結線（`main`）、終了コード決定（`determine_exit_code`）。`--yes`/`--dry-run` の排他と `--region` 指定回数上限（50）を検証する。 |
| `runner` | 純粋ロジック（分岐） | 実行モードごとの解放オーケストレーション。`run_dry_run`（表示のみ）、`run_auto_approve`（一括解放と集計）、`run_interactive`（1 件ずつ確認して解放）。解放処理・入力受付は `release_fn` / `input_fn` として注入で受け取り、AWS SDK に直接依存しない。 |
| `parallel` | 純粋ロジック + I/O 結線 | 並列度決定（`compute_max_workers` = `min(16, region_count)`）、結果集約（`aggregate`）、`ThreadPoolExecutor` による最大 16 並列の調査実行（`scan_regions`）。 |
| `scanner` | 純粋ロジック + I/O | 未利用 EIP 抽出（`extract_unused_eips`、純粋関数）と単一リージョン調査（`scan_region`、`describe_addresses` 呼び出しと失敗の隔離）。 |
| `release` | I/O | `release_address` による単一 EIP の解放（`release_eip`）。`ClientError` を `EipReleaseError` へ変換する。 |
| `regions` | 純粋ロジック + I/O | リージョン正規化（`normalize_regions`）・検証（`validate_regions`）と、利用可能リージョン取得（`list_available_regions`）・対象リージョン解決（`resolve_target_regions`）。 |
| `credentials` | I/O | boto3 `Session` の生成・認証解決（`resolve_session`）と型付き `EC2Client` 生成（`create_ec2_client`、標準リトライ設定を適用）。botocore 例外をツール固有例外へ変換する。 |
| `confirm` | 純粋ロジック | 確認入力の解釈（`interpret_input`、`ConfirmDecision`）と 1 件分の確認フロー（`prompt_decision`、無効入力は最大 3 回まで再入力、EOF は再送出）。 |
| `display` | 純粋ロジック + I/O | 未利用 EIP 一覧の整形（`format_eip_list`、純粋関数）と標準出力への書き出し（`print_eip_list`）。 |
| `models` | データ | 不変データクラス（`UnusedEip` / `RegionScanResult` / `AggregatedResult` / `ReleaseSummary`）。 |
| `errors` | 例外 | 例外階層の定義。基底 `AwsEipCleanerError` と派生例外群。 |

## アーキテクチャ概要

### レイヤ分離

AWS API に依存する I/O 層と、外部依存を持たない純粋ロジック層を明確に分離している。純粋ロジック層は入出力が明確な純粋関数として切り出され、Hypothesis のプロパティテストで検証する。I/O 層は moto によるモックと例外系ユニットテストで検証する。

- **純粋ロジック層**（PBT 対象）: `regions.normalize_regions` / `validate_regions`、`scanner.extract_unused_eips`、`parallel.compute_max_workers` / `aggregate`、`display.format_eip_list`、`confirm.interpret_input`、`cli.determine_exit_code`、`runner` のモード分岐・集計。
- **I/O 層**（moto でモック検証）: `credentials`（Session / Client 生成）、`regions.list_available_regions`、`scanner.scan_region`（`describe_addresses`）、`release.release_eip`（`release_address`）。

`runner` は解放処理と入力受付を `release_fn` / `input_fn` として注入で受け取り、モード分岐と集計を副作用なくテストできる形にしている。同様に `cli` は `_build_release_fn` で `EC2Client` をリージョン単位でキャッシュした解放関数を組み立て、`_scan_all_regions` で調査関数を構築して `parallel.scan_regions` に渡す。

### ThreadPoolExecutor による並列調査

`parallel.scan_regions` は `ThreadPoolExecutor(max_workers=compute_max_workers(len(regions)))` で各リージョンの調査関数を最大 16 並列で実行する。`concurrent.futures.as_completed` で全 future の完了を待ってから `aggregate` で集約する。

各 future 内で発生する調査失敗は `scan_region` が例外を送出せず失敗結果（`RegionScanResult(error=...)`）として返すため、1 リージョンの失敗が他リージョンへ波及しない。`scan_region` は API 失敗時に部分取得結果を破棄し、失敗として扱う。

### 例外階層

すべてのツール由来の例外は基底例外 `AwsEipCleanerError` を継承する。組み込み・ライブラリ由来の例外（botocore の `ProfileNotFound` / `NoCredentialsError` / `ClientError` など）は素通しせず、ツール固有例外へ変換して送出する。一部の例外は意味的分類のため標準例外も併せて継承する。

```
Exception
└── AwsEipCleanerError                         # 基底例外
    ├── OptionConflictError                    # --yes と --dry-run の併用
    ├── TooManyRegionsError(ValueError)        # --region 指定回数が上限（50）超過
    ├── InvalidRegionError(ValueError)         # 無効なリージョン名の指定
    ├── RegionListingError(RuntimeError)       # リージョン一覧取得の失敗
    ├── ProfileNotFoundError                   # 認証プロファイル不在
    ├── CredentialResolutionError              # 認証情報の解決失敗
    ├── RegionScanError(RuntimeError)          # 単一リージョンの EIP 列挙失敗
    └── EipReleaseError(RuntimeError)          # EIP 解放の失敗
```

例外変換の対応関係:

- `ProfileNotFound` → `ProfileNotFoundError`
- `NoCredentialsError` / 認証系 `ClientError` → `CredentialResolutionError`
- `describe_addresses` の `ClientError` → `scan_region` 内で捕捉し失敗結果へ隔離
- `release_address` の `ClientError` → `EipReleaseError`
- リージョン一覧取得の失敗 → `RegionListingError`

### 終了コード

`cli.determine_exit_code` が解放集計（`ReleaseSummary`）と調査失敗の有無から最終的な終了コードを決定する。

- 正常完了（解放失敗・調査失敗なし、0 件、dry-run 正常表示）: `0`
- 解放失敗が 1 件以上、または調査失敗リージョンが 1 件以上: 非ゼロ（`1`）
- `--yes` と `--dry-run` の併用: `2`
- 認証失敗・リージョン一覧取得失敗・無効リージョン・指定回数超過などツール固有例外: 非ゼロ（`1`）
- 未知オプション・不正値・`--help` などの argparse 起因: argparse の `SystemExit`（不正は `2`、`--help` は `0`）

## テスト

テストには [pytest](https://docs.pytest.org/) を使用し、`tests/` に配置する。純粋ロジック層は [Hypothesis](https://hypothesis.readthedocs.io/) のプロパティテスト、AWS API を伴う I/O 層は [moto](https://docs.getmoto.org/) によるモックで検証する。

### 実行

```sh
uv run pytest                                # 全テスト
uv run pytest tests/test_scanner_io.py       # 特定ファイル
uv run pytest -k extract_unused_eips         # 名前で絞り込み
```

### プロパティテスト（Hypothesis）

純粋ロジック層の各性質（Correctness Property）を、それぞれプロパティテストとして実装している。各テストは最低 100 反復（`@settings(max_examples=100)`）で評価し、対応する設計プロパティを参照するコメントタグを付す。

```python
# Feature: aws-eip-cleaner, Property 3: 未利用 EIP 抽出は ...
@settings(max_examples=100)
@given(addresses=st.lists(_address(), max_size=20), region=_REGION)
def test_extract_unused_eips_matches_unassociated_and_preserves_fields(...): ...
```

生成器（strategy）は入力空間を意図的に制約して作る。例えば未利用 EIP 抽出のテストでは、`AssociationId` の有無・空文字・キー欠損を混在させたアドレス集合を生成し、抽出の網羅性を高めている。

### moto によるモック

boto3 を使う I/O 処理のテストでは、実 AWS API を呼ばず moto でモックする。`@mock_aws` デコレータを付けたテスト内で EIP を割り当て、`describe_addresses` による全件列挙や `release_address` の呼び出しを検証する。API 例外系は `monkeypatch` でクライアントメソッドを差し替えて再現する。

```python
from moto import mock_aws

@mock_aws
def test_scan_region_lists_all_and_extracts_unused() -> None:
    client = boto3.client("ec2", region_name="us-east-1")
    client.allocate_address(Domain="vpc")
    result = scan_region(client, "us-east-1")
    ...
```

## 型検査・リント

### 型検査（mypy strict）

すべての関数・メソッドの引数・戻り値（`-> None` を含む）に型ヒントを付ける。boto3 のクライアントには `boto3-stubs[ec2]` の型（`mypy_boto3_ec2.client.EC2Client` など）を使う。型記法は Python 3.14 の標準的なもの（`X | None`、`list[X]`、`dict[K, V]`）を用いる。

```sh
uv run mypy
```

mypy は strict モードで、`src` と `tests` の双方を対象とする（`pyproject.toml` の `[tool.mypy]`）。

### リント・フォーマット（Ruff）

フォーマットとリントは [Ruff](https://docs.astral.sh/ruff/) に統一する（isort / black は個別に導入しない）。docstring のスタイルチェック（`D` ルール、numpy convention）も Ruff で行う。

```sh
uv run ruff format     # フォーマット適用
uv run ruff check      # リント
```

`pyproject.toml` の設定では `select = ["E", "F", "I", "D"]` を有効化し、pydocstyle の convention を `numpy` に設定している。日本語 docstring は句点「。」で終わるため、英語ピリオドを要求する `D400` / `D415` は無効化している。

## コーディング規約（要点）

本リポジトリの steering（`.kiro/steering/python.md`）に従う。主な点は以下の通り。

- import は絶対 import に統一する（相対 import を使わない）。
- 型ヒントを全関数・メソッドの引数・戻り値に付ける。
- 公開モジュール・クラス・関数・メソッドに日本語・numpy スタイルの docstring を付ける。
- コメントは非自明な内容（意図・背景・制約）のみに限定する。処理内容の説明は docstring に集約する。
- ロギングは標準 `logging`（`logger = logging.getLogger(__name__)`）を使用する。デバッグ・進捗出力に `print` は使わない（ただし一覧表示や確認プロンプトなど、利用者向けの意図的な出力は `print` を用いる）。
- エラーは `AwsEipCleanerError` を基底とするツール固有例外へ変換して送出する。組み込み・ライブラリ例外を素通しさせない。

## コントリビュート手順

1. 最新の状態を取り込み、作業用のブランチを作成する。
   ```sh
   git switch -c feature/<変更内容>
   ```
2. 依存を同期する。
   ```sh
   uv sync
   ```
3. 実装する。純粋ロジックと I/O を分離し、上記のコーディング規約に従う。新規の依存は `uv add` / `uv add --dev` で追加し `uv.lock` を更新する。
4. テストを追加する。純粋ロジックにはプロパティテスト（Hypothesis）と代表例・境界のユニットテスト、AWS 依存部分には moto によるモック統合テストを用意する。
5. ローカルで型検査・リント・テストを通す。
   ```sh
   uv run ruff format
   uv run ruff check
   uv run mypy
   uv run pytest
   ```
6. 変更内容が分かる粒度でコミットする。
7. ブランチをプッシュしてプルリクエストを作成する。PR 説明には変更概要・確認した内容（実行したチェック）を記載する。

すべてのチェック（`ruff format` / `ruff check` / `mypy` strict / `pytest`）が通ることを、レビュー依頼前の完了条件とする。
