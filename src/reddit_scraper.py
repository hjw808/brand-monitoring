"""Reddit scraper module using PRAW."""

import logging
import os
from datetime import datetime
from typing import List, Dict, Optional, Union

import praw
from praw.models import Submission, Comment

logger = logging.getLogger(__name__)


class RedditScraper:
    """Scrapes brand mentions from Reddit using PRAW."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        user_agent: str = "BrandMonitor/1.0"
    ):
        """Initialize Reddit scraper.

        Args:
            client_id: Reddit API client ID (or set REDDIT_CLIENT_ID env var).
            client_secret: Reddit API client secret (or set REDDIT_CLIENT_SECRET env var).
            user_agent: User agent string for API requests.
        """
        self.client_id = client_id or os.environ.get("REDDIT_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("REDDIT_CLIENT_SECRET")
        self.user_agent = user_agent

        self._reddit = None

    @property
    def reddit(self) -> Optional[praw.Reddit]:
        """Get Reddit instance, initializing if needed."""
        if self._reddit is None and self.client_id and self.client_secret:
            self._reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent
            )
        return self._reddit

    def is_configured(self) -> bool:
        """Check if Reddit API credentials are configured."""
        return bool(self.client_id and self.client_secret)

    def search_posts(
        self,
        query: str,
        subreddits: Optional[List[str]] = None,
        sort: str = "relevance",
        time_filter: str = "week",
        limit: int = 25
    ) -> List[Dict[str, str]]:
        """Search Reddit posts for a query.

        Args:
            query: Search query (brand name + keywords).
            subreddits: List of subreddits to search (None for all).
            sort: Sort method ("relevance", "hot", "top", "new").
            time_filter: Time filter ("hour", "day", "week", "month", "year", "all").
            limit: Maximum number of results.

        Returns:
            List of post dictionaries.
        """
        if not self.reddit:
            return []

        results = []

        try:
            # Search in specific subreddits or all
            if subreddits:
                subreddit = self.reddit.subreddit("+".join(subreddits))
            else:
                subreddit = self.reddit.subreddit("all")

            for submission in subreddit.search(
                query,
                sort=sort,
                time_filter=time_filter,
                limit=limit
            ):
                results.append(self._parse_submission(submission))

        except Exception as e:
            logger.error("Error searching Reddit: %s", e)

        return results

    def get_subreddit_posts(
        self,
        subreddit_name: str,
        query: str,
        sort: str = "new",
        limit: int = 25
    ) -> List[Dict[str, str]]:
        """Get posts from a specific subreddit matching query.

        Args:
            subreddit_name: Name of subreddit.
            query: Search query.
            sort: Sort method.
            limit: Maximum number of results.

        Returns:
            List of post dictionaries.
        """
        if not self.reddit:
            return []

        results = []

        try:
            subreddit = self.reddit.subreddit(subreddit_name)

            for submission in subreddit.search(query, sort=sort, limit=limit):
                results.append(self._parse_submission(submission))

        except Exception as e:
            logger.error("Error getting subreddit posts: %s", e)

        return results

    def _parse_submission(self, submission: Submission) -> Dict[str, str]:
        """Parse a Reddit submission into a dictionary.

        Args:
            submission: PRAW Submission object.

        Returns:
            Dictionary with post details.
        """
        # Get selftext or indicate it's a link post
        content = submission.selftext if submission.selftext else f"[Link post to: {submission.url}]"

        return {
            "title": submission.title,
            "content": content[:5000],  # Limit content length
            "url": f"https://reddit.com{submission.permalink}",
            "author": str(submission.author) if submission.author else "[deleted]",
            "subreddit": submission.subreddit.display_name,
            "score": submission.score,
            "num_comments": submission.num_comments,
            "published_at": datetime.fromtimestamp(submission.created_utc),
            "source_type": "reddit"
        }

    def get_comments_for_post(
        self,
        post_url: str,
        limit: int = 20
    ) -> List[Dict[str, str]]:
        """Get comments for a Reddit post.

        Args:
            post_url: URL of the Reddit post.
            limit: Maximum number of comments.

        Returns:
            List of comment dictionaries.
        """
        if not self.reddit:
            return []

        results = []

        try:
            submission = self.reddit.submission(url=post_url)
            submission.comments.replace_more(limit=0)

            for comment in submission.comments.list()[:limit]:
                if isinstance(comment, Comment):
                    results.append({
                        "content": comment.body[:2000],
                        "author": str(comment.author) if comment.author else "[deleted]",
                        "score": comment.score,
                        "published_at": datetime.fromtimestamp(comment.created_utc),
                        "url": f"https://reddit.com{comment.permalink}",
                        "source_type": "reddit_comment"
                    })

        except Exception as e:
            logger.error("Error getting comments: %s", e)

        return results

    def search_brand(
        self,
        brand: str,
        keywords: Optional[List[str]] = None,
        subreddits: Optional[List[str]] = None,
        time_filter: str = "week",
        limit: int = 25
    ) -> List[Dict[str, str]]:
        """Search Reddit for brand mentions.

        Args:
            brand: Brand name.
            keywords: Additional keywords.
            subreddits: Specific subreddits to search.
            time_filter: Time filter for search.
            limit: Maximum results.

        Returns:
            List of post dictionaries.
        """
        # Build query
        query_parts = [brand]
        if keywords:
            query_parts.extend(keywords)
        query = " ".join(query_parts)

        return self.search_posts(
            query,
            subreddits=subreddits,
            time_filter=time_filter,
            limit=limit
        )


class RedditScraperNoAuth:
    """Fallback Reddit scraper without authentication (limited functionality)."""

    def __init__(self):
        """Initialize the no-auth scraper."""
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def search_posts(
        self,
        query: str,
        limit: int = 25
    ) -> List[Dict[str, str]]:
        """Search Reddit using JSON endpoint (no auth required, but limited).

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            List of post dictionaries.
        """
        results = []

        try:
            from urllib.parse import quote_plus
            url = f"https://www.reddit.com/search.json?q={quote_plus(query)}&limit={limit}&sort=relevance&t=week"

            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            for post in data.get("data", {}).get("children", []):
                post_data = post.get("data", {})
                results.append({
                    "title": post_data.get("title", ""),
                    "content": post_data.get("selftext", "")[:5000] or f"[Link post]",
                    "url": f"https://reddit.com{post_data.get('permalink', '')}",
                    "author": post_data.get("author", "[deleted]"),
                    "subreddit": post_data.get("subreddit", ""),
                    "score": post_data.get("score", 0),
                    "num_comments": post_data.get("num_comments", 0),
                    "published_at": datetime.fromtimestamp(post_data.get("created_utc", 0)),
                    "source_type": "reddit"
                })

        except Exception as e:
            logger.error("Error with Reddit JSON search: %s", e)

        return results

    def search_brand(
        self,
        brand: str,
        keywords: Optional[List[str]] = None,
        limit: int = 25,
        **kwargs
    ) -> List[Dict[str, str]]:
        """Search Reddit for brand mentions.

        Args:
            brand: Brand name.
            keywords: Additional keywords.
            limit: Maximum results.

        Returns:
            List of post dictionaries.
        """
        query_parts = [brand]
        if keywords:
            query_parts.extend(keywords)
        query = " ".join(query_parts)

        return self.search_posts(query, limit)


def get_reddit_scraper(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None
) -> Union[RedditScraper, RedditScraperNoAuth]:
    """Get appropriate Reddit scraper based on available credentials.

    Args:
        client_id: Reddit API client ID.
        client_secret: Reddit API client secret.

    Returns:
        RedditScraper if credentials available, else RedditScraperNoAuth.
    """
    scraper = RedditScraper(client_id, client_secret)
    if scraper.is_configured():
        return scraper
    return RedditScraperNoAuth()
