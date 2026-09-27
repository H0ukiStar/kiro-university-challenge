# Requirements Document

## Introduction

aws-eip-cleaner は、AWS アカウント上の未利用 Elastic IP（EIP）を検出して削除する CLI ツールである。コマンドラインオプションで調査対象リージョンや認証プロファイルを指定でき、複数リージョンを並列に調査する。削除対象を一覧化したうえで、対話的な確認を経て解放（release）する。ドライラン、確認スキップによる一括削除、標準的な認証情報解決チェーンへの対応を備える。

## Glossary

- **CLI_Tool**: 本ツール本体。argparse でオプションを解析し、EIP の調査・削除を統括する CLI アプリケーション。
- **EIP**: Elastic IP アドレス。AWS が提供する静的パブリック IPv4 アドレス。EC2 の `describe-addresses` で列挙され、`release-address` で解放される。
- **Unused_EIP**: いずれのリソース（EC2 インスタンスや ENI）にも関連付けられていない EIP。`Association ID` を持たない（`Association ID` が未設定または空文字である）割り当て済みアドレスを指す。
- **Allocation_ID**: EIP の割り当てを一意に識別する ID（例: `eipalloc-xxxx`）。VPC スコープの EIP の解放に使用する。
- **Association_ID**: EIP がリソースに関連付けられていることを示す ID（例: `eipassoc-xxxx`）。この ID を持たない EIP を未利用とみなす。
- **Region**: AWS のリージョン（例: `us-east-1`）。調査・削除の対象単位。有効な Region 名の一覧は boto3（botocore）が保持する EC2 サービスの既知リージョン一覧（`Session.get_available_regions("ec2")`）を基準とする。
- **Region_Scanner**: 単一リージョン内の EIP を列挙し、未利用 EIP を抽出する処理単位。
- **Credential_Resolver**: boto3 の標準認証情報解決チェーン、またはユーザ指定プロファイルに基づいて認証情報を解決する処理単位。
- **Dry_Run_Mode**: 削除対象の一覧表示のみを行い、実際の解放を行わない実行モード。
- **Interactive_Confirmation**: 削除対象を 1 件ずつユーザに提示し、削除可否の入力を求める確認処理。
- **Auto_Approve_Mode**: 対話確認をスキップし、削除対象を一括で解放する実行モード（`--yes` で有効化）。

## Requirements

### Requirement 1: コマンドラインオプションの解析

**User Story:** 運用者として、コマンドラインオプションでツールの挙動を制御したい。実行時にリージョンや認証、削除モードを柔軟に切り替えられるようにするため。

#### Acceptance Criteria

1. THE CLI_Tool SHALL argparse を用いてコマンドラインオプションを解析する
2. IF 未知のオプションが指定された場合, THEN THE CLI_Tool SHALL 使用方法（対応するすべてのオプション名と概要を含む）を標準エラー出力に表示し、未知のオプションを指定した旨を示すエラーメッセージを標準エラー出力に表示し、いかなる削除処理も実行せずに終了コード 2 で終了する
3. WHEN `--help` が指定された場合, THE CLI_Tool SHALL 各オプションの名前・引数の要否・説明を標準出力に表示し、いかなる削除処理も実行せずに終了コード 0 で終了する
4. IF オプションの値が想定する形式に合致しない場合, THEN THE CLI_Tool SHALL 該当オプション名と不正である旨を示すエラーメッセージを標準エラー出力に表示し、いかなる削除処理も実行せずに終了コード 2 で終了する
5. WHEN いずれのオプションも指定されずに実行された場合, THE CLI_Tool SHALL 各オプションの既定値を適用して処理を継続する

### Requirement 2: 調査対象リージョンの指定

**User Story:** 運用者として、調査対象のリージョンを指定または全リージョンに設定したい。必要な範囲だけを効率的に調査するため。

#### Acceptance Criteria

