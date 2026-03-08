"""Sentiment analysis module using Ollama."""

import json
import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    """Result of sentiment analysis."""
    sentiment: str  # "positive", "negative", "neutral"
    score: float  # -1 to 1
    reasoning: str
    confidence: float  # 0 to 1


class SentimentAnalyzer:
    """Analyzes sentiment of brand mentions using Ollama."""

    def __init__(self, model: str = "llama3.1", temperature: float = 0):
        """Initialize the sentiment analyzer.

        Args:
            model: Ollama model name.
            temperature: LLM temperature (0 for consistent results).
        """
        self.llm = ChatOllama(model=model, temperature=temperature)

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a sentiment analysis expert. Analyze the sentiment of text regarding a specific brand or company.

Your response must be valid JSON with these exact fields:
- sentiment: "positive", "negative", or "neutral"
- score: number from -1 (very negative) to 1 (very positive), 0 is neutral
- reasoning: brief explanation (1-2 sentences)
- confidence: number from 0 to 1 indicating how confident you are

Consider:
- Direct statements about the brand
- Implied opinions
- Context and tone
- Specific praise or criticism"""),
            ("human", """Analyze the sentiment about "{brand}" in this text:

Title: {title}
Content: {content}

Respond with only valid JSON, no other text.""")
        ])

    def analyze(
        self,
        brand: str,
        title: str,
        content: str
    ) -> SentimentResult:
        """Analyze sentiment of a single mention.

        Args:
            brand: Brand name being monitored.
            title: Title of the mention.
            content: Content/body of the mention.

        Returns:
            SentimentResult with sentiment analysis.
        """
        # Truncate content if too long
        content = content[:2000] if content else ""

        try:
            chain = self.prompt | self.llm
            response = chain.invoke({
                "brand": brand,
                "title": title,
                "content": content
            })

            # Parse JSON response
            result = self._parse_response(response.content)
            return result

        except Exception as e:
            logger.error("Sentiment analysis error: %s", e)
            # Return neutral on error
            return SentimentResult(
                sentiment="neutral",
                score=0.0,
                reasoning=f"Analysis failed: {str(e)}",
                confidence=0.0
            )

    def _parse_response(self, response_text: str) -> SentimentResult:
        """Parse LLM response into SentimentResult.

        Args:
            response_text: Raw LLM response.

        Returns:
            Parsed SentimentResult.
        """
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response_text)

            sentiment = data.get("sentiment", "neutral").lower()
            if sentiment not in ["positive", "negative", "neutral"]:
                sentiment = "neutral"

            score = float(data.get("score", 0))
            score = max(-1, min(1, score))  # Clamp to [-1, 1]

            confidence = float(data.get("confidence", 0.5))
            confidence = max(0, min(1, confidence))

            return SentimentResult(
                sentiment=sentiment,
                score=score,
                reasoning=data.get("reasoning", ""),
                confidence=confidence
            )

        except (json.JSONDecodeError, ValueError) as e:
            # Fallback: try to extract sentiment from text
            text_lower = response_text.lower()
            if "positive" in text_lower:
                return SentimentResult("positive", 0.5, response_text[:200], 0.3)
            elif "negative" in text_lower:
                return SentimentResult("negative", -0.5, response_text[:200], 0.3)
            else:
                return SentimentResult("neutral", 0.0, response_text[:200], 0.3)

    def analyze_batch(
        self,
        brand: str,
        mentions: List[Dict[str, str]]
    ) -> List[Tuple[Dict, SentimentResult]]:
        """Analyze sentiment of multiple mentions.

        Args:
            brand: Brand name being monitored.
            mentions: List of mention dictionaries with 'title' and 'content'.

        Returns:
            List of (mention, SentimentResult) tuples.
        """
        results = []

        for mention in mentions:
            title = mention.get("title", "")
            content = mention.get("content", "")

            result = self.analyze(brand, title, content)
            results.append((mention, result))

        return results

    def get_aggregate_sentiment(
        self,
        results: List[SentimentResult]
    ) -> Dict[str, float]:
        """Calculate aggregate sentiment metrics.

        Args:
            results: List of SentimentResults.

        Returns:
            Dictionary with aggregate metrics.
        """
        if not results:
            return {
                "average_score": 0.0,
                "positive_ratio": 0.0,
                "negative_ratio": 0.0,
                "neutral_ratio": 0.0,
                "count": 0
            }

        total = len(results)
        positive = sum(1 for r in results if r.sentiment == "positive")
        negative = sum(1 for r in results if r.sentiment == "negative")
        neutral = sum(1 for r in results if r.sentiment == "neutral")
        avg_score = sum(r.score for r in results) / total

        return {
            "average_score": avg_score,
            "positive_ratio": positive / total,
            "negative_ratio": negative / total,
            "neutral_ratio": neutral / total,
            "count": total
        }
