"""Tests for src/reddit_scraper.py - PRAW + unauthenticated fallback."""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.reddit_scraper import RedditScraper, RedditScraperNoAuth, get_reddit_scraper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_submission(
    title="Test Post",
    selftext="Test body text",
    url="https://example.com/link",
    permalink="/r/test/comments/abc123/test_post/",
    author="testuser",
    subreddit_name="test",
    score=42,
    num_comments=10,
    created_utc=1700000000.0,
):
    """Create a mock PRAW Submission object."""
    sub = MagicMock()
    sub.title = title
    sub.selftext = selftext
    sub.url = url
    sub.permalink = permalink
    sub.author = MagicMock()
    sub.author.__str__ = lambda self: author
    sub.subreddit = MagicMock()
    sub.subreddit.display_name = subreddit_name
    sub.score = score
    sub.num_comments = num_comments
    sub.created_utc = created_utc
    return sub


def _make_comment(
    body="Test comment body",
    author="commenter",
    score=5,
    created_utc=1700001000.0,
    permalink="/r/test/comments/abc123/test_post/def456/",
):
    """Create a mock PRAW Comment object."""
    from praw.models import Comment as CommentClass
    comment = MagicMock(spec=CommentClass)
    comment.body = body
    comment.author = MagicMock()
    comment.author.__str__ = lambda self: author
    comment.score = score
    comment.created_utc = created_utc
    comment.permalink = permalink
    return comment


# ---------------------------------------------------------------------------
# Authenticated scraper tests
# ---------------------------------------------------------------------------

class TestRedditScraperInit:
    """Tests for RedditScraper initialization."""

    def test_credentials_from_args(self):
        """Should accept credentials via constructor arguments."""
        scraper = RedditScraper(client_id="test_id", client_secret="test_secret")
        assert scraper.client_id == "test_id"
        assert scraper.client_secret == "test_secret"

    @patch.dict(os.environ, {"REDDIT_CLIENT_ID": "env_id", "REDDIT_CLIENT_SECRET": "env_secret"})
    def test_credentials_from_env(self):
        """Should fall back to environment variables."""
        scraper = RedditScraper()
        assert scraper.client_id == "env_id"
        assert scraper.client_secret == "env_secret"

    def test_is_configured_true(self):
        """is_configured should return True when credentials present."""
        scraper = RedditScraper(client_id="id", client_secret="secret")
        assert scraper.is_configured() is True

    def test_is_configured_false(self):
        """is_configured should return False when credentials missing."""
        scraper = RedditScraper(client_id=None, client_secret=None)
        # Clear env vars if they happen to be set
        with patch.dict(os.environ, {}, clear=True):
            scraper2 = RedditScraper()
            assert scraper2.is_configured() is False


class TestRedditScraperSearchPosts:
    """Tests for authenticated search_posts."""

    @patch("src.reddit_scraper.praw.Reddit")
    def test_search_posts_returns_results(self, mock_reddit_cls):
        """Should return parsed post dictionaries from PRAW search."""
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        submissions = [
            _make_submission(title="Post 1", permalink="/r/test/comments/1/post_1/"),
            _make_submission(title="Post 2", permalink="/r/test/comments/2/post_2/"),
        ]
        mock_subreddit = MagicMock()
        mock_subreddit.search.return_value = iter(submissions)
        mock_reddit.subreddit.return_value = mock_subreddit

        scraper = RedditScraper(client_id="id", client_secret="secret")
        scraper._reddit = mock_reddit

        results = scraper.search_posts("test query")
        assert len(results) == 2
        assert results[0]["title"] == "Post 1"
        assert results[1]["title"] == "Post 2"

    @patch("src.reddit_scraper.praw.Reddit")
    def test_search_specific_subreddits(self, mock_reddit_cls):
        """Should search in specified subreddits."""
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_subreddit = MagicMock()
        mock_subreddit.search.return_value = iter([])
        mock_reddit.subreddit.return_value = mock_subreddit

        scraper = RedditScraper(client_id="id", client_secret="secret")
        scraper._reddit = mock_reddit

        scraper.search_posts("test", subreddits=["apple", "tech"])
        mock_reddit.subreddit.assert_called_with("apple+tech")

    @patch("src.reddit_scraper.praw.Reddit")
    def test_search_all_subreddits_default(self, mock_reddit_cls):
        """Should search r/all when no subreddits specified."""
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_subreddit = MagicMock()
        mock_subreddit.search.return_value = iter([])
        mock_reddit.subreddit.return_value = mock_subreddit

        scraper = RedditScraper(client_id="id", client_secret="secret")
        scraper._reddit = mock_reddit

        scraper.search_posts("test")
        mock_reddit.subreddit.assert_called_with("all")

    def test_returns_empty_when_not_configured(self):
        """Should return empty list when Reddit is not configured."""
        scraper = RedditScraper(client_id=None, client_secret=None)
        results = scraper.search_posts("test")
        assert results == []

    @patch("src.reddit_scraper.praw.Reddit")
    def test_handles_api_error(self, mock_reddit_cls):
        """Should return empty list on PRAW exception."""
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_subreddit = MagicMock()
        mock_subreddit.search.side_effect = Exception("API rate limit")
        mock_reddit.subreddit.return_value = mock_subreddit

        scraper = RedditScraper(client_id="id", client_secret="secret")
        scraper._reddit = mock_reddit

        results = scraper.search_posts("test")
        assert results == []


