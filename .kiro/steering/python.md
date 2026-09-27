---
inclusion: always
---

# Python 開発規約

本プロジェクトは Python を使用したツールを開発する。以下の規約に従うこと。

## コーディングスタイル

- [PEP 8](https://peps.python.org/pep-0008/) を順守すること。
- import は絶対 import に統一すること（相対 import を使わない）。曖昧さがなく、PEP 8 の推奨にも沿うため。

## 型ヒント

- すべての関数・メソッドの引数と戻り値に型ヒントを記載すること。
  - 型が自明な場合でも必ず記載する。
  - 戻り値の型（`-> None` を含む）も省略しない。
- 変数についても、型が推論しにくい場合や可読性が向上する場合は型注釈を付けること。
- 記法は Python 3.14 の標準的なものを使用すること。
  - `Optional[X]` ではなく `X | None`。
  - `Union[X, Y]` ではなく `X | Y`。
  - `List[X]` / `Dict[K, V]` などではなく組み込みの `list[X]` / `dict[K, V]`。
- boto3 を使用する場合は型スタブ（[`boto3-stubs`](https://pypi.org/project/boto3-stubs/)）を利用し、型ヒントを効かせること。
  - 利用するサービスに対応する extras を指定してインストールする（例: `uv add --dev "boto3-stubs[ec2]"`）。
  - クライアント・リソースの型注釈には `mypy_boto3_*` の型を使用する（例: `EC2Client`）。
- 型チェックには [mypy](https://mypy.readthedocs.io/) を使用すること。
  - `uv run mypy` で検査する。CI や動作確認の一環として実行する。

```python
from boto3.session import Session
from mypy_boto3_ec2.client import EC2Client


def create_ec2_client(session: Session) -> EC2Client:
    """EC2 クライアントを生成する。

    Parameters
    ----------
    session : Session
        boto3 のセッション。

    Returns
    -------
    EC2Client
        型付けされた EC2 クライアント。
    """
    return session.client("ec2")
```

## docstring

- すべての公開モジュール・クラス・関数・メソッドに docstring を記載すること。
- 日本語で記述すること。
- [numpy スタイル](https://numpydoc.readthedocs.io/en/latest/format.html) を使用すること。

```python
def add(x: int, y: int) -> int:
    """2 つの整数を加算する。

    Parameters
    ----------
    x : int
        加算する値。
    y : int
        加算する値。

    Returns
    -------
    int
        x と y の合計。
    """
    return x + y
```

## コメント方針

- コメントには非自明な内容のみを書くこと。
  - コードを読めば分かる処理内容をそのまま説明するコメントは書かない。
  - なぜそうしているか（意図・背景・制約・トレードオフ）など、コードから読み取れない情報を書く。
- Kiro の spec 開発に特有のコメント（`req-1.4` のような要件 ID への参照など）はコードに残さないこと。ノイズになるため。
- 処理内容の説明は docstring に集約し、実装中の逐次的なコメントは最小限にとどめること。

```python
# 悪い例: コードを読めば分かる／spec 由来のノイズ
count = count + 1  # count に 1 を足す
# req-1.4: EIP を解放する
release_eip(allocation_id)

# 良い例: 非自明な意図を説明する
# AWS 側の結果整合性で解放直後は一覧に残るため、リトライ前に待機する
time.sleep(RELEASE_PROPAGATION_WAIT_SECONDS)
```

## ロギング

- ログ出力には標準ライブラリの [`logging`](https://docs.python.org/3/library/logging.html) を使用すること。
  - デバッグや進捗の出力に `print` を使わない。
  - モジュールごとに `logger = logging.getLogger(__name__)` でロガーを取得する。
  - ログレベル（`debug` / `info` / `warning` / `error`）を用途に応じて適切に使い分ける。

```python
import logging

logger = logging.getLogger(__name__)


def release_eip(allocation_id: str) -> None:
    """EIP を解放する。

    Parameters
    ----------
    allocation_id : str
        解放対象の割り当て ID。
    """
    logger.info("EIP を解放します: %s", allocation_id)
```

## エラーハンドリング

- エラーは既存のクラス（`Exception` や標準例外、ライブラリ提供の例外など）を基底とし、独自のエラークラスを作成して利用すること。
  - ツール全体の基底となる例外クラスを 1 つ用意し、個別のエラーはそれを継承させる。
  - 状況に応じた適切な標準例外（`ValueError`、`RuntimeError` など）を基底に選ぶこと。
- 組み込み例外をそのまま `raise` するのではなく、ツール固有の意味を持つ独自例外に変換して送出すること。

```python
class AwsEipCleanerError(Exception):
    """本ツールの基底例外。"""


class EipReleaseError(AwsEipCleanerError):
    """EIP の解放に失敗した場合の例外。"""
```

## リンター / フォーマッター

- [Ruff](https://docs.astral.sh/ruff/) を使用すること。
  - `isort`（import 並び替え）や `black`（フォーマット）の代替として Ruff で統一する。個別に isort / black を導入しない。
  - docstring のスタイルチェックも Ruff で行う（`pydocstyle` 系ルール `D` を有効化し、numpy convention を指定する）。
- フォーマットは `ruff format`、リントは `ruff check` を使用すること。

`pyproject.toml` の設定例:

```toml
[tool.ruff]
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "I", "D"]

[tool.ruff.lint.pydocstyle]
convention = "numpy"
```

mypy の設定例:

```toml
[tool.mypy]
python_version = "3.14"
strict = true
```

## テスト

- テストには [pytest](https://docs.pytest.org/) を使用すること。
- テストコードは各ツールの `tests` ディレクトリに配置すること。
- boto3 を使う処理のテストでは、実 AWS API を呼ばず [moto](https://docs.getmoto.org/) でモックすること。
  - `uv add --dev moto` で導入する。

## 環境 / パッケージ管理

- 環境構築とパッケージ管理には [uv](https://docs.astral.sh/uv/) を使用すること。
- 依存関係の追加は `uv add`、開発用依存は `uv add --dev` を使用すること。
- コマンド実行は `uv run`（例: `uv run pytest`、`uv run ruff check`）を使用すること。

## フォルダ構成

各 Python ツールの内部は、uv の標準的な src レイアウトを採用すること。リポジトリ全体の構成は `structure.md` を参照。

```
aws-eip-cleaner/              # ツールのルートディレクトリ
├── pyproject.toml
├── README.md
├── uv.lock
├── src/
│   └── aws_eip_cleaner/
│       └── __init__.py
└── tests/
    └── __init__.py
```

- ソースコードは `src/<パッケージ名>/` に、テストは `tests/` に配置すること。
- パッケージ名はツールのディレクトリ名に対応させ、Python の識別子として有効な形（ハイフンをアンダースコアに置換した `aws_eip_cleaner`）にすること。
