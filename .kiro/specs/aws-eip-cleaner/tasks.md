# Implementation Plan: aws-eip-cleaner

## Overview

設計のモジュール構成（`src/aws_eip_cleaner/` の各モジュール）に沿って、コーディング作業のみを段階的・テスト駆動で積み上げる。まず uv によるプロジェクト初期化と依存整備、例外階層・データモデルという土台を用意し、以降は純粋ロジック層を先に実装して各層に対応する Correctness Property を Hypothesis のプロパティテスト（各 100 反復）で検証する。AWS API に依存する I/O 層は moto によるモック統合テストと例外系ユニットテストで検証する。最後にオーケストレーション（`cli` / `runner`）で全体を結線し、mypy strict / ruff check / pytest を通す。

各タスクは requirements の該当項目を `_Requirements: X.Y_`、対応する Correctness Property を `_Properties: N_` の形式で参照する。`*` 付きサブタスクはテスト関連で任意実装。

## Tasks

- [x] 1. プロジェクト初期化と土台整備
  - `aws-eip-cleaner/` ディレクトリを作成し、uv で src レイアウトのプロジェクトを初期化する（`aws-eip-cleaner/pyproject.toml`, `README.md`, `uv.lock`, `src/aws_eip_cleaner/__init__.py`, `tests/__init__.py`）
  - 依存を追加する: `uv add boto3` / `uv add "boto3-stubs[ec2]"`
  - 開発依存を追加する: `uv add --dev pytest hypothesis moto mypy ruff`
  - `pyproject.toml` に steering 準拠の設定を記述する（`[tool.ruff] target-version = "py314"`, `[tool.ruff.lint] select = ["E","F","I","D"]`, `[tool.ruff.lint.pydocstyle] convention = "numpy"`, `[tool.mypy] python_version = "3.14"` / `strict = true`）
  - `python -m aws_eip_cleaner` 用に `src/aws_eip_cleaner/__main__.py` の骨組み（`from aws_eip_cleaner.cli import main` を呼び出し `raise SystemExit(main())`）を作成する
  - _Requirements: 1.1_

- [x] 2. 例外階層とデータモデル
  - [x] 2.1 例外階層を実装する（`errors.py`）
    - `AwsEipCleanerError` を基底に、`OptionConflictError`, `TooManyRegionsError(ValueError)`, `InvalidRegionError(ValueError)`, `RegionListingError(RuntimeError)`, `ProfileNotFoundError`, `CredentialResolutionError`, `RegionScanError(RuntimeError)`, `EipReleaseError(RuntimeError)` を定義する
    - 各例外に日本語 numpy スタイル docstring を付す
    - _Requirements: 2.3, 2.4, 3.3, 3.4, 5.5, 9.5, 10.3_

  - [x] 2.2 データモデルを実装する（`models.py`）
    - `UnusedEip`（frozen dataclass: `allocation_id`, `public_ip`, `region`, `association_id: str | None = None`）を定義する
    - `RegionScanResult`（`region`, `unused_eips`, `error: str | None`, `succeeded` プロパティ）を定義する
    - `AggregatedResult`（`unused_eips`, `succeeded_regions`, `failed_regions: dict[str, str]`, `has_scan_failure` プロパティ）を定義する
    - `ReleaseSummary`（`succeeded`, `failed`, `total` プロパティ）を定義する
    - _Requirements: 5.4, 4.3, 10.6_

- [x] 3. リージョン正規化・検証（純粋ロジック層）
  - [x] 3.1 `normalize_regions` / `validate_regions` を実装する（`regions.py`）
    - `normalize_regions`: 重複排除しつつ順序を安定させて返す
    - `validate_regions`: 全要素が `available` に含まれることを検証し、含まれない値があれば `InvalidRegionError` を送出する
    - _Requirements: 2.1, 2.3, 2.4_

  - [x] 3.2 リージョン正規化のプロパティテストを書く
    - **Property 1: リージョン正規化は一意集合と等価かつ冪等**
    - `# Feature: aws-eip-cleaner, Property 1` タグと本文コメントを付す。`@settings(max_examples=100)`
    - 重複・順序ばらつきを含むリージョンリストを生成し、一意集合との等価性と冪等性を検証する
    - _Requirements: 2.1, 2.3_
    - _Properties: 1_

  - [x] 3.3 リージョン検証のプロパティテストを書く
    - **Property 2: リージョン検証は無効値を 1 つでも含めば拒否する**
    - `# Feature: aws-eip-cleaner, Property 2` タグと本文コメントを付す。`@settings(max_examples=100)`
    - 全要素が利用可能集合に含まれる場合のみ成功、1 つでも含まれなければ `InvalidRegionError` を検証する
    - _Requirements: 2.4_
    - _Properties: 2_