1. WHEN CLI_Tool が起動され `--region` オプションが 1 つ以上指定された場合, THE CLI_Tool SHALL 指定された Region（重複指定は 1 件に統合する）のみを調査対象とする
2. IF CLI_Tool の起動時に `--region` オプションが 1 つも指定されなかった場合, THEN THE CLI_Tool SHALL 呼び出しに使用した認証情報でアクセス可能な全 Region を調査対象とする
3. THE CLI_Tool SHALL `--region` オプションの複数回指定を 1 回以上 50 回以下の範囲で受け付け、同一の Region 名が複数回指定された場合は 1 件として扱う。IF `--region` の指定回数（重複排除前）が 50 回を超えた場合, THEN THE CLI_Tool SHALL 指定回数が上限を超えた旨のエラーメッセージを標準エラー出力に表示し、いずれの Region に対しても調査を実行せずに非ゼロの終了コードで終了する
4. IF `--region` に boto3（botocore）の EC2 既知リージョン一覧（`Session.get_available_regions("ec2")`）に含まれない値が 1 つ以上指定された場合, THEN THE CLI_Tool SHALL 該当する Region 名が無効である旨のエラーメッセージを標準エラー出力に表示し、いずれの Region に対しても調査を実行せずに非ゼロの終了コードで終了する
5. IF `--region` オプションが 1 つも指定されず、かつアクセス可能な全 Region の取得に失敗した場合, THEN THE CLI_Tool SHALL Region 一覧の取得に失敗した旨のエラーメッセージを標準エラー出力に表示し、調査を実行せずに非ゼロの終了コードで終了する

### Requirement 3: 認証情報の解決

**User Story:** 運用者として、標準の認証情報チェーンまたは指定プロファイルで認証したい。環境に応じた認証方式を選べるようにするため。

#### Acceptance Criteria

1. WHEN `--profile` オプションが指定されずに認証処理が開始された場合, THE Credential_Resolver SHALL boto3 の標準認証情報解決チェーンを用いて認証情報を解決する
2. WHERE `--profile` オプションが指定された場合, THE Credential_Resolver SHALL 指定されたプロファイル名を用いて認証情報を解決する
3. IF 指定されたプロファイル名が認証情報ソースに存在しない場合, THEN THE CLI_Tool SHALL 該当プロファイルが見つからない旨を示すエラーメッセージを標準エラー出力に表示し、認証情報を取得せずに 1 以上の終了コードで終了する
4. IF 認証情報の解決に失敗した場合, THEN THE CLI_Tool SHALL 認証に失敗した旨を示すエラーメッセージを標準エラー出力に表示し、1 以上の終了コードで終了する
5. WHEN 認証情報の解決が成功した場合, THE Credential_Resolver SHALL 解決した認証情報を用いて後続処理で使用するクライアントを生成できる状態にする

### Requirement 4: リージョン間の並列調査

**User Story:** 運用者として、複数リージョンの調査を並列に実行したい。多数のリージョンを対象にしても短時間で結果を得るため。

#### Acceptance Criteria

1. WHEN 2 つ以上の Region が調査対象となった場合, THE CLI_Tool SHALL 各 Region の Region_Scanner を同時に最大 16 並列まで並行して実行する
2. WHILE いずれかの Region の調査が未完了である間, THE CLI_Tool SHALL 全 Region の調査完了を待機し、集約処理を開始しない
3. WHEN すべての Region の調査が完了した場合, THE CLI_Tool SHALL 各 Region の調査結果を 1 つの集約結果に統合する
4. IF ある Region の調査中にエラーが発生した場合, THEN THE CLI_Tool SHALL 当該 Region の識別子とエラー内容を記録し、当該 Region を失敗として集約結果に含め、他の Region の調査を継続する
5. IF 1 つ以上の Region の調査がエラーで失敗し、かつ 1 つ以上の Region が成功した場合, THEN THE CLI_Tool SHALL 成功した Region の結果を集約結果に含めたうえで処理を継続する

### Requirement 5: 未利用 EIP の検出

**User Story:** 運用者として、未利用の EIP を検出したい。不要な課金対象を特定して削除できるようにするため。

#### Acceptance Criteria

