"""Summary generator module using Ollama."""

import json
import logging
import re
from typing import Dict, List, Optional
from dataclasses import dataclass

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


@dataclass
class BrandSummary:
    """Summary of brand perception."""
    overall_sentiment: str
    summary: str
    key_themes: List[str]
    positive_highlights: List[str]
    negative_concerns: List[str]
    recommendations: List[str]


class Summarizer:
    """Generates summaries of brand perception using Ollama."""

    def __init__(self, model: str = "llama3.1", temperature: float = 0.3):
        """Initialize the summarizer.

        Args:
            model: Ollama model name.
            temperature: LLM temperature.
        """
        self.llm = ChatOllama(model=model, temperature=temperature)

        self.summary_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a brand analyst expert. Generate comprehensive summaries of brand perception based on collected mentions.

Your response must be valid JSON with these fields:
- overall_sentiment: "positive", "negative", "mixed", or "neutral"
- summary: 2-3 paragraph summary of overall brand perception
- key_themes: list of 3-5 main themes/topics being discussed
- positive_highlights: list of 2-4 positive things people are saying
- negative_concerns: list of 2-4 concerns or criticisms
- recommendations: list of 2-3 actionable recommendations for the brand

Be specific and reference actual content from the mentions."""),
            ("human", """Generate a brand perception summary for "{brand}".

Statistics:
- Total mentions: {total_mentions}
- Positive: {positive_count} ({positive_pct}%)
- Negative: {negative_count} ({negative_pct}%)
- Neutral: {neutral_count} ({neutral_pct}%)
- Average sentiment score: {avg_score}

Recent mentions (showing {shown_count} of {total_mentions}):
{mentions_text}

Respond with only valid JSON, no other text.""")
        ])

    def generate_summary(
        self,
        brand: str,
        mentions: List[Dict],
        sentiment_stats: Dict
    ) -> BrandSummary:
        """Generate a summary of brand perception.

        Args:
            brand: Brand name.
            mentions: List of mention dictionaries with sentiment.
            sentiment_stats: Sentiment statistics dictionary.

        Returns:
            BrandSummary with analysis.
        """
        # Prepare mentions text (limit to avoid context overflow)
        mentions_text = self._format_mentions(mentions[:20])

        # Calculate percentages
        total = sentiment_stats.get("total", 0) or 1
        positive = sentiment_stats.get("positive", {}).get("count", 0)
        negative = sentiment_stats.get("negative", {}).get("count", 0)
        neutral = sentiment_stats.get("neutral", {}).get("count", 0)

        avg_score = (
            sentiment_stats.get("positive", {}).get("avg_score", 0) * positive +
            sentiment_stats.get("negative", {}).get("avg_score", 0) * negative +
            sentiment_stats.get("neutral", {}).get("avg_score", 0) * neutral
        ) / total if total > 0 else 0

        try:
            chain = self.summary_prompt | self.llm
            response = chain.invoke({
                "brand": brand,
                "total_mentions": total,
                "positive_count": positive,
                "positive_pct": round(positive / total * 100, 1),
                "negative_count": negative,
                "negative_pct": round(negative / total * 100, 1),
                "neutral_count": neutral,
                "neutral_pct": round(neutral / total * 100, 1),
                "avg_score": round(avg_score, 2),
                "shown_count": min(20, len(mentions)),
                "mentions_text": mentions_text
            })

            return self._parse_response(response.content)

        except Exception as e:
            logger.error("Summary generation error: %s", e)
            return BrandSummary(
                overall_sentiment="unknown",
                summary=f"Unable to generate summary: {str(e)}",
                key_themes=[],
                positive_highlights=[],
                negative_concerns=[],
                recommendations=[]
            )

    def _format_mentions(self, mentions: List[Dict]) -> str:
        """Format mentions for prompt context.

        Args:
            mentions: List of mention dictionaries.

        Returns:
            Formatted string of mentions.
        """
        formatted = []

        for i, mention in enumerate(mentions, 1):
            sentiment = mention.get("sentiment") or "unknown"
            source = mention.get("source", "unknown")
            title = mention.get("title", "No title")[:100]
            content = mention.get("content", "")[:300]

            formatted.append(
                f"{i}. [{sentiment.upper()}] [{source}]\n"
                f"   Title: {title}\n"
                f"   Content: {content}..."
            )

        return "\n\n".join(formatted)

    def _parse_response(self, response_text: str) -> BrandSummary:
        """Parse LLM response into BrandSummary.

        Args:
            response_text: Raw LLM response.

        Returns:
            Parsed BrandSummary.
        """
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response_text)

            return BrandSummary(
                overall_sentiment=data.get("overall_sentiment", "unknown"),
                summary=data.get("summary", ""),
                key_themes=data.get("key_themes", []),
                positive_highlights=data.get("positive_highlights", []),
                negative_concerns=data.get("negative_concerns", []),
                recommendations=data.get("recommendations", [])
            )

        except (json.JSONDecodeError, ValueError):
            # Fallback: return raw response as summary
            return BrandSummary(
                overall_sentiment="unknown",
                summary=response_text[:1000],
                key_themes=[],
                positive_highlights=[],
                negative_concerns=[],
                recommendations=[]
            )

    def generate_quick_summary(
        self,
        brand: str,
        mentions: List[Dict]
    ) -> str:
        """Generate a quick one-paragraph summary.

        Args:
            brand: Brand name.
            mentions: List of recent mentions.

        Returns:
            Single paragraph summary string.
        """
        quick_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a brand analyst. Write a brief, insightful summary."),
            ("human", """In 2-3 sentences, summarize what people are saying about "{brand}" based on these {count} recent mentions:

{mentions}

Focus on the main sentiment and key topics.""")
        ])

        mentions_text = "\n".join([
            f"- [{m.get('sentiment', 'unknown')}] {m.get('title', '')[:80]}"
            for m in mentions[:10]
        ])

        try:
            chain = quick_prompt | self.llm
            response = chain.invoke({
                "brand": brand,
                "count": len(mentions),
                "mentions": mentions_text
            })
            return response.content

        except Exception as e:
            return f"Unable to generate summary: {str(e)}"
