# Discord-Obsidian Bot アーキテクチャドキュメント

## 概要

Discord のメッセージを AI で整形し、GitHub API 経由で Obsidian Vault に保存する Bot。
Obsidian の知識管理機能（内部リンク、階層タグ、コールアウト等）を最大限に活かした形式で保存する。

## ディレクトリ構成

```
discord-obsidian-bot/
├── main.py                          # エントリーポイント、設定読み込み、Bot クラス
├── processor.py                     # メッセージ処理（AI 整形 + フォールバック）
├── adapters/
│   ├── base.py                      # 抽象基底クラス（MessageData, BaseInputAdapter 等）
│   ├── inputs/
│   │   └── discord_input.py         # Discord メッセージ受信
│   ├── outputs/
│   │   └── github_output.py         # GitHub API でファイル保存
│   └── ai/
│       ├── prompt.py                # AI プロンプト定義（メモ/日記/読書）
│       ├── ollama_ai.py             # Ollama ネイティブ API アダプタ
│       └── openai_ai.py             # OpenAI 互換 API アダプタ
├── docker-compose.yml               # Docker 環境変数設定
├── Dockerfile                       # コンテナビルド定義
├── config.yaml.example              # YAML 設定ファイルのサンプル
├── requirements.txt                 # Python 依存パッケージ
└── .github/workflows/
    └── docker-publish.yml           # ghcr.io への自動ビルド/プッシュ
```

## データフロー

```
Discord メッセージ
    │
    ▼
┌─────────────────┐
│  DiscordInput    │  メッセージ受信、channel_type 判定
│  discord_input.py│  → MessageData に変換
└────────┬────────┘
         │ MessageData
         ▼
┌─────────────────┐    ┌──────────────────┐
│  Bot             │───▶│  GitHubOutput    │  既存ファイルを取得
│  main.py         │◀───│  github_output.py│  （AI 統合用）
└────────┬────────┘    └──────────────────┘
         │ MessageData + existing_content
         ▼
┌─────────────────┐    ┌──────────────────┐
│ MessageProcessor │───▶│  AI Adapter      │  AI で整形
│ processor.py     │◀───│  ollama/openai   │  （失敗時はフォールバック）
└────────┬────────┘    └──────────────────┘
         │ filename, content, append
         ▼
┌─────────────────┐
│  GitHubOutput    │  GitHub API で保存
│  github_output.py│  → Obsidian Vault に反映
└─────────────────┘
```

## チャンネルタイプ

3 種類のチャンネルタイプがあり、それぞれ処理方式が異なる。

### memo（メモ）

| 項目 | 値 |
|------|-----|
| 環境変数 | `CHANNEL_MEMO` |
| 保存先 | `GITHUB_PATH_MEMO`（デフォルト: `Inbox`） |
| ファイル名 | `2026-02-03.md`（日付ベース） |
| 蓄積単位 | 1 日 1 ファイル |
| 保存方式 | 既存ファイルあり → AI 統合で上書き / なし → 新規作成 |

### diary（日記）

| 項目 | 値 |
|------|-----|
| 環境変数 | `CHANNEL_DIARY` |
| 保存先 | `GITHUB_PATH_DIARY`（デフォルト: `Diary`） |
| ファイル名 | `2026-02-03.md`（日付ベース） |
| 蓄積単位 | 1 日 1 ファイル |
| 保存方式 | memo と同じ（プロンプトが日記向け） |

### reading（読書）

| 項目 | 値 |
|------|-----|
| 環境変数 | `CHANNEL_READING` |
| 保存先 | `GITHUB_PATH_READING`（デフォルト: `Reading`） |
| ファイル名 | `{書籍タイトル}.md`（AI が抽出） |
| 蓄積単位 | 1 冊 1 ファイル |
| 保存方式 | 常に上書き（AI が既存 + 新規を統合） |

reading は他と異なり、AI を 2 回呼び出す:

1. **タイトル抽出**（軽量）: メッセージから書籍タイトルを取得 → ファイル名に使用
2. **ノート整形**（通常）: 既存内容 + 新メッセージを統合

タイトル抽出に失敗した場合は、日付ベースのファイル名にフォールバックする。

## アダプタパターン

抽象基底クラスが `adapters/base.py` に定義されている。

### MessageData

全アダプタ間で受け渡されるメッセージの共通フォーマット:

```python
@dataclass
class MessageData:
    content: str           # メッセージ本文
    author: str            # 投稿者名
    timestamp: datetime    # 投稿日時（UTC）
    channel: str           # チャンネル名
    attachments: List[str] # 添付ファイル URL リスト
    channel_type: str      # "memo" | "diary" | "reading"
```

### BaseInputAdapter

メッセージ入力元の抽象クラス。現在は Discord のみ実装。

- `run()`: メッセージ監視を開始
- `stop()`: 監視を停止

### BaseOutputAdapter

出力先の抽象クラス。現在は GitHub のみ実装。

- `save(filename, content, append)`: ファイルを保存

### BaseAIAdapter

AI 整形の抽象クラス。Ollama と OpenAI 互換の 2 つを実装。

- `is_available()`: サービスの死活確認
- `format_message(content, metadata, existing_content)`: メッセージを整形
- `extract_book_title(content)`: 書籍タイトルを抽出（reading 用）

## AI 整形の仕組み

### プロンプト構成（adapters/ai/prompt.py）

| 定数 | 用途 |
|------|------|
| `MEMO_SYSTEM_PROMPT` | メモ用システムプロンプト |
| `DIARY_SYSTEM_PROMPT` | 日記用システムプロンプト |
| `READING_SYSTEM_PROMPT` | 読書ノート用システムプロンプト |
| `BOOK_TITLE_EXTRACTION_PROMPT` | 書籍タイトル抽出用プロンプト |

`get_system_prompt(channel_type)` で channel_type に応じたプロンプトを取得する。

`build_user_prompt(content, metadata, existing_content)` でユーザープロンプトを組み立てる。
既存ファイル内容がある場合は `【既存のObsidianファイル内容】` と `【新しいメモ内容】` を
明確に分けて AI に渡す。

### Obsidian 最適化

AI プロンプトは以下の Obsidian 機能を活用するよう指示している:

- **内部リンク `[[]]`**: 人名、場所、概念、プロジェクト、書籍名をリンク化
- **階層タグ**: `場所/渋谷`、`ジャンル/技術書` のようなネストタグ
- **コールアウト**: `> [!quote]`、`> [!tip]`、`> [!warning]`、`> [!question]`
- **frontmatter**: `type`、`source`、`author`、`status` 等の Dataview 互換フィールド

### フォールバック

AI が利用不可の場合（Ollama 停止中、ネットワークエラー等）:

1. AI 整形を試みる
2. 失敗した場合 → プレーン Markdown テンプレートで保存
3. reading のタイトル抽出が失敗 → 日付ベースのファイル名を使用

## 既存ファイル統合の仕組み

同じ日に複数回メッセージを送った場合、単純な追記ではなく AI による統合を行う。

### 処理の流れ（main.py の `_handle_message`）

```
1. save_path を channel_type から決定
2. ファイル名を計算（reading は AI でタイトル抽出）
3. GitHub から既存ファイルを取得（get_existing_content）
4. processor.process() に既存内容を渡す
5. AI が統合成功 → append=False（上書き保存）
6. AI が失敗 → append=True（単純追記）
```

### frontmatter 重複防止（processor.py の `_strip_frontmatter`）

AI 非統合モード（既存ファイルなし + daily テンプレート）の場合、
AI が生成した frontmatter を除去してから追記する。
これにより同一ファイルに frontmatter が複数回出現することを防ぐ。

## 設定方法

### 環境変数（推奨）

`config.yaml` なしで動作する。全設定を環境変数で行う。

```bash
# 必須
DISCORD_TOKEN=...          # Discord Bot トークン
GITHUB_TOKEN=...           # GitHub Personal Access Token
GITHUB_REPO=owner/repo     # リポジトリ名

# チャンネル設定（最低1つ必要）
CHANNEL_MEMO=123456        # メモ用チャンネル ID（カンマ区切りで複数可）
CHANNEL_DIARY=789012       # 日記用チャンネル ID
CHANNEL_READING=345678     # 読書用チャンネル ID
DISCORD_CHANNELS=123456    # 後方互換（memo として扱われる）

# 保存先パス
GITHUB_BRANCH=main
GITHUB_PATH_MEMO=Inbox     # メモ保存先（デフォルト: Inbox）
GITHUB_PATH_DIARY=Diary    # 日記保存先（デフォルト: Diary）
GITHUB_PATH_READING=Reading # 読書ノート保存先（デフォルト: Reading）

# プロセッサ
PROCESSOR_TIMEZONE=Asia/Tokyo
PROCESSOR_TEMPLATE=daily    # daily（日別） | single（1メッセージ1ファイル）

# AI 整形（任意）
AI_ENABLED=false            # true にすると AI 整形が有効
AI_PROVIDER=ollama          # ollama | openai
AI_BASE_URL=http://localhost:11434  # AI サービスの URL
AI_MODEL=gemma2             # 使用するモデル名
AI_API_KEY=                 # OpenAI 互換 API のキー（Ollama は不要）
AI_TIMEOUT=60               # AI リクエストのタイムアウト（秒）
```