1. WHEN あるリージョンの調査が実行された場合, THE Region_Scanner SHALL 当該リージョンの割り当て済み EIP をすべて列挙する
2. IF 当該リージョンに割り当て済み EIP が 1 件も存在しない場合, THEN THE Region_Scanner SHALL 空の Unused_EIP 一覧を返し、当該リージョンをエラーなしで処理完了として扱う
3. THE Region_Scanner SHALL 列挙した割り当て済み EIP のうち、Association_ID を持たない（Association_ID が未設定または空である）各 EIP を Unused_EIP として抽出する
4. THE Region_Scanner SHALL 抽出した各 Unused_EIP について、Allocation_ID、パブリック IP アドレス、リージョン、関連付け状態（Unused_EIP は関連付けなし）の 4 項目を記録する
5. IF EIP の列挙処理が AWS API 呼び出しの失敗により完了できない場合, THEN THE Region_Scanner SHALL 当該リージョンの列挙を失敗として扱い、失敗したリージョンと失敗理由を示すエラー情報を呼び出し元に通知し、部分的に取得した EIP を Unused_EIP として記録しない

### Requirement 6: 削除対象一覧の表示

**User Story:** 運用者として、削除対象の一覧を確認したい。削除を実行する前に対象を把握するため。

#### Acceptance Criteria

1. WHEN すべての調査が完了した場合, THE CLI_Tool SHALL 検出した各 Unused_EIP を Allocation_ID、パブリック IP アドレス、リージョン、関連付け状態の各項目を含む形で 1 件 1 行の一覧として標準出力に表示する
2. WHEN 検出した Unused_EIP を一覧表示する場合, THE CLI_Tool SHALL 一覧の先頭または末尾に検出件数の合計を表示する
3. IF Unused_EIP が 1 件も検出されなかった場合, THEN THE CLI_Tool SHALL 削除対象が 0 件である旨を示すメッセージを標準出力に表示し、終了コード 0 で終了する
4. WHEN 一覧を表示する場合, THE CLI_Tool SHALL 検出件数を 0 件から 100000 件までの範囲で全件を表示する
5. IF 検出件数が 100000 件を超えた場合, THEN THE CLI_Tool SHALL 件数を打ち切らずに検出した全件を表示する

### Requirement 7: ドライランモード

**User Story:** 運用者として、削除せずに対象一覧だけを確認したい。実削除の前に影響範囲を安全に検証するため。

#### Acceptance Criteria

1. WHERE `--dry-run` オプションが指定された場合, THE CLI_Tool SHALL 削除対象となる各 EIP について割り当て ID・パブリック IP アドレス・リージョン・関連付け状態を含む一覧を標準出力に表示し、いかなる EIP の解放も行わない
2. WHERE `--dry-run` オプションが指定された場合, THE CLI_Tool SHALL 対話確認を行わずに処理を完了する
3. WHERE `--dry-run` オプションが指定され、かつ削除対象の EIP が 0 件の場合, THE CLI_Tool SHALL 対象が存在しない旨のメッセージを標準出力に表示し、EIP の解放を行わずに正常終了する
4. WHERE `--dry-run` オプションが指定された場合, THE CLI_Tool SHALL 表示した削除対象の総件数を標準出力に表示する

### Requirement 8: 対話的な削除確認

**User Story:** 運用者として、削除対象を 1 件ずつ確認しながら削除したい。誤削除を防ぐため。

#### Acceptance Criteria

1. WHERE `--dry-run` と `--yes` のいずれも指定されなかった場合, THE Interactive_Confirmation SHALL 各 Unused_EIP を 1 件ずつ、当該 EIP を一意に識別できる情報（割り当て ID とパブリック IP アドレス）とともに提示し、承認は `y`、拒否は `n` の 1 文字入力（大文字・小文字を区別しない）を求める
2. WHEN ユーザが承認入力（`y` または `Y`）を行った場合, THE CLI_Tool SHALL 当該 EIP を解放する
3. WHEN ユーザが拒否入力（`n` または `N`）を行った場合, THE CLI_Tool SHALL 当該 EIP を解放せず次の Unused_EIP へ進む
4. IF ユーザが承認（`y`/`Y`）でも拒否（`n`/`N`）でもない入力を行った場合, THEN THE Interactive_Confirmation SHALL 当該 EIP を解放せず、入力が無効である旨を示すメッセージを提示したうえで同一の EIP について再度入力を求め、再入力の要求は同一の EIP につき最大 3 回までとする
5. IF 同一の EIP について無効な入力が 3 回連続した場合, THEN THE Interactive_Confirmation SHALL 当該 EIP を解放せずに拒否として扱い、次の Unused_EIP へ進む
6. IF 標準入力が閉じられた（EOF）または処理が中断された場合, THEN THE CLI_Tool SHALL 残りの全 Unused_EIP を解放せずに処理を終了する
7. IF EIP の解放に失敗した場合, THEN THE CLI_Tool SHALL 当該 EIP を解放済みとして扱わず、解放に失敗した旨を示すエラーメッセージを提示し、次の Unused_EIP へ進む
8. WHEN すべての Unused_EIP の確認・解放処理が完了した場合, IF 1 件以上の解放失敗があった場合, THEN THE CLI_Tool SHALL 少なくとも 1 件の失敗があったことを示す非ゼロの終了コードで終了し、ELSE THE CLI_Tool SHALL 終了コード 0 で終了する