- [x] 4. 未利用 EIP 抽出（純粋ロジック層）
  - [x] 4.1 `extract_unused_eips` を実装する（`scanner.py`）
    - `describe_addresses` 相当のアドレス集合から `AssociationId` 未設定または空のものを `UnusedEip`（`association_id=None`）として抽出する
    - `allocation_id`・`public_ip` は元アドレス由来、`region` は引数由来とする
    - _Requirements: 5.2, 5.3, 5.4_

  - [x] 4.2 未利用 EIP 抽出のプロパティテストを書く
    - **Property 3: 未利用 EIP 抽出は Association_ID 非保持の EIP と厳密一致しフィールドを保持する**
    - `# Feature: aws-eip-cleaner, Property 3` タグと本文コメントを付す。`@settings(max_examples=100)`
    - `AssociationId` の有無・空文字を混在させたアドレス集合を生成し、抽出結果の厳密一致とフィールド保持、空入力時の空出力を検証する
    - _Requirements: 5.2, 5.3, 5.4_
    - _Properties: 3_

- [x] 5. 結果集約と並列度決定（純粋ロジック層）
  - [x] 5.1 `aggregate` / `compute_max_workers` を実装する（`parallel.py`）
    - `aggregate`: 成功/失敗リージョンを分類し、成功リージョンの EIP のみを統合した `AggregatedResult` を返す
    - `compute_max_workers`: `min(limit, region_count)` を返す（`region_count>=1` 前提）
    - _Requirements: 4.1, 4.3, 4.4, 4.5_

  - [x] 5.2 集約のプロパティテストを書く
    - **Property 4: 集約は全リージョンを漏れなく分類し成功結果の EIP を保持する**
    - `# Feature: aws-eip-cleaner, Property 4` タグと本文コメントを付す。`@settings(max_examples=100)`
    - 成功・失敗混在の調査結果リストを生成し、成功/失敗集合の直和が全入力に一致すること、失敗集合が `error` 保持と一致すること、統合 EIP が成功分のみであることを検証する
    - _Requirements: 4.3, 4.4, 4.5_
    - _Properties: 4_

  - [x] 5.3 並列度決定のユニットテストを書く
    - `compute_max_workers` が `min(16, n)` を返すことを境界 n=1, 15, 16, 17 で検証する
    - _Requirements: 4.1_

- [x] 6. 一覧整形（純粋ロジック層）
  - [x] 6.1 `format_eip_list` / `print_eip_list` を実装する（`display.py`）
    - `format_eip_list`: 各 EIP を Allocation_ID・パブリック IP・リージョン・関連付け状態を含む 1 行に整形し、合計件数の行を含める。打ち切りは行わない。`association_id is None` は「関連付けなし」文言に整形する
    - `print_eip_list`: 整形結果を標準出力へ書き出す
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 7.1, 7.4_

  - [x] 6.2 一覧整形のプロパティテストを書く
    - **Property 5: 一覧整形は全対象を 1 行ずつ全項目付きで表示し件数を含め打ち切らない**
    - `# Feature: aws-eip-cleaner, Property 5` タグと本文コメントを付す。`@settings(max_examples=100)`
    - 明細行数が入力件数と一致、各行に全 4 項目が含まれること、合計件数表示が含まれることを検証する
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 7.1, 7.4_
    - _Properties: 5_

- [x] 7. 確認入力の解釈（純粋ロジック層）
  - [x] 7.1 `ConfirmDecision` / `interpret_input` を実装する（`confirm.py`）
    - `interpret_input`: 正規化後（トリム・小文字化）が `"y"` で APPROVE、`"n"` で REJECT、それ以外を INVALID とする
    - _Requirements: 8.2, 8.3, 8.4_

  - [x] 7.2 入力解釈のプロパティテストを書く
    - **Property 6: 確認入力の解釈は y/n（大小無視）以外をすべて無効とする**
    - `# Feature: aws-eip-cleaner, Property 6` タグと本文コメントを付す。`@settings(max_examples=100)`
    - 特殊文字・空文字・空白を含む任意 Unicode 文字列を生成し、分類を検証する
    - _Requirements: 8.2, 8.3, 8.4_
    - _Properties: 6_

  - [x] 7.3 `prompt_decision` を実装する（`confirm.py`）
    - 1 件の EIP について承認/拒否を得る。無効入力は最大 3 回まで再入力を求め、3 回連続無効なら REJECT として扱う。`input_fn` を注入可能にし、`EOFError` は再送出する
    - _Requirements: 8.1, 8.5_

  - [x] 7.4 `prompt_decision` のユニットテストを書く
    - 無効入力 3 連続で REJECT になること（境界）、承認/拒否の即時解決、EOF での再送出を擬似 `input_fn` で検証する
    - _Requirements: 8.1, 8.5_