### config.yaml（代替）

`config.yaml` が存在する場合はそちらが優先される。
`${VAR_NAME}` 形式で環境変数を参照できる。
`config.yaml.example` を参照。

### 設定の優先順位

```
config.yaml（あれば）> 環境変数
```

`load_config()` in `main.py` が決定する。

## デプロイ

### CI/CD パイプライン

```
git push / tag → GitHub Actions → Docker ビルド → ghcr.io にプッシュ
```

`.github/workflows/docker-publish.yml` で定義。
トリガー: `main` ブランチへの push、`v*` タグ、`workflow_dispatch`（手動）。

イメージ: `ghcr.io/tamo2918/discord-obsidian-bot`

### TrueNAS SCALE

Custom App として Kubernetes 上で動作する。
Docker CLI は使えない（k3s ベース）。
環境変数は TrueNAS UI の「Extra Environment Variables」で設定する。

## 新しいチャンネルタイプを追加する手順

例: `project` タイプを追加する場合。

### 1. プロンプト追加（adapters/ai/prompt.py）

```python
# prompt.py に追加
PROJECT_SYSTEM_PROMPT = """..."""

# SYSTEM_PROMPTS dict に追加
SYSTEM_PROMPTS = {
    "memo": MEMO_SYSTEM_PROMPT,
    "diary": DIARY_SYSTEM_PROMPT,
    "reading": READING_SYSTEM_PROMPT,
    "project": PROJECT_SYSTEM_PROMPT,   # 追加
}
```

`build_user_prompt()` の label 分岐にも追加:

```python
elif channel_type == "project":
    label = "プロジェクトメモ"
```

### 2. 環境変数・パスマップ追加（main.py）

`load_config_from_env()` に追加:

```python
project_channels = _parse_channels(os.environ.get("CHANNEL_PROJECT", ""))
for ch in project_channels:
    channel_map[ch] = "project"

path_map["project"] = os.environ.get("GITHUB_PATH_PROJECT", "Projects")
```

### 3. docker-compose.yml に環境変数追加

```yaml
- CHANNEL_PROJECT=${CHANNEL_PROJECT:-}
- GITHUB_PATH_PROJECT=${GITHUB_PATH_PROJECT:-Projects}
```

### 4. 特殊なファイル名ロジックが必要な場合

reading のように日付ベース以外のファイル名が必要な場合:

- `main.py` の `_handle_message()` に分岐を追加
- `processor.py` の `process()` に分岐を追加
- 必要に応じて `BaseAIAdapter` に新しいメソッドを追加

日付ベースで良い場合は追加の変更不要（memo/diary と同じ流れで動く）。

## 新しい AI プロバイダを追加する手順

### 1. アダプタ作成（adapters/ai/）

`BaseAIAdapter` を継承して実装:

```python
class NewProviderAI(BaseAIAdapter):
    def __init__(self, config: dict): ...
    def is_available(self) -> bool: ...
    def format_message(self, content, metadata, existing_content=None): ...
    def extract_book_title(self, content) -> Optional[str]: ...
```

### 2. ファクトリに登録（main.py）

`create_ai_adapter()` に分岐を追加:

```python
elif provider == "new_provider":
    from adapters.ai.new_provider_ai import NewProviderAI
    adapter = NewProviderAI(config)
```

## 技術スタック

| コンポーネント | 技術 |
|---------------|------|
| 言語 | Python 3.11 |
| Discord | discord.py >= 2.0 |
| HTTP | requests |
| 設定ファイル | PyYAML |
| タイムゾーン | pytz |
| コンテナ | Docker（非 root 実行） |
| CI/CD | GitHub Actions |
| レジストリ | GitHub Container Registry (ghcr.io) |
| デプロイ先 | TrueNAS SCALE (Kubernetes / k3s) |

## Discord Bot の権限

必要な Intents:

- `message_content`: メッセージ内容の読み取り
- `guild_messages`: サーバーメッセージの受信

Bot はメッセージ処理後にリアクションを付ける:
- 成功: ✅
- 失敗: ❌
