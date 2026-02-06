"""note.com RSS fetcher for saving articles to Obsidian via GitHub."""
import json
import logging
import re
from datetime import datetime
from typing import List, Optional

import feedparser
import html2text
import pytz
import requests
from bs4 import BeautifulSoup

from adapters.outputs.github_output import GitHubOutput

logger = logging.getLogger(__name__)

# User-Agent to avoid 403 errors
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class NoteRSSFetcher:
    """Fetches articles from note.com RSS feeds and saves them as Markdown."""

    def __init__(self, config: dict, github_output: GitHubOutput):
        self.users = [
            u.strip()
            for u in config.get("users", "").split(",")
            if u.strip()
        ]
        self.base_path = config.get("path", "70_Note")
        self.interval = int(config.get("interval", 60))
        self.github = github_output
        self.timezone = pytz.timezone(config.get("timezone", "Asia/Tokyo"))

        self._converter = html2text.HTML2Text()
        self._converter.body_width = 0  # No line wrapping
        self._converter.unicode_snob = True
        self._converter.mark_code = True

    def _parse_rss(self, username: str) -> List[dict]:
        """Fetch and parse RSS feed for a note.com user.

        Returns list of dicts with keys: title, link, published.
        """
        url = f"https://note.com/{username}/rss"
        try:
            feed = feedparser.parse(
                url,
                request_headers={"User-Agent": USER_AGENT},
            )
            if feed.bozo and not feed.entries:
                logger.error(f"RSS parse error for {username}: {feed.bozo_exception}")
                return []

            articles = []
            for entry in feed.entries:
                published = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6]).strftime(
                        "%Y-%m-%d"
                    )
                articles.append(
                    {
                        "title": entry.get("title", "Untitled"),
                        "link": entry.get("link", ""),
                        "published": published,
                    }
                )
            logger.info(f"RSS: found {len(articles)} articles for {username}")
            return articles
        except Exception as e:
            logger.error(f"Failed to fetch RSS for {username}: {e}")
            return []

    def _fetch_article_content(self, url: str) -> Optional[str]:
        """Fetch article body HTML from a note.com article page.

        Strategy:
        1. __NEXT_DATA__ JSON (most reliable)
        2. Fallback: div with note-common-styles__textnote-body class
        3. Fallback: <article> tag
        """
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            if resp.status_code != 200:
                logger.error(f"Failed to fetch article {url}: HTTP {resp.status_code}")
                return None

            soup = BeautifulSoup(resp.text, "html.parser")

            # Strategy 1: __NEXT_DATA__
            next_data_tag = soup.find("script", id="__NEXT_DATA__")
            if next_data_tag and next_data_tag.string:
                try:
                    data = json.loads(next_data_tag.string)
                    # Navigate to article body in Next.js page props
                    props = data.get("props", {}).get("pageProps", {})
                    note = props.get("note", {})
                    body = note.get("body")
                    if body:
                        logger.debug(f"Extracted body from __NEXT_DATA__ for {url}")
                        return body
                except (json.JSONDecodeError, KeyError) as e:
                    logger.debug(f"__NEXT_DATA__ parse failed: {e}")

            # Strategy 2: note body class
            body_div = soup.find(
                "div", class_=re.compile(r"note-common-styles__textnote-body")
            )
            if body_div:
                logger.debug(f"Extracted body from textnote-body div for {url}")
                return str(body_div)

            # Strategy 3: <article> tag
            article = soup.find("article")
            if article:
                logger.debug(f"Extracted body from <article> tag for {url}")
                return str(article)

            logger.warning(f"Could not extract article body from {url}")
            return None

        except Exception as e:
            logger.error(f"Error fetching article {url}: {e}")
            return None

    def _html_to_markdown(self, html: str) -> str:
        """Convert HTML string to Markdown."""
        return self._converter.handle(html).strip()

    def _sanitize_filename(self, title: str) -> str:
        """Sanitize a title for use as a filename.

        Removes characters that are invalid in filenames and trims length.
        """
        # Remove/replace invalid filename characters
        sanitized = re.sub(r'[\\/:*?"<>|]', "", title)
        # Collapse whitespace
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        # Trim to reasonable length
        if len(sanitized) > 100:
            sanitized = sanitized[:100].rstrip()
        return sanitized or "Untitled"

    def _build_markdown(
        self,
        title: str,
        author: str,
        url: str,
        published: str,
        body_md: str,
    ) -> str:
        """Build frontmatter-annotated Markdown for a note.com article."""
        now = datetime.now(self.timezone).strftime("%Y-%m-%d")
        # Escape quotes in title for YAML
        safe_title = title.replace('"', '\\"')
        return (
            f"---\n"
            f'type: note_rss\n'
            f'source: "{url}"\n'
            f'author: "{author}"\n'
            f'title: "{safe_title}"\n'
            f'published: "{published}"\n'
            f'fetched: "{now}"\n'
            f"tags:\n"
            f"  - note\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"{body_md}\n"
        )

    def fetch_user_articles(self, username: str) -> List[dict]:
        """Fetch all articles from a user's RSS feed."""
        return self._parse_rss(username)

    def save_new_articles(self, username: str) -> int:
        """Fetch and save new articles for a user.

        Checks for existing files to avoid duplicates.

        Returns:
            Number of newly saved articles.
        """
        articles = self.fetch_user_articles(username)
        saved_count = 0

        for article in articles:
            title = article["title"]
            link = article["link"]
            published = article["published"]

            safe_title = self._sanitize_filename(title)
            filename = f"{username}/{safe_title}.md"

            # Check if already saved
            existing = self.github.get_existing_content(
                filename, base_path=self.base_path
            )
            if existing is not None:
                logger.debug(f"Already exists, skipping: {self.base_path}/{filename}")
                continue

            # Fetch full article content
            body_html = self._fetch_article_content(link)
            if body_html is None:
                logger.warning(f"Skipping article (no body): {title}")
                continue

            body_md = self._html_to_markdown(body_html)
            content = self._build_markdown(title, username, link, published, body_md)

            success = self.github.save(
                filename, content, append=False, base_path=self.base_path
            )
            if success:
                saved_count += 1
                logger.info(f"Saved article: {self.base_path}/{filename}")
            else:
                logger.error(f"Failed to save article: {self.base_path}/{filename}")

        return saved_count
