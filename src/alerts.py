"""Alert system for detecting sentiment spikes and anomalies."""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from .database import Database


@dataclass
class Alert:
    """Represents an alert."""
    alert_type: str
    severity: str  # "low", "medium", "high"
    message: str
    details: Dict


class AlertSystem:
    """Monitors for sentiment spikes and generates alerts."""

    def __init__(
        self,
        db: Database,
        negative_spike_threshold: float = 0.3,
        min_mentions_for_alert: int = 5,
        comparison_days: int = 7
    ):
        """Initialize the alert system.

        Args:
            db: Database instance.
            negative_spike_threshold: Ratio increase to trigger negative spike alert.
            min_mentions_for_alert: Minimum mentions needed to generate alerts.
            comparison_days: Days to compare for trend analysis.
        """
        self.db = db
        self.negative_spike_threshold = negative_spike_threshold
        self.min_mentions_for_alert = min_mentions_for_alert
        self.comparison_days = comparison_days

    def check_negative_spike(self, brand: str) -> Optional[Alert]:
        """Check for negative sentiment spike.

        Compares recent negative ratio to historical average.

        Args:
            brand: Brand name to check.

        Returns:
            Alert if spike detected, None otherwise.
        """
        # Get recent stats (last 24 hours)
        recent_stats = self._get_period_stats(brand, hours=24)

        # Get historical stats (previous week)
        historical_stats = self._get_period_stats(
            brand,
            hours=self.comparison_days * 24,
            offset_hours=24
        )

        if recent_stats["total"] < self.min_mentions_for_alert:
            return None

        if historical_stats["total"] < self.min_mentions_for_alert:
            return None

        recent_negative_ratio = recent_stats["negative"] / recent_stats["total"]
        historical_negative_ratio = historical_stats["negative"] / max(historical_stats["total"], 1)

        # Check if negative ratio increased significantly
        if historical_negative_ratio > 0:
            increase = (recent_negative_ratio - historical_negative_ratio) / historical_negative_ratio
        else:
            increase = recent_negative_ratio

        if increase >= self.negative_spike_threshold:
            severity = self._calculate_severity(increase)

            return Alert(
                alert_type="negative_spike",
                severity=severity,
                message=f"Negative sentiment spike detected for {brand}",
                details={
                    "recent_negative_ratio": round(recent_negative_ratio * 100, 1),
                    "historical_negative_ratio": round(historical_negative_ratio * 100, 1),
                    "increase_percent": round(increase * 100, 1),
                    "recent_mentions": recent_stats["total"],
                    "recent_negative": recent_stats["negative"]
                }
            )

        return None

    def check_volume_spike(self, brand: str) -> Optional[Alert]:
        """Check for unusual mention volume.

        Args:
            brand: Brand name to check.

        Returns:
            Alert if volume spike detected, None otherwise.
        """
        # Get recent volume (last 24 hours)
        recent_stats = self._get_period_stats(brand, hours=24)

        # Get average daily volume (previous week)
        historical_stats = self._get_period_stats(
            brand,
            hours=self.comparison_days * 24,
            offset_hours=24
        )

        if historical_stats["total"] < self.min_mentions_for_alert:
            return None

        avg_daily = historical_stats["total"] / self.comparison_days

        if avg_daily > 0 and recent_stats["total"] > avg_daily * 2:
            increase = (recent_stats["total"] - avg_daily) / avg_daily

            return Alert(
                alert_type="volume_spike",
                severity="medium",
                message=f"Unusual mention volume for {brand}",
                details={
                    "recent_count": recent_stats["total"],
                    "average_daily": round(avg_daily, 1),
                    "increase_percent": round(increase * 100, 1)
                }
            )

        return None

    def check_highly_negative_mention(
        self,
        brand: str,
        threshold: float = -0.8
    ) -> List[Alert]:
        """Check for highly negative individual mentions.

        Args:
            brand: Brand name to check.
            threshold: Sentiment score threshold (very negative).

        Returns:
            List of alerts for highly negative mentions.
        """
        alerts = []

        mentions = self.db.get_mentions(brand, days=1)

        for mention in mentions:
            score = mention.get("sentiment_score")
            if score is not None and score <= threshold:
                alerts.append(Alert(
                    alert_type="highly_negative",
                    severity="medium",
                    message=f"Highly negative mention detected for {brand}",
                    details={
                        "title": mention.get("title", "")[:100],
                        "source": mention.get("source"),
                        "sentiment_score": score,
                        "url": mention.get("url")
                    }
                ))

        return alerts

    def _get_period_stats(
        self,
        brand: str,
        hours: int,
        offset_hours: int = 0
    ) -> Dict[str, int]:
        """Get sentiment stats for a specific time period.

        Args:
            brand: Brand name.
            hours: Period length in hours.
            offset_hours: Hours to offset from now.

        Returns:
            Dictionary with total, positive, negative, neutral counts.
        """
        # This is a simplified version - in production you'd query by date range
        mentions = self.db.get_mentions(brand, days=max(1, hours // 24 + 1))

        now = datetime.now()
        period_start = now - timedelta(hours=hours + offset_hours)
        period_end = now - timedelta(hours=offset_hours)

        filtered = []
        for m in mentions:
            scraped = m.get("scraped_at")
            if scraped is None:
                continue
            if isinstance(scraped, str):
                try:
                    scraped = datetime.fromisoformat(scraped)
                except ValueError:
                    continue
            if period_start <= scraped <= period_end:
                filtered.append(m)

        stats = {
            "total": len(filtered),
            "positive": sum(1 for m in filtered if m.get("sentiment") == "positive"),
            "negative": sum(1 for m in filtered if m.get("sentiment") == "negative"),
            "neutral": sum(1 for m in filtered if m.get("sentiment") == "neutral")
        }

        return stats

    def _calculate_severity(self, increase: float) -> str:
        """Calculate alert severity based on increase percentage.

        Args:
            increase: Percentage increase (0-1+).

        Returns:
            Severity level string.
        """
        if increase >= 1.0:  # 100%+ increase
            return "high"
        elif increase >= 0.5:  # 50%+ increase
            return "medium"
        else:
            return "low"

    def run_all_checks(self, brand: str) -> List[Alert]:
        """Run all alert checks for a brand.

        Args:
            brand: Brand name to check.

        Returns:
            List of all triggered alerts.
        """
        alerts = []

        # Check for negative spike
        negative_spike = self.check_negative_spike(brand)
        if negative_spike:
            alerts.append(negative_spike)

        # Check for volume spike
        volume_spike = self.check_volume_spike(brand)
        if volume_spike:
            alerts.append(volume_spike)

        # Check for highly negative mentions
        highly_negative = self.check_highly_negative_mention(brand)
        alerts.extend(highly_negative)

        return alerts

    def save_alerts(self, brand: str, alerts: List[Alert]) -> List[int]:
        """Save alerts to database.

        Args:
            brand: Brand name.
            alerts: List of alerts to save.

        Returns:
            List of saved alert IDs.
        """
        alert_ids = []

        for alert in alerts:
            alert_id = self.db.add_alert(
                brand=brand,
                alert_type=alert.alert_type,
                severity=alert.severity,
                message=f"{alert.message}\n\nDetails: {alert.details}"
            )
            alert_ids.append(alert_id)

        return alert_ids