- [x] 8. チェックポイント - 純粋ロジック層のテストを通す
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 終了コード決定（純粋ロジック層）
  - [x] 9.1 `determine_exit_code` を実装する（`cli.py`）
    - `ReleaseSummary` と調査失敗の有無から終了コードを決定する。調査失敗なし前提で `failed > 0` のとき非ゼロ、`failed == 0` のとき 0。調査失敗ありなら非ゼロ
    - _Requirements: 8.8, 9.4, 10.6_

  - [x] 9.2 終了コード決定のプロパティテストを書く
    - **Property 9: 解放集計は非負かつ合計整合で、失敗があるときのみ非ゼロ終了する**
    - `# Feature: aws-eip-cleaner, Property 9` タグと本文コメントを付す。`@settings(max_examples=100)`
    - 成功/失敗をランダムに返す解放関数から得た集計で、`succeeded`/`failed` が非負・和が件数一致、`determine_exit_code` が `failed>0` のときのみ非ゼロを検証する
    - _Requirements: 8.8, 9.4, 10.6_
    - _Properties: 9_

- [x] 10. 解放オーケストレーション（純粋ロジック層の分岐）
  - [x] 10.1 `run_dry_run` を実装する（`runner.py`）
    - 一覧と総件数を表示し、解放・対話を一切行わない。終了コードを返す
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 10.2 dry-run のプロパティテストを書く
    - **Property 7: dry-run では解放も対話も一切発生しない**
    - `# Feature: aws-eip-cleaner, Property 7` タグと本文コメントを付す。`@settings(max_examples=100)`
    - 任意の EIP リストで解放関数呼び出し回数が 0、対話が発生しないことを検証する
    - _Requirements: 7.1, 7.2_
    - _Properties: 7_

  - [x] 10.3 `run_auto_approve` を実装する（`runner.py`）
    - 総数を表示し全件を解放、成功/失敗を集計する。部分失敗（`EipReleaseError`）を捕捉し ERROR ログ後に失敗計上して継続する
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6, 10.3_

  - [x] 10.4 yes モードのプロパティテストを書く
    - **Property 8: yes モードは全対象に対し解放を 1 回ずつ試行する**
    - `# Feature: aws-eip-cleaner, Property 8` タグと本文コメントを付す。`@settings(max_examples=100)`
    - 任意の EIP リストで各 EIP に解放が 1 回ずつ試行され、対話が発生しないことを検証する
    - _Requirements: 9.1_
    - _Properties: 8_

  - [x] 10.5 yes モードの件数表示・0 件ユニットテストを書く
    - 総数表示・成功/失敗件数表示（9.2, 9.3）、0 件時のメッセージと終了コード 0（9.6）を検証する
    - _Requirements: 9.2, 9.3, 9.6_

  - [x] 10.6 `run_interactive` を実装する（`runner.py`）
    - 1 件ずつ確認し承認分のみ解放、成功/失敗を集計する。`EOFError` で残りを中断する。解放失敗は捕捉・ERROR ログ・失敗計上して次へ進む
    - _Requirements: 8.6, 8.7_

  - [x] 10.7 対話モードのユニットテストを書く
    - 擬似 `input_fn` で EOF 中断（残りが解放されない: 8.6）、解放失敗時の継続（8.7）を検証する
    - _Requirements: 8.6, 8.7_

- [x] 11. チェックポイント - オーケストレーションのテストを通す
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. 認証解決（I/O 層）
  - [x] 12.1 `resolve_session` / `create_ec2_client` を実装する（`credentials.py`）
    - `resolve_session`: `profile is None` なら標準チェーン、指定時はそのプロファイル。`ProfileNotFound` → `ProfileNotFoundError`、`NoCredentialsError`/認証系 `ClientError` → `CredentialResolutionError` に変換する
    - `create_ec2_client`: 指定リージョンの型付き `EC2Client` を生成し、`Config(retries={"max_attempts": 3, "mode": "standard"})` を適用する
    - _Requirements: 3.1, 3.2, 3.5, 10.4_

  - [x] 12.2 認証成功の moto モック統合テストを書く
    - profile 有無で Session 生成引数が切り替わり、クライアント生成が成功することを検証する
    - _Requirements: 3.1, 3.2, 3.5_

  - [x] 12.3 認証失敗・リトライ設定のユニットテストを書く
    - プロファイル不在で `ProfileNotFoundError`、認証失敗で `CredentialResolutionError`（3.3, 3.4）、生成 Config の `retries` が `{"max_attempts": 3, "mode": "standard"}`（10.4）を検証する
    - _Requirements: 3.3, 3.4, 10.4_