class TestParseSubmission:
    """Tests for _parse_submission helper."""

    def test_parses_all_fields(self):
        """Should correctly map submission fields to dict."""
        sub = _make_submission(
            title="Test Title",
            selftext="Post body",
            permalink="/r/tech/comments/xyz/test/",
            author="john",
            subreddit_name="tech",
            score=100,
            num_comments=25,
            created_utc=1700000000.0,
        )

        scraper = RedditScraper(client_id="id", client_secret="secret")
        result = scraper._parse_submission(sub)

        assert result["title"] == "Test Title"
        assert result["content"] == "Post body"
        assert result["url"] == "https://reddit.com/r/tech/comments/xyz/test/"
        assert result["subreddit"] == "tech"
        assert result["score"] == 100
        assert result["num_comments"] == 25
        assert result["source_type"] == "reddit"
        assert isinstance(result["published_at"], datetime)

    def test_handles_link_post(self):
        """Should indicate link posts in content."""
        sub = _make_submission(selftext="", url="https://external.com/article")
        scraper = RedditScraper(client_id="id", client_secret="secret")
        result = scraper._parse_submission(sub)

        assert "[Link post to:" in result["content"]

    def test_handles_deleted_author(self):
        """Should handle submissions with deleted author."""
        sub = _make_submission()
        sub.author = None
        scraper = RedditScraper(client_id="id", client_secret="secret")
        result = scraper._parse_submission(sub)

        assert result["author"] == "[deleted]"

    def test_truncates_long_content(self):
        """Should truncate content to 5000 chars."""
        sub = _make_submission(selftext="A" * 10000)
        scraper = RedditScraper(client_id="id", client_secret="secret")
        result = scraper._parse_submission(sub)

        assert len(result["content"]) <= 5000


class TestGetComments:
    """Tests for get_comments_for_post."""

    @patch("src.reddit_scraper.praw.Reddit")
    def test_returns_comments(self, mock_reddit_cls):
        """Should return parsed comment dictionaries."""
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        comments = [
            _make_comment(body="Comment 1"),
            _make_comment(body="Comment 2"),
        ]
        mock_submission = MagicMock()
        mock_submission.comments.replace_more = MagicMock()
        mock_submission.comments.list.return_value = comments
        mock_reddit.submission.return_value = mock_submission

        scraper = RedditScraper(client_id="id", client_secret="secret")
        scraper._reddit = mock_reddit

        results = scraper.get_comments_for_post("https://reddit.com/r/test/comments/abc/test/")
        assert len(results) == 2
        assert results[0]["content"] == "Comment 1"

    def test_returns_empty_when_not_configured(self):
        """Should return empty list when not configured."""
        scraper = RedditScraper(client_id=None, client_secret=None)
        results = scraper.get_comments_for_post("https://reddit.com/some/post")
        assert results == []

    @patch("src.reddit_scraper.praw.Reddit")
    def test_handles_comment_error(self, mock_reddit_cls):
        """Should return empty list on error fetching comments."""
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit
        mock_reddit.submission.side_effect = Exception("Not found")

        scraper = RedditScraper(client_id="id", client_secret="secret")
        scraper._reddit = mock_reddit

        results = scraper.get_comments_for_post("https://reddit.com/bad/url")
        assert results == []


