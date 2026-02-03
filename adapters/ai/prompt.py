"""Shared prompt templates for AI adapters."""

SYSTEM_PROMPT = """\
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


def build_user_prompt(content: str, metadata: dict) -> str:
    """
    Build a user prompt from message content and metadata.

    Args:
        content: Raw message content
        metadata: Dict with keys like timestamp, author, channel, attachments

    Returns:
        Formatted user prompt string
    """
    parts = [f"メモ内容:\n{content}"]

    if metadata.get("timestamp"):
        parts.append(f"日時: {metadata['timestamp']}")

    if metadata.get("channel"):
        parts.append(f"チャンネル: {metadata['channel']}")

    if metadata.get("attachments"):
        urls = "\n".join(metadata["attachments"])
        parts.append(f"添付画像:\n{urls}")

    return "\n\n".join(parts)
