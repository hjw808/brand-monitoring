"""SQLite database module for storing brand mentions and sentiment data."""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class Mention:
    """Represents a brand mention."""
    id: Optional[int]
    brand: str
    source: str  # "news", "reddit", "twitter"
    title: str
    content: str
    url: str
    author: Optional[str]
    published_at: datetime
    scraped_at: datetime
    sentiment: Optional[str]  # "positive", "negative", "neutral"
    sentiment_score: Optional[float]  # -1 to 1
    sentiment_reasoning: Optional[str]


class Database:
    """SQLite database for brand monitoring data."""

    def __init__(self, db_path: str = "data/brand_monitoring.db"):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._create_tables()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _dt(dt: Optional[datetime]) -> Optional[str]:
        """Convert a datetime to an ISO-8601 string for SQLite storage.

        Python 3.12+ deprecated the automatic datetime adapter in sqlite3.
        Storing timestamps as TEXT (ISO-8601) keeps the schema portable and
        avoids DeprecationWarnings on every parameterised query.
        """
        return dt.isoformat() if dt is not None else None

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Mentions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                url TEXT UNIQUE,
                author TEXT,
                published_at TIMESTAMP,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sentiment TEXT,
                sentiment_score REAL,
                sentiment_reasoning TEXT
            )
        """)

        # Summaries table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                period_start TIMESTAMP,
                period_end TIMESTAMP,
                total_mentions INTEGER,
                positive_count INTEGER,
                negative_count INTEGER,
                neutral_count INTEGER,
                summary_text TEXT,
                key_themes TEXT
            )
        """)

        # Alerts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                acknowledged INTEGER DEFAULT 0
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_brand ON mentions(brand)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_source ON mentions(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_sentiment ON mentions(sentiment)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_published ON mentions(published_at)")

        conn.commit()
        conn.close()

    def add_mention(self, mention: Mention) -> Optional[int]:
        """Add a mention to the database.

        Args:
            mention: Mention object to add.

        Returns:
            ID of inserted row, or None if duplicate.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO mentions
                (brand, source, title, content, url, author, published_at, scraped_at,
                 sentiment, sentiment_score, sentiment_reasoning)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mention.brand,
                mention.source,
                mention.title,
                mention.content,
                mention.url,
                mention.author,
                self._dt(mention.published_at),
                self._dt(mention.scraped_at),
                mention.sentiment,
                mention.sentiment_score,
                mention.sentiment_reasoning
            ))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Duplicate URL
            return None
        finally:
            conn.close()

    def update_sentiment(
        self,
        mention_id: int,
        sentiment: str,
        sentiment_score: float,
        reasoning: str
    ) -> None:
        """Update sentiment for a mention.

        Args:
            mention_id: ID of the mention to update.
            sentiment: Sentiment label.
            sentiment_score: Sentiment score (-1 to 1).
            reasoning: Explanation for the sentiment.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE mentions
            SET sentiment = ?, sentiment_score = ?, sentiment_reasoning = ?
            WHERE id = ?
        """, (sentiment, sentiment_score, reasoning, mention_id))

        conn.commit()
        conn.close()

    def get_mentions(
        self,
        brand: str,
        source: Optional[str] = None,
        sentiment: Optional[str] = None,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get mentions for a brand.

        Args:
            brand: Brand name to filter by.
            source: Optional source filter.
            sentiment: Optional sentiment filter.
            days: Number of days to look back.
            limit: Maximum number of results.

        Returns:
            List of mention dictionaries.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
            SELECT * FROM mentions
            WHERE brand = ? COLLATE NOCASE AND scraped_at >= ?
        """
        params = [brand, self._dt(datetime.now() - timedelta(days=days))]

        if source:
            query += " AND source = ?"
            params.append(source)

        if sentiment:
            query += " AND sentiment = ?"
            params.append(sentiment)

        query += " ORDER BY published_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_unanalyzed_mentions(self, limit: int = 50, brand: str = None) -> List[Dict[str, Any]]:
        """Get mentions without sentiment analysis.

        Args:
            limit: Maximum number of results.
            brand: If provided, only return mentions for this brand.

        Returns:
            List of mention dictionaries.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if brand:
            cursor.execute("""
                SELECT * FROM mentions
                WHERE sentiment IS NULL AND LOWER(brand) = LOWER(?)
                ORDER BY scraped_at DESC
                LIMIT ?
            """, (brand, limit))
        else:
            cursor.execute("""
                SELECT * FROM mentions
                WHERE sentiment IS NULL
                ORDER BY scraped_at DESC
                LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_sentiment_stats(
        self,
        brand: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """Get sentiment statistics for a brand.

        Args:
            brand: Brand name.
            days: Number of days to analyze.

        Returns:
            Dictionary with sentiment counts and percentages.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff = self._dt(datetime.now() - timedelta(days=days))

        cursor.execute("""
            SELECT
                sentiment,
                COUNT(*) as count,
                AVG(sentiment_score) as avg_score
            FROM mentions
            WHERE brand = ? COLLATE NOCASE AND scraped_at >= ? AND sentiment IS NOT NULL
            GROUP BY sentiment
        """, (brand, cutoff))

        rows = cursor.fetchall()
        conn.close()

        stats = {
            "positive": {"count": 0, "avg_score": 0},
            "negative": {"count": 0, "avg_score": 0},
            "neutral": {"count": 0, "avg_score": 0},
            "total": 0
        }

        for row in rows:
            if row["sentiment"] in stats:
                stats[row["sentiment"]] = {
                    "count": row["count"],
                    "avg_score": row["avg_score"] or 0
                }
                stats["total"] += row["count"]

        return stats

    def get_sentiment_trend(
        self,
        brand: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get daily sentiment trend for a brand.

        Args:
            brand: Brand name.
            days: Number of days to analyze.

        Returns:
            List of daily sentiment data.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff = self._dt(datetime.now() - timedelta(days=days))

        cursor.execute("""
            SELECT
                DATE(published_at) as date,
                sentiment,
                COUNT(*) as count,
                AVG(sentiment_score) as avg_score
            FROM mentions
            WHERE brand = ? COLLATE NOCASE AND published_at >= ? AND sentiment IS NOT NULL
            GROUP BY DATE(published_at), sentiment
            ORDER BY date
        """, (brand, cutoff))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def add_alert(
        self,
        brand: str,
        alert_type: str,
        severity: str,
        message: str
    ) -> int:
        """Add an alert to the database.

        Args:
            brand: Brand name.
            alert_type: Type of alert (e.g., "negative_spike").
            severity: Alert severity ("low", "medium", "high").
            message: Alert message.

        Returns:
            ID of inserted alert.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO alerts (brand, alert_type, severity, message)
            VALUES (?, ?, ?, ?)
        """, (brand, alert_type, severity, message))

        conn.commit()
        alert_id = cursor.lastrowid
        conn.close()

        return alert_id

    def get_alerts(
        self,
        brand: str,
        unacknowledged_only: bool = True,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get alerts for a brand.

        Args:
            brand: Brand name.
            unacknowledged_only: Only return unacknowledged alerts.
            limit: Maximum number of results.

        Returns:
            List of alert dictionaries.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM alerts WHERE brand = ? COLLATE NOCASE"
        params = [brand]

        if unacknowledged_only:
            query += " AND acknowledged = 0"

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def acknowledge_alert(self, alert_id: int) -> None:
        """Mark an alert as acknowledged.

        Args:
            alert_id: ID of the alert to acknowledge.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE alerts SET acknowledged = 1 WHERE id = ?",
            (alert_id,)
        )

        conn.commit()
        conn.close()

    def save_summary(
        self,
        brand: str,
        period_start: datetime,
        period_end: datetime,
        total_mentions: int,
        positive_count: int,
        negative_count: int,
        neutral_count: int,
        summary_text: str,
        key_themes: str
    ) -> int:
        """Save a brand summary to the database.

        Args:
            brand: Brand name.
            period_start: Start of summary period.
            period_end: End of summary period.
            total_mentions: Total mention count.
            positive_count: Positive mention count.
            negative_count: Negative mention count.
            neutral_count: Neutral mention count.
            summary_text: Generated summary.
            key_themes: Identified themes.

        Returns:
            ID of inserted summary.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO summaries
            (brand, period_start, period_end, total_mentions, positive_count,
             negative_count, neutral_count, summary_text, key_themes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            brand, self._dt(period_start), self._dt(period_end), total_mentions,
            positive_count, negative_count, neutral_count,
            summary_text, key_themes
        ))

        conn.commit()
        summary_id = cursor.lastrowid
        conn.close()

        return summary_id

    def get_latest_summary(self, brand: str) -> Optional[Dict[str, Any]]:
        """Get the latest summary for a brand.

        Args:
            brand: Brand name.

        Returns:
            Summary dictionary or None.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM summaries
            WHERE brand = ? COLLATE NOCASE
            ORDER BY generated_at DESC
            LIMIT 1
        """, (brand,))

        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def get_source_distribution(self, brand: str, days: int = 7) -> Dict[str, int]:
        """Get mention count by source for a brand.

        Args:
            brand: Brand name.
            days: Number of days to analyze.

        Returns:
            Dictionary mapping source to count.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff = self._dt(datetime.now() - timedelta(days=days))

        cursor.execute("""
            SELECT source, COUNT(*) as count
            FROM mentions
            WHERE brand = ? COLLATE NOCASE AND scraped_at >= ?
            GROUP BY source
        """, (brand, cutoff))

        rows = cursor.fetchall()
        conn.close()

        return {row["source"]: row["count"] for row in rows}
