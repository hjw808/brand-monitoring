"""Web scraper module for Google News and other sources."""

import logging
import re
import time
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
import feedparser
from ddgs import DDGS

logger = logging.getLogger(__name__)


class WebScraper:
    """Scrapes mentions from Google News and other web sources."""

    def __init__(self, request_delay: float = 1.0):
        """Initialize the web scraper.

        Args:
            request_delay: Delay between requests in seconds.
        """
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def scrape_google_news(
        self,
        query: str,
        max_results: int = 20
    ) -> List[Dict[str, str]]:
        """Scrape Google News for a query using RSS feed.

        Args:
            query: Search query (brand name + keywords).
            max_results: Maximum number of results to return.

        Returns:
            List of article dictionaries with title, content, url, published_at.
        """
        results = []

        # Use Google News RSS feed
        encoded_query = quote_plus(query)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

        try:
            feed = feedparser.parse(rss_url)

            for entry in feed.entries[:max_results]:
                # Parse published date
                published_at = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_at = datetime(*entry.published_parsed[:6])

                # Extract source from title (Google News format: "Title - Source")
                title = entry.title
                source_name = "Unknown"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0]
                    source_name = parts[1] if len(parts) > 1 else "Unknown"

                # Get summary/description
                content = ""
                if hasattr(entry, 'summary'):
                    # Clean HTML from summary
                    soup = BeautifulSoup(entry.summary, 'html.parser')
                    content = soup.get_text(strip=True)

                results.append({
                    "title": title,
                    "content": content,
                    "url": entry.link,
                    "source_name": source_name,
                    "published_at": published_at or datetime.now(),
                    "source_type": "news"
                })

                time.sleep(self.request_delay * 0.1)  # Small delay between processing

        except Exception as e:
            logger.error("Error scraping Google News: %s", e)

        return results

    def scrape_article_content(self, url: str) -> Optional[str]:
        """Attempt to scrape full article content from URL.

        Args:
            url: Article URL.

        Returns:
            Article text content or None if failed.
        """
        try:
            time.sleep(self.request_delay)
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Remove script and style elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                element.decompose()

            # Try common article content selectors
            article_selectors = [
                'article',
                '[class*="article-body"]',
                '[class*="article-content"]',
                '[class*="post-content"]',
                '[class*="entry-content"]',
                'main',
            ]

            for selector in article_selectors:
                article = soup.select_one(selector)
                if article:
                    paragraphs = article.find_all('p')
                    if paragraphs:
                        text = ' '.join(p.get_text(strip=True) for p in paragraphs)
                        if len(text) > 100:
                            return text[:5000]  # Limit content length

            # Fallback: get all paragraphs
            paragraphs = soup.find_all('p')
            text = ' '.join(p.get_text(strip=True) for p in paragraphs)
            return text[:5000] if len(text) > 100 else None

        except Exception as e:
            logger.error("Error scraping article %s: %s", url, e)
            return None

    def scrape_duckduckgo_news(
        self,
        query: str,
        max_results: int = 15
    ) -> List[Dict[str, str]]:
        """Scrape news from DuckDuckGo News using the ddgs library.

        Args:
            query: Search query.
            max_results: Maximum number of results.

        Returns:
            List of article dictionaries.
        """
        results = []

        try:
            ddgs = DDGS()
            news_results = ddgs.news(query, max_results=max_results)

            for item in news_results:
                # Parse date from DDG news results
                published_at = datetime.now()
                if item.get("date"):
                    try:
                        published_at = datetime.fromisoformat(
                            item["date"].replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except (ValueError, AttributeError):
                        pass

                results.append({
                    "title": item.get("title", ""),
                    "content": item.get("body", ""),
                    "url": item.get("url", ""),
                    "source_name": item.get("source", "Web"),
                    "published_at": published_at,
                    "source_type": "news"
                })

        except Exception as e:
            logger.error("Error scraping DuckDuckGo News: %s", e)

        return results

    def scrape_all_news(
        self,
        brand: str,
        keywords: List[str] = None,
        max_results_per_source: int = 15
    ) -> List[Dict[str, str]]:
        """Scrape news from all available sources.

        Args:
            brand: Brand name to search for.
            keywords: Additional keywords to include.
            max_results_per_source: Maximum results from each source.

        Returns:
            Combined list of article dictionaries.
        """
        # Build search query
        query_parts = [brand]
        if keywords:
            query_parts.extend(keywords)
        query = " ".join(query_parts)

        all_results = []

        # Scrape Google News
        google_results = self.scrape_google_news(query, max_results_per_source)
        all_results.extend(google_results)

        # Scrape DuckDuckGo News as backup
        ddg_results = self.scrape_duckduckgo_news(query, max_results_per_source)
        all_results.extend(ddg_results)

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for result in all_results:
            if result["url"] not in seen_urls:
                seen_urls.add(result["url"])
                unique_results.append(result)

        return unique_results
