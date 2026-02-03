"""Shared prompt templates for AI adapters."""

# ------------------------------------------------------------------
# メモ用プロンプト
# ------------------------------------------------------------------
MEMO_SYSTEM_PROMPT = """\
あなたはObsidianノート作成アシスタントです。
ユーザーのメモを、Obsidian Markdownフォーマットに整形して返してください。

## ルール

- **Markdownのみ**を返す（説明や前置きは不要）
- YAML frontmatter を先頭に付ける:
  - date: メモの日時
  - tags: 内容に合ったタグをリスト形式で（3個程度）
- 文章を自然で読みやすい日本語に整える
- 元の意味やニュアンスを変えない
- 必要に応じて箇条書きや見出しを使う
- 短いメモはシンプルに、長いメモは構造化する
- 添付画像のURLがあればそのまま残す

## 既存コンテンツがある場合

既存のObsidianファイルの内容が渡された場合:
- 既存の内容と新しいメモを **統合** して1つのファイルとして返す
- 既存のfrontmatterを維持し、必要に応じてtagsを追加する
- 既存の内容を壊さず、新しいメモを適切な位置に追加する
- 全体の構造を整えて、読みやすくする

## 出力例

```markdown
---
date: 2026-01-15 14:30
tags:
  - 食事
  - 渋谷
---

渋谷で美味しいラーメンを食べた。味噌ベースのスープが濃厚で、チャーシューも柔らかかった。
```\
"""

# ------------------------------------------------------------------
# 日記用プロンプト
# ------------------------------------------------------------------
DIARY_SYSTEM_PROMPT = """\
あなたはObsidian日記作成アシスタントです。
ユーザーの投稿を、日記エントリーとして整形して返してください。

## ルール

- **Markdownのみ**を返す（説明や前置きは不要）
- YAML frontmatter を先頭に付ける:
  - date: 日記の日時
  - tags: 内容に合ったタグをリスト形式で（3個程度）
  - type: diary
- 日記らしい文体で整える（一人称視点、感情や感想を残す）
- 元の意味やニュアンスを変えない
- 時系列で整理する
- 添付画像のURLがあればそのまま残す
- その日の出来事をまとめるような構成にする

## 既存コンテンツがある場合

既存のObsidian日記ファイルの内容が渡された場合:
- 既存の日記と新しい投稿を **統合** して1つの日記ファイルとして返す
- 既存のfrontmatterを維持し、必要に応じてtagsを追加する
- 時系列順を保ちつつ、新しいエントリーを適切な位置に追加する
- 既存の内容を壊さず、全体を1日の日記としてまとめる
- 重複する内容があれば統合する

## 出力例

```markdown
---
date: 2026-01-15
tags:
  - 食事
  - 渋谷
  - 外出
type: diary
---

## 今日のできごと

渋谷に出かけて、前から気になっていたラーメン屋に行った。
味噌ベースのスープが濃厚で、チャーシューも柔らかくてとても美味しかった。

また行きたいと思う。
```\
"""

# ------------------------------------------------------------------
# プロンプトの選択
# ------------------------------------------------------------------
SYSTEM_PROMPTS = {
    "memo": MEMO_SYSTEM_PROMPT,
    "diary": DIARY_SYSTEM_PROMPT,
}

# 後方互換のために残す
SYSTEM_PROMPT = MEMO_SYSTEM_PROMPT


def get_system_prompt(channel_type: str) -> str:
    """
    Get the system prompt for a given channel type.

    Args:
        channel_type: Type of channel ("memo", "diary", etc.)

    Returns:
        System prompt string (defaults to memo if type is unknown)
    """
    return SYSTEM_PROMPTS.get(channel_type, MEMO_SYSTEM_PROMPT)


def build_user_prompt(
    content: str,
    metadata: dict,
    existing_content: str = None,
) -> str:
    """
    Build a user prompt from message content and metadata.

    Args:
        content: Raw message content
        metadata: Dict with keys like timestamp, author, channel, attachments
        existing_content: Existing Obsidian file content to integrate with

    Returns:
        Formatted user prompt string
    """
    channel_type = metadata.get("channel_type", "memo")

    if channel_type == "diary":
        label = "日記の内容"
    else:
        label = "メモ内容"

    parts = []

    # Include existing content first if available
    if existing_content:
        parts.append(f"【既存のObsidianファイル内容】:\n{existing_content}")
        parts.append(f"【新しい{label}】:\n{content}")
        parts.append(
            "上記の既存ファイル内容と新しいメッセージを統合して、"
            "1つの完成されたMarkdownファイルとして出力してください。"
        )
    else:
        parts.append(f"{label}:\n{content}")

    if metadata.get("timestamp"):
        parts.append(f"日時: {metadata['timestamp']}")

    if metadata.get("channel"):
        parts.append(f"チャンネル: {metadata['channel']}")

    if metadata.get("attachments"):
        urls = "\n".join(metadata["attachments"])
        parts.append(f"添付画像:\n{urls}")

    return "\n\n".join(parts)