class TestSearchBrand:
    """Tests for search_brand convenience method."""

    @patch("src.reddit_scraper.praw.Reddit")
    def test_builds_query_from_brand_and_keywords(self, mock_reddit_cls):
        """Should combine brand and keywords into query string."""
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_subreddit = MagicMock()
        mock_subreddit.search.return_value = iter([])
        mock_reddit.subreddit.return_value = mock_subreddit

        scraper = RedditScraper(client_id="id", client_secret="secret")
        scraper._reddit = mock_reddit

        scraper.search_brand("Apple", keywords=["iPhone", "review"])

        call_args = mock_subreddit.search.call_args
        query = call_args[0][0]
        assert "Apple" in query
        assert "iPhone" in query
        assert "review" in query


# ---------------------------------------------------------------------------
# Unauthenticated scraper tests
# ---------------------------------------------------------------------------

class TestRedditScraperNoAuth:
    """Tests for RedditScraperNoAuth fallback."""

    def test_search_posts_with_json(self):
        """Should parse Reddit JSON endpoint response."""
        mock_data = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "No Auth Post",
                            "selftext": "Body text",
                            "permalink": "/r/test/comments/noauth/post/",
                            "author": "anon",
                            "subreddit": "test",
                            "score": 15,
                            "num_comments": 3,
                            "created_utc": 1700000000.0,
                        }
                    }
                ]
            }
        }

        scraper = RedditScraperNoAuth()
        mock_response = MagicMock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(scraper.session, "get", return_value=mock_response):
            results = scraper.search_posts("test query")

        assert len(results) == 1
        assert results[0]["title"] == "No Auth Post"
        assert results[0]["url"] == "https://reddit.com/r/test/comments/noauth/post/"

    def test_handles_network_error(self):
        """Should return empty list on network error."""
        scraper = RedditScraperNoAuth()

        with patch.object(scraper.session, "get", side_effect=Exception("Timeout")):
            results = scraper.search_posts("test")

        assert results == []

    def test_handles_empty_response(self):
        """Should return empty list when Reddit returns no results."""
        mock_data = {"data": {"children": []}}

        scraper = RedditScraperNoAuth()
        mock_response = MagicMock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(scraper.session, "get", return_value=mock_response):
            results = scraper.search_posts("obscure query")

        assert results == []

    def test_search_brand_builds_query(self):
        """search_brand should combine brand and keywords."""
        scraper = RedditScraperNoAuth()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"children": []}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(scraper.session, "get", return_value=mock_response) as mock_get:
            scraper.search_brand("Tesla", keywords=["Model3"])

        call_url = mock_get.call_args[0][0]
        assert "Tesla" in call_url
        assert "Model3" in call_url


# ---------------------------------------------------------------------------
# Factory function tests
# ---------------------------------------------------------------------------

class TestGetRedditScraper:
    """Tests for the get_reddit_scraper factory function."""

    def test_returns_authenticated_scraper_with_credentials(self):
        """Should return RedditScraper when credentials are provided."""
        scraper = get_reddit_scraper("client_id", "client_secret")
        assert isinstance(scraper, RedditScraper)

    @patch.dict(os.environ, {}, clear=True)
    def test_returns_noauth_scraper_without_credentials(self):
        """Should return RedditScraperNoAuth when no credentials."""
        # Ensure no env vars
        os.environ.pop("REDDIT_CLIENT_ID", None)
        os.environ.pop("REDDIT_CLIENT_SECRET", None)
        scraper = get_reddit_scraper()
        assert isinstance(scraper, RedditScraperNoAuth)

    @patch.dict(os.environ, {"REDDIT_CLIENT_ID": "env_id", "REDDIT_CLIENT_SECRET": "env_sec"})
    def test_returns_authenticated_from_env(self):
        """Should return RedditScraper when env vars are set."""
        scraper = get_reddit_scraper()
        assert isinstance(scraper, RedditScraper)
