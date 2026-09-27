# EIP の解放手順

## 解放とは

- **release（解放）** = 割り当て（allocation）を AWS に返却する操作。これで課金が止まる。
- **disassociate（関連付け解除）** = リソースから IP を切り離すだけ。課金は止まらない。

未使用 EIP の掃除では通常 disassociate は不要（そもそも未関連付けが候補）。必要なのは release。

## API / コマンド

- VPC スコープの EIP: `AllocationId` を指定して解放する。
  - AWS CLI: `aws ec2 release-address --allocation-id eipalloc-xxxx --region <region>`
  - boto3: `client.release_address(AllocationId="eipalloc-xxxx")`
- EC2-Classic（現在はほぼ存在しない）は `PublicIp` 指定。新規環境では考慮不要。

## 不可逆性（最重要）

解放した IP アドレスは共有プールに戻り、**同じアドレスを再取得できる保証はない（実質的に不可能）**。allowlist や DNS に固定していた場合、復旧できない。この不可逆性が、ドライランと事前確認を必須にする理由。

## リトライと冪等性

- **リトライ可能エラー**（スロットリング `RequestLimitExceeded`、一時的な `5xx` など）は、指数バックオフで再試行する。boto3 なら標準リトライ機構に委譲するのが簡単。
  - 例: `Config(retries={"max_attempts": 3, "mode": "standard"})`
- **リトライ不能エラー**（`AuthFailure`、`InvalidAllocationID.NotFound` など）は再試行せず失敗として確定させる。
- **冪等性**: すでに解放済みの `AllocationId` を再度解放しようとすると `InvalidAllocationID.NotFound` になる。二重実行時はこれを「既に解放済み」として扱えるよう考慮する。
- **結果整合性**: 解放直後は `describe-addresses` の一覧に一時的に残ることがある。直後の再検証は少し待ってから行う。

## バッチ処理の方針

- 1 件の解放失敗で全体を止めない。失敗は記録して次へ進む。
- 全件処理後に成功件数・失敗件数を集計する。
- 1 件でも失敗があれば呼び出し側に非ゼロ終了で通知し、ユーザに再確認を促す。
- 失敗ログには `AllocationId`・`PublicIp`・リージョン・エラー理由を含める。

## 実行モードの使い分け

| モード | 挙動 | いつ使うか |
| --- | --- | --- |
| ドライラン | 一覧表示のみ、解放しない | 常に最初に実行して対象を確認 |
| 対話確認 | 1 件ずつ承認/拒否 | 既定。人間が確認できる規模 |
| 一括自動 | 全件を確認なしで解放 | 対象が多すぎて対話が非現実的なときのみ、明示合意の上で |

一括自動モードとドライランは同時指定しない（矛盾するため）。
