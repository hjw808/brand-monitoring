"""Shared fixtures for Brand Monitoring test suite."""

import os
import sys
import tempfile
import pytest
from datetime import datetime, timedelta

# Ensure the project root is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import Database, Mention


@pytest.fixture
def tmp_db_path(tmp_path):
    """Provide a temporary database path for each test."""
    return str(tmp_path / "test_brand_monitoring.db")


@pytest.fixture
def db(tmp_db_path):
    """Provide a fresh Database instance backed by a temp file."""
    return Database(db_path=tmp_db_path)


@pytest.fixture
def sample_mention():
    """Return a factory function that creates sample Mention objects."""
    def _make(
        brand="TestBrand",
        source="news",
        title="Test Article Title",
        content="This is test content about the brand.",
        url=None,
        author="Test Author",
        published_at=None,
        scraped_at=None,
        sentiment=None,
        sentiment_score=None,
        sentiment_reasoning=None,
    ):
        return Mention(
            id=None,
            brand=brand,
            source=source,
            title=title,
            content=content,
            url=url or f"https://example.com/{id(object())}",
            author=author,
            published_at=published_at or datetime.now(),
            scraped_at=scraped_at or datetime.now(),
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            sentiment_reasoning=sentiment_reasoning,
        )
    return _make


@pytest.fixture
def populated_db(db, sample_mention):
    """Provide a database populated with diverse test data."""
    now = datetime.now()

    mentions = [
        sample_mention(
            brand="Apple",
            source="news",
            title="Apple releases new iPhone",
            content="Great new features in the latest iPhone.",
            url="https://news.example.com/apple-iphone",
            sentiment="positive",
            sentiment_score=0.8,
            sentiment_reasoning="Positive product release coverage",
            published_at=now - timedelta(hours=2),
            scraped_at=now - timedelta(hours=1),
        ),
        sample_mention(
            brand="Apple",
            source="news",
            title="Apple stock drops 5%",
            content="Investors worried about supply chain issues.",
            url="https://news.example.com/apple-stock-drop",
            sentiment="negative",
            sentiment_score=-0.7,
            sentiment_reasoning="Negative financial news",
            published_at=now - timedelta(hours=5),
            scraped_at=now - timedelta(hours=4),
        ),
        sample_mention(
            brand="Apple",
            source="reddit",
            title="My experience with Apple support",
            content="Had a neutral experience with Apple customer service.",
            url="https://reddit.com/r/apple/post1",
            sentiment="neutral",
            sentiment_score=0.0,
            sentiment_reasoning="Mixed experience report",
            published_at=now - timedelta(hours=8),
            scraped_at=now - timedelta(hours=7),
        ),
        sample_mention(
            brand="Apple",
            source="reddit",
            title="Apple Vision Pro review",
            content="This product is amazing and revolutionary!",
            url="https://reddit.com/r/apple/post2",
            sentiment="positive",
            sentiment_score=0.9,
            sentiment_reasoning="Very positive product review",
            published_at=now - timedelta(hours=3),
            scraped_at=now - timedelta(hours=2),
        ),
        sample_mention(
            brand="Apple",
            source="news",
            title="Apple faces antitrust lawsuit",
            content="Major legal trouble for tech giant.",
            url="https://news.example.com/apple-antitrust",
            sentiment="negative",
            sentiment_score=-0.9,
            sentiment_reasoning="Serious legal issue",
            published_at=now - timedelta(hours=1),
            scraped_at=now,
        ),
        # Different brand
        sample_mention(
            brand="Samsung",
            source="news",
            title="Samsung Galaxy S25 announced",
            content="Samsung announces latest flagship phone.",
            url="https://news.example.com/samsung-s25",
            sentiment="positive",
            sentiment_score=0.6,
            sentiment_reasoning="Positive product announcement",
            published_at=now - timedelta(hours=4),
            scraped_at=now - timedelta(hours=3),
        ),
        # Unanalyzed mention
        sample_mention(
            brand="Apple",
            source="news",
            title="Apple plans new campus",
            content="Reports of new campus construction.",
            url="https://news.example.com/apple-campus",
            sentiment=None,
            sentiment_score=None,
            sentiment_reasoning=None,
            published_at=now - timedelta(hours=6),
            scraped_at=now - timedelta(hours=5),
        ),
    ]

    for mention in mentions:
        db.add_mention(mention)

    return db