- [x] 13. リージョン列挙（I/O 層）
  - [x] 13.1 `list_available_regions` / `resolve_target_regions` を実装する（`regions.py`）
    - `list_available_regions`: `Session.get_available_regions("ec2")` 相当でアクセス可能リージョンを取得、失敗時 `RegionListingError`
    - `resolve_target_regions`: 指定があれば正規化+検証、無指定なら全リージョンを返す
    - _Requirements: 2.2, 2.5_

  - [x] 13.2 リージョン列挙の moto モック・例外ユニットテストを書く
    - 全リージョン取得（2.2）と取得失敗時の `RegionListingError`・非ゼロ終了（2.5）を検証する
    - _Requirements: 2.2, 2.5_

- [x] 14. EIP 列挙・解放（I/O 層）
  - [x] 14.1 `scan_region` を実装する（`scanner.py`）
    - `describe_addresses` で全件列挙し `extract_unused_eips` に渡す。API `ClientError` は捕捉して `RegionScanResult(error=...)` に変換し、部分取得結果を破棄する
    - _Requirements: 5.1, 5.5_

  - [x] 14.2 `scan_region` の moto モック・例外ユニットテストを書く
    - moto で EIP を割り当て全件列挙（5.1）、API 例外時に失敗扱いで部分結果を記録しないこと（5.5）を検証する
    - _Requirements: 5.1, 5.5_

  - [x] 14.3 `release_eip` を実装する（`release.py`）
    - `Allocation_ID` を用いて `release_address` を実行する。リトライ可能エラーは botocore 標準リトライに委譲。失敗時 `EipReleaseError` に変換。成功は INFO ログ（Allocation_ID）
    - _Requirements: 10.1, 10.2, 10.4, 10.5_

  - [x] 14.4 `release_eip` の moto モック・ログユニットテストを書く
    - moto で Allocation_ID 指定の解放（10.1）、リトライ不能エラーで 1 回失敗確定（10.5）、`caplog` で INFO/ERROR に Allocation_ID が含まれること（10.2, 10.3）を検証する
    - _Requirements: 10.1, 10.2, 10.3, 10.5_

- [x] 15. 並列調査の結線（I/O + 並列）
  - [x] 15.1 `scan_regions` を実装する（`parallel.py`）
    - `ThreadPoolExecutor(max_workers=compute_max_workers(...))` で各リージョンを最大 16 並列調査し、`as_completed` で全 future 完了後に `aggregate` を呼ぶ。各 future の例外は `scan_fn` が失敗結果として返すため他へ波及しない
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 15.2 `scan_regions` のユニットテストを書く
    - 擬似 `scan_fn` で全 future 完了後に集約されること（4.2）、1 リージョン失敗が他へ波及せず継続すること（4.4, 4.5）を検証する
    - _Requirements: 4.2, 4.4, 4.5_

- [ ] 16. CLI 引数解析・オプション検証・全体オーケストレーション
  - [ ] 16.1 `build_parser` / `parse_args` / `validate_options` を実装する（`cli.py`）
    - `--region`（append, 既定 `[]`）, `--profile`（既定 None）, `--dry-run`（store_true）, `--yes`（store_true）を定義する
    - `validate_options`: `--yes`/`--dry-run` 併用で `OptionConflictError`、`--region` 指定回数（重複排除前）が 50 超で `TooManyRegionsError`
    - _Requirements: 1.1, 1.5, 2.3, 9.5_

  - [ ]* 16.2 引数解析・検証のユニットテストを書く
    - Namespace/既定値（1.1, 1.5）、未知オプション・不正値で `SystemExit(2)` と stderr（1.2, 1.4）、`--help` で `SystemExit(0)` と stdout（1.3）、併用で `OptionConflictError`・非ゼロ終了・解放未実行（9.5）、`--region` 境界 50 受理/51 で `TooManyRegionsError`・非ゼロ終了（2.3）を検証する
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.3, 9.5_

  - [ ] 16.3 `main` を実装して全体を結線する（`cli.py` / `__main__.py`）
    - 解析 → 検証 → 認証解決 → 対象リージョン決定 → 並列調査 → 集約 → 一覧表示 → 0 件分岐（6.3）→ モード分岐（dry-run/yes/対話）→ 集計 → `determine_exit_code` で終了コードを返す
    - `OptionConflictError`/`SystemExit(2)` 系はコード 2、その他の `AwsEipCleanerError` は非ゼロ（1）にマッピングする
    - _Requirements: 1.1, 6.1, 6.2, 6.3, 8.8, 9.4, 10.6_

  - [ ]* 16.4 `main` の 0 件境界・終了コード統合テストを書く
    - 0 件検出時に各モードで対象なしメッセージと終了コード 0（6.3, 7.3, 9.6）、解放失敗/調査失敗時の非ゼロ終了を擬似依存注入で検証する
    - _Requirements: 6.3, 7.3, 9.6_

