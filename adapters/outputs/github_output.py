"""GitHub output adapter for saving files to a repository."""
import base64
import hashlib
import logging
import time
from typing import Optional, Tuple

import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class GitHubOutput:
    """GitHub output adapter that saves files to a repository."""

    API_BASE = "https://api.github.com"

    def __init__(self, config: dict):
        """
        Initialize the GitHub output adapter.

        Args:
            config: GitHub configuration containing token, repo, branch, and path
        """
        self.token = config["token"]
        self.repo = config["repo"]
        self.branch = config.get("branch", "main")
        self.base_path = config.get("path", "")

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get_file_path(self, filename: str) -> str:
        """Get full file path including base path."""
        if self.base_path:
            return f"{self.base_path}/{filename}"
        return filename

    def _get_file(self, filepath: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Get file content and SHA from GitHub.

        Args:
            filepath: Path to the file in the repository

        Returns:
            Tuple of (content, sha) or (None, None) if file doesn't exist
        """
        url = f"{self.API_BASE}/repos/{self.repo}/contents/{filepath}"
        params = {"ref": self.branch}

        response = requests.get(url, headers=self.headers, params=params)

        if response.status_code == 200:
            data = response.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return content, data["sha"]
        elif response.status_code == 404:
            return None, None
        else:
            logger.error(f"Failed to get file: {response.status_code} - {response.text}")
            return None, None

    def _create_or_update_file(
        self,
        filepath: str,
        content: str,
        sha: Optional[str] = None,
        message: str = "Update from Discord bot",
    ) -> bool:
        """
        Create or update a file in the repository.

        Args:
            filepath: Path to the file
            content: File content
            sha: Existing file SHA (for updates)
            message: Commit message

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.API_BASE}/repos/{self.repo}/contents/{filepath}"

        body = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": self.branch,
        }

        if sha:
            body["sha"] = sha

        response = requests.put(url, headers=self.headers, json=body)

        if response.status_code in (200, 201):
            return True
        else:
            logger.error(
                f"Failed to save file: {response.status_code} - {response.text}"
            )
            return False

    def get_existing_content(self, filename: str, base_path: str = None) -> Optional[str]:
        """
        Get existing file content from GitHub.

        Args:
            filename: Name of the file
            base_path: Override base path (e.g. "Diary" instead of default "Inbox")

        Returns:
            File content as string, or None if file doesn't exist
        """
        if base_path is not None:
            filepath = f"{base_path}/{filename}" if base_path else filename
        else:
            filepath = self._get_file_path(filename)

        content, _ = self._get_file(filepath)
        return content

    def save(
        self,
        filename: str,
        content: str,
        append: bool = False,
        base_path: str = None,
    ) -> bool:
        """
        Save content to a file in the GitHub repository.

        Args:
            filename: Name of the file to save
            content: Content to save
            append: If True, append to existing file; otherwise overwrite
            base_path: Override base path (e.g. "Diary" instead of default "Inbox")

        Returns:
            True if save was successful, False otherwise
        """
        if base_path is not None:
            filepath = f"{base_path}/{filename}" if base_path else filename
        else:
            filepath = self._get_file_path(filename)
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # Get existing file if it exists
                existing_content, sha = self._get_file(filepath)

                if append and existing_content:
                    # Append to existing content
                    final_content = existing_content + "\n" + content
                    message = f"Append message to {filename}"
                else:
                    final_content = content
                    message = (
                        f"Update {filename}"
                        if existing_content
                        else f"Create {filename}"
                    )

                success = self._create_or_update_file(
                    filepath, final_content, sha, message
                )

                if success:
                    logger.info(f"Successfully saved to {filepath}")
                    return True

            except requests.exceptions.RequestException as e:
                logger.error(f"Request error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    # Exponential backoff
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return False

        return False

    def upload_image(self, image_url: str, date_str: str, base_path: str = None) -> Optional[str]:
        """
        Download an image from a URL and upload it to GitHub.

        Args:
            image_url: URL of the image to download (e.g. Discord CDN)
            date_str: Date string for organizing (YYYY-MM format)
            base_path: Override base path for the attachments folder

        Returns:
            Relative path to the uploaded image for Obsidian, or None if failed
        """
        try:
            # Download image
            response = requests.get(image_url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Failed to download image: {response.status_code}")
                return None

            image_data = response.content

            # Determine filename from URL or content hash
            parsed_url = urlparse(image_url)
            original_name = parsed_url.path.split("/")[-1]

            # Add hash prefix to avoid collisions
            content_hash = hashlib.md5(image_data).hexdigest()[:8]
            filename = f"{content_hash}_{original_name}"

            # Upload path: _attachments/YYYY-MM/filename
            attachments_dir = "_attachments"
            if base_path:
                upload_path = f"{base_path}/{attachments_dir}/{date_str}/{filename}"
            elif self.base_path:
                upload_path = f"{self.base_path}/{attachments_dir}/{date_str}/{filename}"
            else:
                upload_path = f"{attachments_dir}/{date_str}/{filename}"

            # Check if already uploaded
            _, existing_sha = self._get_file(upload_path)
            if existing_sha:
                logger.info(f"Image already exists: {upload_path}")
                return upload_path

            # Upload to GitHub
            url = f"{self.API_BASE}/repos/{self.repo}/contents/{upload_path}"
            body = {
                "message": f"Upload image: {filename}",
                "content": base64.b64encode(image_data).decode("utf-8"),
                "branch": self.branch,
            }

            resp = requests.put(url, headers=self.headers, json=body)
            if resp.status_code in (200, 201):
                logger.info(f"Uploaded image to {upload_path}")
                return upload_path
            else:
                logger.error(f"Failed to upload image: {resp.status_code} - {resp.text}")
                return None

        except Exception as e:
            logger.error(f"Error uploading image: {e}")
            return None
