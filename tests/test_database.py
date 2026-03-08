"""Tests for src/database.py - SQLite persistence, queries, and filtering."""

import sqlite3
import pytest
from datetime import datetime, timedelta

from src.database import Database, Mention


class TestTableCreation:
    """Tests for database table creation."""

    def test_mentions_table_exists(self, db, tmp_db_path):
        """Verify the mentions table is created on initialization."""
        conn = sqlite3.connect(tmp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_summaries_table_exists(self, db, tmp_db_path):
        """Verify the summaries table is created on initialization."""
        conn = sqlite3.connect(tmp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='summaries'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_alerts_table_exists(self, db, tmp_db_path):
        """Verify the alerts table is created on initialization."""
        conn = sqlite3.connect(tmp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alerts'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_mentions_table_schema(self, db, tmp_db_path):
        """Verify the mentions table has expected columns."""
        conn = sqlite3.connect(tmp_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(mentions)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        expected = {
            "id", "brand", "source", "title", "content", "url",
            "author", "published_at", "scraped_at", "sentiment",
            "sentiment_score", "sentiment_reasoning"
        }
        assert expected.issubset(columns)

    def test_indexes_created(self, db, tmp_db_path):
        """Verify that indexes are created for performance."""
        conn = sqlite3.connect(tmp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "idx_mentions_brand" in indexes
        assert "idx_mentions_source" in indexes
        assert "idx_mentions_sentiment" in indexes
        assert "idx_mentions_published" in indexes

    def test_idempotent_table_creation(self, tmp_db_path):
        """Creating a Database twice should not raise errors."""
        db1 = Database(db_path=tmp_db_path)
        db2 = Database(db_path=tmp_db_path)
        # Both should succeed without errors
        assert db1.db_path == db2.db_path


class TestInsertMention:
    """Tests for inserting mentions."""

    def test_insert_returns_id(self, db, sample_mention):
        """Inserting a mention should return a valid row id."""
        mention = sample_mention(url="https://example.com/unique1")
        result = db.add_mention(mention)
        assert result is not None
        assert isinstance(result, int)
        assert result > 0

    def test_insert_multiple_mentions(self, db, sample_mention):
        """Multiple inserts with unique URLs should all succeed."""
        ids = []
        for i in range(5):
            mention = sample_mention(url=f"https://example.com/article-{i}")
            result = db.add_mention(mention)
            ids.append(result)

        assert all(id_ is not None for id_ in ids)
        assert len(set(ids)) == 5  # All IDs unique

    def test_insert_stores_all_fields(self, db, sample_mention):
        """All fields of the mention should be persisted correctly."""
        now = datetime.now()
        mention = sample_mention(
            brand="Tesla",
            source="reddit",
            title="Tesla Review",
            content="Great car!",
            url="https://example.com/tesla-review",
            author="reviewer1",
            published_at=now,
            scraped_at=now,
            sentiment="positive",
            sentiment_score=0.85,
            sentiment_reasoning="Positive review",
        )
        db.add_mention(mention)

        results = db.get_mentions("Tesla", days=1)
        assert len(results) == 1
        row = results[0]
        assert row["brand"] == "Tesla"
        assert row["source"] == "reddit"
        assert row["title"] == "Tesla Review"
        assert row["content"] == "Great car!"
        assert row["url"] == "https://example.com/tesla-review"
        assert row["author"] == "reviewer1"
        assert row["sentiment"] == "positive"
        assert abs(row["sentiment_score"] - 0.85) < 0.01

    def test_insert_with_none_optional_fields(self, db, sample_mention):
        """Inserting with None optional fields should succeed."""
        mention = sample_mention(
            url="https://example.com/no-optionals",
            author=None,
            sentiment=None,
            sentiment_score=None,
            sentiment_reasoning=None,
        )
        result = db.add_mention(mention)
        assert result is not None


class TestDuplicateURLHandling:
    """Tests for URL uniqueness constraint."""

    def test_duplicate_url_returns_none(self, db, sample_mention):
        """Inserting a mention with a duplicate URL should return None."""
        url = "https://example.com/same-url"
        m1 = sample_mention(url=url, title="First")
        m2 = sample_mention(url=url, title="Second")

        result1 = db.add_mention(m1)
        result2 = db.add_mention(m2)

        assert result1 is not None
        assert result2 is None

    def test_duplicate_does_not_overwrite(self, db, sample_mention):
        """A duplicate insert should not change the original row."""
        url = "https://example.com/no-overwrite"
        m1 = sample_mention(url=url, title="Original Title")
        m2 = sample_mention(url=url, title="New Title")

        db.add_mention(m1)
        db.add_mention(m2)  # should be ignored

        results = db.get_mentions("TestBrand", days=1)
        assert len(results) == 1
        assert results[0]["title"] == "Original Title"


class TestQueryMentions:
    """Tests for querying mentions with filters."""

    def test_filter_by_brand(self, populated_db):
        """get_mentions should filter by brand name."""
        apple = populated_db.get_mentions("Apple", days=30)
        samsung = populated_db.get_mentions("Samsung", days=30)

        assert len(apple) >= 5  # 5 Apple + 1 unanalyzed Apple
        assert len(samsung) == 1

    def test_filter_by_source(self, populated_db):
        """get_mentions should filter by source when provided."""
        news = populated_db.get_mentions("Apple", source="news", days=30)
        reddit = populated_db.get_mentions("Apple", source="reddit", days=30)

        for m in news:
            assert m["source"] == "news"
        for m in reddit:
            assert m["source"] == "reddit"

    def test_filter_by_sentiment(self, populated_db):
        """get_mentions should filter by sentiment when provided."""
        positive = populated_db.get_mentions("Apple", sentiment="positive", days=30)
        negative = populated_db.get_mentions("Apple", sentiment="negative", days=30)
        neutral = populated_db.get_mentions("Apple", sentiment="neutral", days=30)

        for m in positive:
            assert m["sentiment"] == "positive"
        for m in negative:
            assert m["sentiment"] == "negative"
        for m in neutral:
            assert m["sentiment"] == "neutral"

    def test_filter_by_days(self, db, sample_mention):
        """get_mentions should respect the days parameter."""
        now = datetime.now()
        # Recent mention
        db.add_mention(sample_mention(
            url="https://example.com/recent",
            scraped_at=now,
        ))
        # Old mention (scraped 10 days ago)
        db.add_mention(sample_mention(
            url="https://example.com/old",
            scraped_at=now - timedelta(days=10),
        ))

        within_7 = db.get_mentions("TestBrand", days=7)
        within_30 = db.get_mentions("TestBrand", days=30)

        assert len(within_7) == 1
        assert len(within_30) == 2

    def test_limit_parameter(self, db, sample_mention):
        """get_mentions should respect the limit parameter."""
        for i in range(10):
            db.add_mention(sample_mention(url=f"https://example.com/limit-{i}"))

        limited = db.get_mentions("TestBrand", days=1, limit=3)
        assert len(limited) == 3

    def test_combined_filters(self, populated_db):
        """Multiple filters should be applied together."""
        results = populated_db.get_mentions(
            "Apple", source="news", sentiment="negative", days=30
        )
        for m in results:
            assert m["brand"] == "Apple"
            assert m["source"] == "news"
            assert m["sentiment"] == "negative"

    def test_order_by_published_at_desc(self, populated_db):
        """Results should be ordered by published_at descending."""
        results = populated_db.get_mentions("Apple", days=30)
        dates = []
        for m in results:
            if m["published_at"]:
                dates.append(m["published_at"])

        # Should be descending
        for i in range(len(dates) - 1):
            assert dates[i] >= dates[i + 1]


class TestEmptyDatabaseQueries:
    """Tests for querying an empty database."""

    def test_get_mentions_empty(self, db):
        """get_mentions should return empty list on empty db."""
        result = db.get_mentions("NonExistentBrand", days=7)
        assert result == []

    def test_get_unanalyzed_empty(self, db):
        """get_unanalyzed_mentions should return empty list on empty db."""
        result = db.get_unanalyzed_mentions()
        assert result == []

    def test_get_sentiment_stats_empty(self, db):
        """get_sentiment_stats should return zeroed stats on empty db."""
        stats = db.get_sentiment_stats("NoBrand", days=7)
        assert stats["total"] == 0
        assert stats["positive"]["count"] == 0
        assert stats["negative"]["count"] == 0
        assert stats["neutral"]["count"] == 0

    def test_get_sentiment_trend_empty(self, db):
        """get_sentiment_trend should return empty list on empty db."""
        result = db.get_sentiment_trend("NoBrand", days=30)
        assert result == []

    def test_get_source_distribution_empty(self, db):
        """get_source_distribution should return empty dict on empty db."""
        result = db.get_source_distribution("NoBrand", days=7)
        assert result == {}

    def test_get_alerts_empty(self, db):
        """get_alerts should return empty list on empty db."""
        result = db.get_alerts("NoBrand")
        assert result == []

    def test_get_latest_summary_empty(self, db):
        """get_latest_summary should return None on empty db."""
        result = db.get_latest_summary("NoBrand")
        assert result is None


class TestUnanalyzedMentions:
    """Tests for get_unanalyzed_mentions."""

    def test_returns_only_unanalyzed(self, populated_db):
        """Should only return mentions where sentiment is NULL."""
        unanalyzed = populated_db.get_unanalyzed_mentions()
        for m in unanalyzed:
            assert m["sentiment"] is None

    def test_respects_limit(self, db, sample_mention):
        """Should respect the limit parameter."""
        for i in range(10):
            db.add_mention(sample_mention(
                url=f"https://example.com/unanalyzed-{i}",
                sentiment=None,
            ))

        limited = db.get_unanalyzed_mentions(limit=3)
        assert len(limited) == 3


class TestUpdateSentiment:
    """Tests for updating mention sentiment."""

    def test_update_sentiment_fields(self, db, sample_mention):
        """update_sentiment should set sentiment fields on a mention."""
        mention = sample_mention(
            url="https://example.com/to-analyze",
            sentiment=None,
            sentiment_score=None,
        )
        mention_id = db.add_mention(mention)

        db.update_sentiment(mention_id, "positive", 0.75, "Test reasoning")

        # Verify the update
        results = db.get_mentions("TestBrand", days=1)
        assert len(results) == 1
        assert results[0]["sentiment"] == "positive"
        assert abs(results[0]["sentiment_score"] - 0.75) < 0.01
        assert results[0]["sentiment_reasoning"] == "Test reasoning"


class TestSentimentStats:
    """Tests for get_sentiment_stats."""

    def test_counts_by_sentiment(self, populated_db):
        """Should correctly count mentions by sentiment category."""
        stats = populated_db.get_sentiment_stats("Apple", days=30)
        assert stats["positive"]["count"] == 2  # Two positive Apple mentions
        assert stats["negative"]["count"] == 2  # Two negative Apple mentions
        assert stats["neutral"]["count"] == 1   # One neutral Apple mention
        assert stats["total"] == 5  # Excludes the unanalyzed one

    def test_avg_score_computed(self, populated_db):
        """Should compute average sentiment score per category."""
        stats = populated_db.get_sentiment_stats("Apple", days=30)
        # Positive: (0.8 + 0.9) / 2 = 0.85
        assert abs(stats["positive"]["avg_score"] - 0.85) < 0.01
        # Negative: (-0.7 + -0.9) / 2 = -0.8
        assert abs(stats["negative"]["avg_score"] - (-0.8)) < 0.01


class TestSentimentTrend:
    """Tests for get_sentiment_trend."""

    def test_returns_daily_breakdown(self, populated_db):
        """Should return daily counts grouped by sentiment."""
        trend = populated_db.get_sentiment_trend("Apple", days=30)
        assert isinstance(trend, list)
        for row in trend:
            assert "date" in row
            assert "sentiment" in row
            assert "count" in row


class TestSourceDistribution:
    """Tests for get_source_distribution."""

    def test_counts_by_source(self, populated_db):
        """Should return correct counts per source."""
        dist = populated_db.get_source_distribution("Apple", days=30)
        assert "news" in dist
        assert "reddit" in dist
        # Apple has 4 news mentions (including unanalyzed) and 2 reddit mentions
        assert dist["news"] == 4
        assert dist["reddit"] == 2


class TestAlerts:
    """Tests for alert CRUD operations."""

    def test_add_alert_returns_id(self, db):
        """add_alert should return the alert id."""
        alert_id = db.add_alert("Apple", "negative_spike", "high", "Test alert")
        assert alert_id is not None
        assert isinstance(alert_id, int)

    def test_get_alerts_returns_saved_alert(self, db):
        """Saved alerts should be retrievable."""
        db.add_alert("Apple", "negative_spike", "high", "Test alert message")
        alerts = db.get_alerts("Apple")
        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "negative_spike"
        assert alerts[0]["severity"] == "high"
        assert alerts[0]["message"] == "Test alert message"

    def test_acknowledge_alert(self, db):
        """Acknowledging an alert should hide it from unacknowledged queries."""
        alert_id = db.add_alert("Apple", "volume_spike", "medium", "Volume alert")

        # Before acknowledging
        unacked = db.get_alerts("Apple", unacknowledged_only=True)
        assert len(unacked) == 1

        # Acknowledge
        db.acknowledge_alert(alert_id)

        # After acknowledging
        unacked = db.get_alerts("Apple", unacknowledged_only=True)
        assert len(unacked) == 0

        # Still visible when including acknowledged
        all_alerts = db.get_alerts("Apple", unacknowledged_only=False)
        assert len(all_alerts) == 1

    def test_alerts_filtered_by_brand(self, db):
        """Alerts should be filtered by brand."""
        db.add_alert("Apple", "spike", "high", "Apple alert")
        db.add_alert("Samsung", "spike", "high", "Samsung alert")

        apple_alerts = db.get_alerts("Apple")
        samsung_alerts = db.get_alerts("Samsung")

        assert len(apple_alerts) == 1
        assert len(samsung_alerts) == 1


class TestSummaries:
    """Tests for summary CRUD operations."""

    def test_save_summary_returns_id(self, db):
        """save_summary should return the summary id."""
        now = datetime.now()
        summary_id = db.save_summary(
            brand="Apple",
            period_start=now - timedelta(days=7),
            period_end=now,
            total_mentions=100,
            positive_count=50,
            negative_count=30,
            neutral_count=20,
            summary_text="Overall positive sentiment.",
            key_themes="innovation, pricing, quality"
        )
        assert summary_id is not None
        assert isinstance(summary_id, int)

    def test_get_latest_summary(self, db):
        """get_latest_summary should return the most recent summary."""
        import time
        now = datetime.now()

        # Save two summaries with a >1s delay so SQLite CURRENT_TIMESTAMP differs
        db.save_summary(
            "Apple", now - timedelta(days=14), now - timedelta(days=7),
            80, 40, 25, 15, "Older summary", "theme1"
        )
        time.sleep(1.1)  # SQLite CURRENT_TIMESTAMP has 1-second resolution
        db.save_summary(
            "Apple", now - timedelta(days=7), now,
            100, 50, 30, 20, "Newer summary", "theme2"
        )

        latest = db.get_latest_summary("Apple")
        assert latest is not None
        assert latest["summary_text"] == "Newer summary"
        assert latest["total_mentions"] == 100