- [ ] 17. 最終チェックポイント - 型検査・リント・全テストを通す
  - `uv run mypy`（strict）でエラーがないことを確認する
  - `uv run ruff format` を適用し `uv run ruff check` でエラーがないことを確認する
  - `uv run pytest` で全テスト（プロパティ・ユニット・moto 統合）が通ることを確認する
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 18. ドキュメント作成
  - [ ] 18.1 開発者向けドキュメントを作成する（`aws-eip-cleaner/docs/developer.md`）
    - 開発環境セットアップ（uv、`uv sync` / `uv add` による依存インストール）を記載する
    - プロジェクト構成（src レイアウト、`src/aws_eip_cleaner/` 配下の各モジュールの責務: `cli` / `runner` / `parallel` / `scanner` / `release` / `regions` / `credentials` / `confirm` / `display` / `models` / `errors`）を記載する
    - テスト実行方法（`uv run pytest`、Hypothesis のプロパティテスト、moto によるモック）を記載する
    - 型検査・リント（`uv run mypy` の strict、`uv run ruff format` / `uv run ruff check`）を記載する
    - アーキテクチャ概要（例外階層、`ThreadPoolExecutor` による並列調査、純粋ロジック層と I/O 層のレイヤ分離）を記載する
    - コントリビュート手順を記載する
    - _Requirements: 1.1, 2.2, 3.1, 4.1, 5.1, 10.1_

  - [ ] 18.2 利用者向けドキュメントを作成する（`aws-eip-cleaner/docs/usage.md`）
    - インストール方法と前提（AWS 認証情報）を記載する
    - CLI オプション一覧（`--region` / `--profile` / `--dry-run` / `--yes`）と各説明を記載する
    - 代表的な使用例（全リージョン dry-run、特定リージョン指定、プロファイル指定、`--yes` による一括削除）を記載する
    - 未利用 EIP の定義、終了コードの意味、注意事項（解放は取り消せない等）を記載する
    - _Requirements: 1.3, 2.1, 2.2, 3.1, 5.2, 6.1, 7.1, 8.1, 9.1, 10.1, 10.6_

  - [ ] 18.3 リポジトリ直下の README を整備する（`aws-eip-cleaner/README.md`）
    - ツールの概要説明を記載する
    - クイックスタート（インストールと最小実行例）を記載する
    - 主要オプションの要約を記載する
    - `docs/developer.md` と `docs/usage.md` へのリンクを記載する
    - _Requirements: 1.1, 1.3, 2.1, 3.1, 7.1_

## Notes

- `*` 付きサブタスクはテスト関連で任意（MVP では省略可）。トップレベルタスクとチェックポイントは必須。
- 各タスクは requirements を `_Requirements: X.Y_`、Correctness Property を `_Properties: N_` で参照する。
- 純粋ロジック層（Property 1〜9）は Hypothesis で各 100 反復（`@settings(max_examples=100)`）、`# Feature: aws-eip-cleaner, Property N: ...` タグを付す。
- I/O 層（credentials, regions 列挙, scan_region, release）は moto モック統合テストと例外系ユニットテストで検証する。
- 型ヒント・docstring（日本語 numpy スタイル）・logging・独自例外変換など steering（structure.md / python.md）に厳密準拠する。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["3.1", "4.1", "5.1", "6.1", "7.1", "9.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "4.2", "5.2", "5.3", "6.2", "7.2", "7.3", "9.2", "10.1", "10.3", "10.6"] },
    { "id": 4, "tasks": ["7.4", "10.2", "10.4", "10.5", "10.7", "12.1", "13.1", "14.1", "14.3"] },
    { "id": 5, "tasks": ["12.2", "12.3", "13.2", "14.2", "14.4", "15.1", "16.1"] },
    { "id": 6, "tasks": ["15.2", "16.2", "16.3"] },
    { "id": 7, "tasks": ["16.4"] },
    { "id": 8, "tasks": ["18.1", "18.2", "18.3"] }
  ]
}
```
