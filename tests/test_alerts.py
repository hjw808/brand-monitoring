"""Tests for src/alerts.py - Alert detection algorithms."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.alerts import AlertSystem, Alert
from src.database import Database, Mention


class TestNegativeSpikeDetection:
    """Tests for check_negative_spike algorithm."""

    def test_detects_negative_spike(self, db, sample_mention):
        """Should detect when negative sentiment ratio spikes."""
        now = datetime.now()

        # Historical data: mostly positive (7 days ago)
        for i in range(10):
            db.add_mention(sample_mention(
                url=f"https://example.com/hist-pos-{i}",
                brand="Apple",
                sentiment="positive",
                sentiment_score=0.7,
                scraped_at=now - timedelta(days=3),
                published_at=now - timedelta(days=3),
            ))
        for i in range(2):
            db.add_mention(sample_mention(
                url=f"https://example.com/hist-neg-{i}",
                brand="Apple",
                sentiment="negative",
                sentiment_score=-0.7,
                scraped_at=now - timedelta(days=3),
                published_at=now - timedelta(days=3),
            ))

        # Recent data: mostly negative (last 24 hours)
        for i in range(3):
            db.add_mention(sample_mention(
                url=f"https://example.com/recent-pos-{i}",
                brand="Apple",
                sentiment="positive",
                sentiment_score=0.7,
                scraped_at=now - timedelta(hours=2),
                published_at=now - timedelta(hours=2),
            ))
        for i in range(7):
            db.add_mention(sample_mention(
                url=f"https://example.com/recent-neg-{i}",
                brand="Apple",
                sentiment="negative",
                sentiment_score=-0.7,
                scraped_at=now - timedelta(hours=2),
                published_at=now - timedelta(hours=2),
            ))

        alert_system = AlertSystem(db, negative_spike_threshold=0.3, min_mentions_for_alert=5)
        alert = alert_system.check_negative_spike("Apple")

        assert alert is not None
        assert alert.alert_type == "negative_spike"

    def test_no_alert_when_no_spike(self, db, sample_mention):
        """Should not alert when negative ratio is stable."""
        now = datetime.now()

        # Both periods: similar negative ratios
        for period_offset in [timedelta(days=3), timedelta(hours=2)]:
            for i in range(6):
                db.add_mention(sample_mention(
                    url=f"https://example.com/stable-pos-{period_offset}-{i}",
                    brand="Apple",
                    sentiment="positive",
                    sentiment_score=0.7,
                    scraped_at=now - period_offset,
                    published_at=now - period_offset,
                ))
            for i in range(4):
                db.add_mention(sample_mention(
                    url=f"https://example.com/stable-neg-{period_offset}-{i}",
                    brand="Apple",
                    sentiment="negative",
                    sentiment_score=-0.7,
                    scraped_at=now - period_offset,
                    published_at=now - period_offset,
                ))

        alert_system = AlertSystem(db, negative_spike_threshold=0.3, min_mentions_for_alert=5)
        alert = alert_system.check_negative_spike("Apple")

        assert alert is None

    def test_no_alert_with_insufficient_recent_data(self, db, sample_mention):
        """Should not alert when recent mentions are below threshold."""
        now = datetime.now()

        # Historical data exists
        for i in range(10):
            db.add_mention(sample_mention(
                url=f"https://example.com/hist-{i}",
                brand="Apple",
                sentiment="positive",
                sentiment_score=0.7,
                scraped_at=now - timedelta(days=3),
                published_at=now - timedelta(days=3),
            ))

        # Only 2 recent mentions (below min_mentions_for_alert=5)
        for i in range(2):
            db.add_mention(sample_mention(
                url=f"https://example.com/recent-few-{i}",
                brand="Apple",
                sentiment="negative",
                sentiment_score=-0.9,
                scraped_at=now - timedelta(hours=2),
                published_at=now - timedelta(hours=2),
            ))

        alert_system = AlertSystem(db, min_mentions_for_alert=5)
        alert = alert_system.check_negative_spike("Apple")

        assert alert is None

    def test_no_alert_with_insufficient_historical_data(self, db, sample_mention):
        """Should not alert when historical data is below threshold."""
        now = datetime.now()

        # Only 2 historical mentions
        for i in range(2):
            db.add_mention(sample_mention(
                url=f"https://example.com/hist-few-{i}",
                brand="Apple",
                sentiment="positive",
                sentiment_score=0.7,
                scraped_at=now - timedelta(days=3),
                published_at=now - timedelta(days=3),
            ))

        # Plenty of recent negative mentions
        for i in range(10):
            db.add_mention(sample_mention(
                url=f"https://example.com/recent-many-{i}",
                brand="Apple",
                sentiment="negative",
                sentiment_score=-0.9,
                scraped_at=now - timedelta(hours=2),
                published_at=now - timedelta(hours=2),
            ))

        alert_system = AlertSystem(db, min_mentions_for_alert=5)
        alert = alert_system.check_negative_spike("Apple")

        assert alert is None


class TestVolumeSpikeDetection:
    """Tests for check_volume_spike algorithm."""

    def test_detects_volume_spike(self, db, sample_mention):
        """Should detect when mention volume exceeds 2x weekly average."""
        now = datetime.now()

        # Historical: 7 mentions over 7 days (avg 1/day)
        for i in range(7):
            db.add_mention(sample_mention(
                url=f"https://example.com/vol-hist-{i}",
                brand="Apple",
                sentiment="positive",
                sentiment_score=0.5,
                scraped_at=now - timedelta(days=3),
                published_at=now - timedelta(days=3),
            ))

        # Recent: 10 mentions in last 24 hours (> 2x avg daily)
        for i in range(10):
            db.add_mention(sample_mention(
                url=f"https://example.com/vol-recent-{i}",
                brand="Apple",
                sentiment="positive",
                sentiment_score=0.5,
                scraped_at=now - timedelta(hours=2),
                published_at=now - timedelta(hours=2),
            ))

        alert_system = AlertSystem(db, min_mentions_for_alert=5)
        alert = alert_system.check_volume_spike("Apple")

        assert alert is not None
        assert alert.alert_type == "volume_spike"
        assert alert.severity == "medium"

    def test_no_volume_alert_within_normal_range(self, db, sample_mention):
        """Should not alert when volume is within normal range."""
        now = datetime.now()

        # Historical: 14 mentions over 7 days (avg 2/day)
        for i in range(14):
            db.add_mention(sample_mention(
                url=f"https://example.com/vol-norm-hist-{i}",
                brand="Apple",
                sentiment="positive",
                sentiment_score=0.5,
                scraped_at=now - timedelta(days=3),
                published_at=now - timedelta(days=3),
            ))

        # Recent: 3 mentions in last 24 hours (< 2x avg of 2/day)
        for i in range(3):
            db.add_mention(sample_mention(
                url=f"https://example.com/vol-norm-recent-{i}",
                brand="Apple",
                sentiment="positive",
                sentiment_score=0.5,
                scraped_at=now - timedelta(hours=2),
                published_at=now - timedelta(hours=2),
            ))

        alert_system = AlertSystem(db, min_mentions_for_alert=5)
        alert = alert_system.check_volume_spike("Apple")

        assert alert is None

    def test_no_volume_alert_insufficient_history(self, db, sample_mention):
        """Should not alert when insufficient historical data."""
        now = datetime.now()

        # Only 2 historical mentions (below threshold)
        for i in range(2):
            db.add_mention(sample_mention(
                url=f"https://example.com/vol-few-{i}",
                brand="Apple",
                sentiment="positive",
                sentiment_score=0.5,
                scraped_at=now - timedelta(days=3),
                published_at=now - timedelta(days=3),
            ))

        alert_system = AlertSystem(db, min_mentions_for_alert=5)
        alert = alert_system.check_volume_spike("Apple")

        assert alert is None


class TestHighlyNegativeMention:
    """Tests for check_highly_negative_mention algorithm."""

    def test_detects_highly_negative_mention(self, db, sample_mention):
        """Should flag mentions with score below threshold."""
        now = datetime.now()

        db.add_mention(sample_mention(
            url="https://example.com/very-neg",
            brand="Apple",
            sentiment="negative",
            sentiment_score=-0.9,
            scraped_at=now - timedelta(hours=2),
            published_at=now - timedelta(hours=2),
        ))

        alert_system = AlertSystem(db)
        alerts = alert_system.check_highly_negative_mention("Apple", threshold=-0.8)

        assert len(alerts) == 1
        assert alerts[0].alert_type == "highly_negative"
        assert alerts[0].severity == "medium"

    def test_ignores_moderately_negative(self, db, sample_mention):
        """Should not flag mentions with score above threshold."""
        now = datetime.now()

        db.add_mention(sample_mention(
            url="https://example.com/mod-neg",
            brand="Apple",
            sentiment="negative",
            sentiment_score=-0.5,
            scraped_at=now - timedelta(hours=2),
            published_at=now - timedelta(hours=2),
        ))

        alert_system = AlertSystem(db)
        alerts = alert_system.check_highly_negative_mention("Apple", threshold=-0.8)

        assert len(alerts) == 0

    def test_all_positive_mentions(self, db, sample_mention):
        """Should return no alerts when all mentions are positive."""
        now = datetime.now()

        for i in range(5):
            db.add_mention(sample_mention(
                url=f"https://example.com/pos-{i}",
                brand="Apple",
                sentiment="positive",
                sentiment_score=0.8,
                scraped_at=now - timedelta(hours=2),
                published_at=now - timedelta(hours=2),
            ))

        alert_system = AlertSystem(db)
        alerts = alert_system.check_highly_negative_mention("Apple")

        assert len(alerts) == 0

    def test_no_mentions(self, db):
        """Should return empty list with no mentions in the database."""
        alert_system = AlertSystem(db)
        alerts = alert_system.check_highly_negative_mention("Apple")
        assert len(alerts) == 0

    def test_multiple_highly_negative(self, db, sample_mention):
        """Should return one alert per highly negative mention."""
        now = datetime.now()

        for i in range(3):
            db.add_mention(sample_mention(
                url=f"https://example.com/multi-neg-{i}",
                brand="Apple",
                sentiment="negative",
                sentiment_score=-0.95,
                scraped_at=now - timedelta(hours=2),
                published_at=now - timedelta(hours=2),
            ))

        alert_system = AlertSystem(db)
        alerts = alert_system.check_highly_negative_mention("Apple", threshold=-0.8)

        assert len(alerts) == 3

    def test_handles_none_sentiment_score(self, db, sample_mention):
        """Should skip mentions where sentiment_score is None."""
        now = datetime.now()

        db.add_mention(sample_mention(
            url="https://example.com/no-score",
            brand="Apple",
            sentiment=None,
            sentiment_score=None,
            scraped_at=now - timedelta(hours=2),
            published_at=now - timedelta(hours=2),
        ))

        alert_system = AlertSystem(db)
        alerts = alert_system.check_highly_negative_mention("Apple")

        assert len(alerts) == 0


class TestSeverityCalculation:
    """Tests for _calculate_severity."""

    def test_high_severity_at_100_percent(self, db):
        """100%+ increase should be high severity."""
        system = AlertSystem(db)
        assert system._calculate_severity(1.0) == "high"
        assert system._calculate_severity(2.5) == "high"

    def test_medium_severity_at_50_percent(self, db):
        """50-99% increase should be medium severity."""
        system = AlertSystem(db)
        assert system._calculate_severity(0.5) == "medium"
        assert system._calculate_severity(0.99) == "medium"

    def test_low_severity_below_50_percent(self, db):
        """Below 50% increase should be low severity."""
        system = AlertSystem(db)
        assert system._calculate_severity(0.3) == "low"
        assert system._calculate_severity(0.1) == "low"
        assert system._calculate_severity(0.49) == "low"


class TestRunAllChecks:
    """Tests for run_all_checks combining all alert types."""

    def test_empty_database_returns_no_alerts(self, db):
        """Should return empty list for a brand with no data."""
        system = AlertSystem(db)
        alerts = system.run_all_checks("NonExistent")
        assert alerts == []

    def test_returns_combined_alerts(self, db, sample_mention):
        """Should combine alerts from all check types."""
        now = datetime.now()

        # Add highly negative mention
        db.add_mention(sample_mention(
            url="https://example.com/combined-neg",
            brand="Apple",
            sentiment="negative",
            sentiment_score=-0.95,
            scraped_at=now - timedelta(hours=2),
            published_at=now - timedelta(hours=2),
        ))

        system = AlertSystem(db, min_mentions_for_alert=100)  # high threshold to avoid spike alerts
        alerts = system.run_all_checks("Apple")

        # Should at least have the highly negative mention alert
        highly_negative_alerts = [a for a in alerts if a.alert_type == "highly_negative"]
        assert len(highly_negative_alerts) >= 1


class TestSaveAlerts:
    """Tests for saving alerts to the database."""

    def test_saves_alerts_to_db(self, db):
        """save_alerts should persist alerts and return IDs."""
        system = AlertSystem(db)

        alerts = [
            Alert(
                alert_type="negative_spike",
                severity="high",
                message="Test spike",
                details={"ratio": 0.8}
            ),
            Alert(
                alert_type="volume_spike",
                severity="medium",
                message="Test volume",
                details={"count": 50}
            ),
        ]

        ids = system.save_alerts("Apple", alerts)
        assert len(ids) == 2
        assert all(isinstance(id_, int) for id_ in ids)

        # Verify persistence
        stored = db.get_alerts("Apple", unacknowledged_only=True)
        assert len(stored) == 2

    def test_saves_empty_list(self, db):
        """save_alerts with empty list should return empty IDs."""
        system = AlertSystem(db)
        ids = system.save_alerts("Apple", [])
        assert ids == []


class TestAlertEdgeCases:
    """Edge case tests for the alert system."""

    def test_single_mention_brand(self, db, sample_mention):
        """Should handle brand with only one mention gracefully."""
        now = datetime.now()

        db.add_mention(sample_mention(
            url="https://example.com/single",
            brand="Tiny",
            sentiment="positive",
            sentiment_score=0.5,
            scraped_at=now - timedelta(hours=2),
            published_at=now - timedelta(hours=2),
        ))

        system = AlertSystem(db, min_mentions_for_alert=5)
        alerts = system.run_all_checks("Tiny")

        # Should not crash; should return empty or very few alerts
        assert isinstance(alerts, list)

    def test_brand_with_all_positive_mentions(self, db, sample_mention):
        """Should return no spike alerts when everything is positive."""
        now = datetime.now()

        for i in range(20):
            db.add_mention(sample_mention(
                url=f"https://example.com/allpos-{i}",
                brand="HappyBrand",
                sentiment="positive",
                sentiment_score=0.8,
                scraped_at=now - timedelta(hours=i + 1),
                published_at=now - timedelta(hours=i + 1),
            ))

        system = AlertSystem(db, min_mentions_for_alert=5)

        neg_spike = system.check_negative_spike("HappyBrand")
        assert neg_spike is None

        highly_neg = system.check_highly_negative_mention("HappyBrand")
        assert len(highly_neg) == 0