### Requirement 9: 確認スキップによる一括削除

**User Story:** 運用者として、確認をスキップして一括削除したい。多数の対象を効率的に削除するため。

#### Acceptance Criteria

1. WHERE `--yes` オプションが指定された場合, THE Auto_Approve_Mode SHALL 対話確認を行わずにすべての Unused_EIP を解放する
2. WHERE `--yes` オプションが指定された場合, WHEN 一括解放処理を開始する, THE Auto_Approve_Mode SHALL 解放対象となった Unused_EIP の総数を表示する
3. WHERE `--yes` オプションが指定された場合, WHEN すべての Unused_EIP の解放処理が完了する, THE Auto_Approve_Mode SHALL 解放に成功した件数と解放に失敗した件数を表示する
4. WHERE `--yes` オプションが指定された場合, IF いずれかの Unused_EIP の解放に失敗した場合, THEN THE Auto_Approve_Mode SHALL 失敗した対象を特定できる識別子と失敗理由を示すエラーメッセージを表示し、残りの Unused_EIP の解放処理を継続したうえで、少なくとも 1 件の失敗があったことを示す非ゼロの終了コードで終了する
5. IF `--yes` と `--dry-run` の両方が指定された場合, THEN THE CLI_Tool SHALL 両オプションが排他である旨のエラーメッセージを表示し、いかなる Unused_EIP も解放せずに非ゼロの終了コードで終了する
6. WHERE `--yes` オプションが指定された場合, IF 解放対象となる Unused_EIP が 0 件の場合, THEN THE Auto_Approve_Mode SHALL 解放対象が存在しない旨のメッセージを表示し、いかなる解放処理も行わずにゼロの終了コードで終了する

### Requirement 10: EIP の解放処理

**User Story:** 運用者として、承認した EIP を確実に解放したい。課金対象の未利用リソースを取り除くため。

#### Acceptance Criteria

1. WHEN ある EIP の解放が承認された場合, THE CLI_Tool SHALL 当該 EIP の Allocation_ID を用いて解放を実行する
2. WHEN ある EIP の解放が成功した場合, THE CLI_Tool SHALL 解放成功を Allocation_ID とともに INFO レベルでログ出力する
3. IF ある EIP の解放に失敗した場合, THEN THE CLI_Tool SHALL 当該 EIP の解放失敗を Allocation_ID およびエラー内容とともに ERROR レベルでログ出力し、当該 EIP を失敗件数に計上したうえで残りの対象の処理を中断せず継続する
4. IF ある EIP の解放がスロットリングや一時的なサーバエラーなどのリトライ可能な API エラーで失敗した場合, THEN THE CLI_Tool SHALL boto3（botocore）の標準リトライ機構（指数バックオフを含む）により当該解放を再試行し、リトライは合計 3 回の試行を上限とする
5. IF ある EIP の解放が認証失敗や割り当て ID 不正などのリトライ不能な API エラーで失敗した場合, THEN THE CLI_Tool SHALL 当該解放を再試行せずに失敗として扱う
6. WHEN すべての解放処理が完了した場合, THE CLI_Tool SHALL 解放成功件数と解放失敗件数をそれぞれ 0 以上の整数として集計し、両件数を表示する
