"""Tests for src/web_scraper.py - Google News RSS + DuckDuckGo scraping."""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock
from urllib.parse import quote_plus

import pytest

from src.web_scraper import WebScraper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feed_entry(title, link, summary="", published_parsed=None, source_name=None):
    """Create a mock feedparser entry."""
    entry = MagicMock()
    if source_name:
        entry.title = f"{title} - {source_name}"
    else:
        entry.title = title
    entry.link = link
    entry.summary = summary

    if published_parsed:
        entry.published_parsed = published_parsed
    else:
        entry.published_parsed = None
        # Make hasattr return False for published_parsed when it's None
        type(entry).published_parsed = PropertyMock(return_value=None)

    return entry


def _make_feed(entries):
    """Create a mock feedparser feed object."""
    feed = MagicMock()
    feed.entries = entries
    return feed


def _make_ddgs_news_result(title, url, body="", source="Web", date=None):
    """Create a mock ddgs news result dict."""
    return {
        "title": title,
        "url": url,
        "body": body,
        "source": source,
        "date": date,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGoogleNewsScraping:
    """Tests for scrape_google_news using mocked feedparser."""

    @patch("src.web_scraper.feedparser.parse")
    @patch("src.web_scraper.time.sleep")
    def test_parses_rss_entries(self, mock_sleep, mock_parse):
        """Should return one dict per RSS entry."""
        entries = [
            _make_feed_entry("Article One - CNN", "https://cnn.com/a1", source_name=None),
            _make_feed_entry("Article Two - BBC", "https://bbc.com/a2", source_name=None),
        ]
        # Titles already have source baked in above for the rsplit test
        entries[0].title = "Article One - CNN"
        entries[1].title = "Article Two - BBC"
        mock_parse.return_value = _make_feed(entries)

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_google_news("test query")

        assert len(results) == 2
        assert results[0]["title"] == "Article One"
        assert results[0]["source_name"] == "CNN"
        assert results[1]["title"] == "Article Two"
        assert results[1]["source_name"] == "BBC"

    @patch("src.web_scraper.feedparser.parse")
    @patch("src.web_scraper.time.sleep")
    def test_respects_max_results(self, mock_sleep, mock_parse):
        """Should limit results to max_results."""
        entries = [
            _make_feed_entry(f"Article {i}", f"https://example.com/{i}")
            for i in range(20)
        ]
        mock_parse.return_value = _make_feed(entries)

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_google_news("test", max_results=5)

        assert len(results) == 5

    @patch("src.web_scraper.feedparser.parse")
    @patch("src.web_scraper.time.sleep")
    def test_parses_published_date(self, mock_sleep, mock_parse):
        """Should correctly parse published_parsed into datetime."""
        entry = _make_feed_entry("Test", "https://example.com/date-test")
        entry.published_parsed = (2025, 3, 15, 10, 30, 0, 5, 74, 0)
        type(entry).published_parsed = PropertyMock(return_value=(2025, 3, 15, 10, 30, 0, 5, 74, 0))
        mock_parse.return_value = _make_feed([entry])

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_google_news("test")

        assert results[0]["published_at"] == datetime(2025, 3, 15, 10, 30, 0)

    @patch("src.web_scraper.feedparser.parse")
    @patch("src.web_scraper.time.sleep")
    def test_handles_missing_published_date(self, mock_sleep, mock_parse):
        """Should use current datetime when published_parsed is absent."""
        entry = MagicMock()
        entry.title = "No Date"
        entry.link = "https://example.com/no-date"
        entry.summary = "summary"
        entry.published_parsed = None
        # hasattr still returns True for MagicMock, but the value is None
        mock_parse.return_value = _make_feed([entry])

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_google_news("test")

        assert len(results) == 1
        # published_at should be roughly now
        assert isinstance(results[0]["published_at"], datetime)

    @patch("src.web_scraper.feedparser.parse")
    @patch("src.web_scraper.time.sleep")
    def test_strips_html_from_summary(self, mock_sleep, mock_parse):
        """Should strip HTML tags from entry summary."""
        entry = _make_feed_entry(
            "HTML Article", "https://example.com/html",
            summary="<b>Bold</b> text with <a href='#'>link</a>"
        )
        mock_parse.return_value = _make_feed([entry])

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_google_news("test")

        assert "<b>" not in results[0]["content"]
        assert "<a" not in results[0]["content"]
        assert "Bold" in results[0]["content"]

    @patch("src.web_scraper.feedparser.parse")
    @patch("src.web_scraper.time.sleep")
    def test_empty_feed_returns_empty_list(self, mock_sleep, mock_parse):
        """Should return empty list when feed has no entries."""
        mock_parse.return_value = _make_feed([])

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_google_news("test")

        assert results == []

    @patch("src.web_scraper.feedparser.parse")
    @patch("src.web_scraper.time.sleep")
    def test_handles_feedparser_error(self, mock_sleep, mock_parse):
        """Should return empty list on feedparser exception."""
        mock_parse.side_effect = Exception("Network error")

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_google_news("test")

        assert results == []


class TestDuckDuckGoScraping:
    """Tests for scrape_duckduckgo_news with mocked ddgs library."""

    @patch("src.web_scraper.DDGS")
    def test_parses_ddg_results(self, mock_ddgs_cls):
        """Should extract title, body, and URL from ddgs news results."""
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value = mock_ddgs
        mock_ddgs.news.return_value = [
            _make_ddgs_news_result("DDG Article 1", "https://example.com/ddg1", body="Snippet one"),
            _make_ddgs_news_result("DDG Article 2", "https://example.com/ddg2", body="Snippet two"),
        ]

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_duckduckgo_news("test query")

        assert len(results) == 2
        assert results[0]["title"] == "DDG Article 1"
        assert results[0]["content"] == "Snippet one"
        assert results[1]["title"] == "DDG Article 2"

    @patch("src.web_scraper.DDGS")
    def test_extracts_url(self, mock_ddgs_cls):
        """Should preserve the URL from ddgs results."""
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value = mock_ddgs
        mock_ddgs.news.return_value = [
            _make_ddgs_news_result("URL Test", "https://realsite.com/article", body="Test"),
        ]

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_duckduckgo_news("test")

        assert len(results) == 1
        assert results[0]["url"] == "https://realsite.com/article"

    @patch("src.web_scraper.DDGS")
    def test_passes_max_results(self, mock_ddgs_cls):
        """Should pass max_results to ddgs.news()."""
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value = mock_ddgs
        mock_ddgs.news.return_value = []

        scraper = WebScraper(request_delay=0)
        scraper.scrape_duckduckgo_news("test", max_results=3)

        mock_ddgs.news.assert_called_once_with("test", max_results=3)

    @patch("src.web_scraper.DDGS")
    def test_handles_ddgs_error(self, mock_ddgs_cls):
        """Should return empty list when ddgs raises an exception."""
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value = mock_ddgs
        mock_ddgs.news.side_effect = Exception("Rate limited")

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_duckduckgo_news("test")

        assert results == []

    @patch("src.web_scraper.DDGS")
    def test_handles_empty_results(self, mock_ddgs_cls):
        """Should return empty list when ddgs returns no news."""
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value = mock_ddgs
        mock_ddgs.news.return_value = []

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_duckduckgo_news("test")

        assert results == []

    @patch("src.web_scraper.DDGS")
    def test_parses_date_from_results(self, mock_ddgs_cls):
        """Should parse ISO date strings from ddgs news results."""
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value = mock_ddgs
        mock_ddgs.news.return_value = [
            _make_ddgs_news_result("Date Test", "https://example.com/d",
                                   date="2025-06-15T10:30:00+00:00"),
        ]

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_duckduckgo_news("test")

        assert results[0]["published_at"] == datetime(2025, 6, 15, 10, 30, 0)


class TestArticleContentScraping:
    """Tests for scrape_article_content."""

    @patch("src.web_scraper.time.sleep")
    def test_extracts_article_content(self, mock_sleep):
        """Should extract paragraph text from article tags."""
        html = """
        <html><body>
        <article>
            <p>First paragraph of the article.</p>
            <p>Second paragraph with more content here to make it over 100 chars total when combined together properly.</p>
        </article>
        </body></html>
        """
        scraper = WebScraper(request_delay=0)
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch.object(scraper.session, "get", return_value=mock_response):
            content = scraper.scrape_article_content("https://example.com/article")

        assert content is not None
        assert "First paragraph" in content

    @patch("src.web_scraper.time.sleep")
    def test_returns_none_on_error(self, mock_sleep):
        """Should return None when request fails."""
        scraper = WebScraper(request_delay=0)

        with patch.object(scraper.session, "get", side_effect=Exception("404")):
            content = scraper.scrape_article_content("https://example.com/missing")

        assert content is None

    @patch("src.web_scraper.time.sleep")
    def test_truncates_long_content(self, mock_sleep):
        """Should truncate content to 5000 characters."""
        long_text = "A" * 200  # Each paragraph > 100 chars
        html = f"<html><body><article>{'<p>' + long_text + '</p>' * 50}</article></body></html>"
        scraper = WebScraper(request_delay=0)
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch.object(scraper.session, "get", return_value=mock_response):
            content = scraper.scrape_article_content("https://example.com/long")

        assert content is not None
        assert len(content) <= 5000


class TestScrapeAllNews:
    """Tests for scrape_all_news combining sources."""

    @patch("src.web_scraper.DDGS")
    @patch("src.web_scraper.time.sleep")
    @patch("src.web_scraper.feedparser.parse")
    def test_combines_sources(self, mock_parse, mock_sleep, mock_ddgs_cls):
        """Should combine results from Google News and DuckDuckGo."""
        # Google News results
        entries = [_make_feed_entry("Google Article", "https://google.example.com/1")]
        mock_parse.return_value = _make_feed(entries)

        # DuckDuckGo results
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value = mock_ddgs
        mock_ddgs.news.return_value = [
            _make_ddgs_news_result("DDG Article", "https://ddg.example.com/1", body="DDG snippet")
        ]

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_all_news("TestBrand")

        assert len(results) == 2

    @patch("src.web_scraper.DDGS")
    @patch("src.web_scraper.time.sleep")
    @patch("src.web_scraper.feedparser.parse")
    def test_deduplicates_by_url(self, mock_parse, mock_sleep, mock_ddgs_cls):
        """Should remove duplicate URLs across sources."""
        shared_url = "https://example.com/shared-article"

        entries = [_make_feed_entry("Same Article", shared_url)]
        mock_parse.return_value = _make_feed(entries)

        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value = mock_ddgs
        mock_ddgs.news.return_value = [
            _make_ddgs_news_result("Same Article DDG", shared_url, body="Same")
        ]

        scraper = WebScraper(request_delay=0)
        results = scraper.scrape_all_news("TestBrand")

        urls = [r["url"] for r in results]
        assert len(urls) == len(set(urls))

    @patch("src.web_scraper.DDGS")
    @patch("src.web_scraper.time.sleep")
    @patch("src.web_scraper.feedparser.parse")
    def test_builds_query_with_keywords(self, mock_parse, mock_sleep, mock_ddgs_cls):
        """Should include keywords in the search query."""
        mock_parse.return_value = _make_feed([])

        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value = mock_ddgs
        mock_ddgs.news.return_value = []

        scraper = WebScraper(request_delay=0)
        scraper.scrape_all_news("Apple", keywords=["iPhone", "review"])

        # Verify feedparser was called with a URL containing the full query
        call_args = mock_parse.call_args[0][0]
        assert "Apple" in call_args
        assert "iPhone" in call_args or quote_plus("iPhone") in call_args
