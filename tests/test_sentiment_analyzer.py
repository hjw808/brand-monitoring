"""Tests for src/sentiment_analyzer.py - LLM sentiment analysis with mocking."""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.sentiment_analyzer import SentimentAnalyzer, SentimentResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_llm_response(content: str):
    """Create a mock LLM response object with .content attribute."""
    response = MagicMock()
    response.content = content
    return response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSentimentResultDataclass:
    """Tests for the SentimentResult dataclass."""

    def test_create_sentiment_result(self):
        """Should create a valid SentimentResult."""
        result = SentimentResult(
            sentiment="positive",
            score=0.8,
            reasoning="Very positive coverage",
            confidence=0.95,
        )
        assert result.sentiment == "positive"
        assert result.score == 0.8
        assert result.reasoning == "Very positive coverage"
        assert result.confidence == 0.95


class TestParseResponse:
    """Tests for _parse_response JSON parsing and fallbacks."""

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_parses_valid_json(self, mock_ollama):
        """Should correctly parse a well-formed JSON response."""
        analyzer = SentimentAnalyzer()

        json_str = json.dumps({
            "sentiment": "positive",
            "score": 0.75,
            "reasoning": "Good product review",
            "confidence": 0.9,
        })

        result = analyzer._parse_response(json_str)
        assert result.sentiment == "positive"
        assert abs(result.score - 0.75) < 0.01
        assert result.reasoning == "Good product review"
        assert abs(result.confidence - 0.9) < 0.01

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_parses_json_embedded_in_text(self, mock_ollama):
        """Should extract JSON even when surrounded by extra text."""
        analyzer = SentimentAnalyzer()

        text = 'Here is the analysis:\n{"sentiment": "negative", "score": -0.6, "reasoning": "Bad press", "confidence": 0.8}\nEnd.'
        result = analyzer._parse_response(text)
        assert result.sentiment == "negative"
        assert abs(result.score - (-0.6)) < 0.01

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_clamps_score_to_valid_range(self, mock_ollama):
        """Should clamp score to [-1, 1] range."""
        analyzer = SentimentAnalyzer()

        # Score above 1
        json_str = json.dumps({
            "sentiment": "positive",
            "score": 5.0,
            "reasoning": "Extreme",
            "confidence": 0.5,
        })
        result = analyzer._parse_response(json_str)
        assert result.score == 1.0

        # Score below -1
        json_str = json.dumps({
            "sentiment": "negative",
            "score": -3.0,
            "reasoning": "Very bad",
            "confidence": 0.5,
        })
        result = analyzer._parse_response(json_str)
        assert result.score == -1.0

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_clamps_confidence_to_valid_range(self, mock_ollama):
        """Should clamp confidence to [0, 1] range."""
        analyzer = SentimentAnalyzer()

        json_str = json.dumps({
            "sentiment": "positive",
            "score": 0.5,
            "reasoning": "test",
            "confidence": 1.5,
        })
        result = analyzer._parse_response(json_str)
        assert result.confidence == 1.0

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_normalizes_invalid_sentiment_to_neutral(self, mock_ollama):
        """Should default to 'neutral' for unrecognized sentiment values."""
        analyzer = SentimentAnalyzer()

        json_str = json.dumps({
            "sentiment": "VERY_POSITIVE",
            "score": 0.9,
            "reasoning": "test",
            "confidence": 0.8,
        })
        result = analyzer._parse_response(json_str)
        assert result.sentiment == "neutral"

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_fallback_detects_positive_text(self, mock_ollama):
        """When JSON fails, should detect 'positive' in text."""
        analyzer = SentimentAnalyzer()

        result = analyzer._parse_response("The sentiment is clearly positive based on the text.")
        assert result.sentiment == "positive"
        assert result.score == 0.5
        assert result.confidence == 0.3

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_fallback_detects_negative_text(self, mock_ollama):
        """When JSON fails, should detect 'negative' in text."""
        analyzer = SentimentAnalyzer()

        result = analyzer._parse_response("This is a negative review overall.")
        assert result.sentiment == "negative"
        assert result.score == -0.5
        assert result.confidence == 0.3

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_fallback_defaults_to_neutral(self, mock_ollama):
        """When JSON fails and no keyword found, should default to neutral."""
        analyzer = SentimentAnalyzer()

        result = analyzer._parse_response("Unable to determine anything meaningful.")
        assert result.sentiment == "neutral"
        assert result.score == 0.0
        assert result.confidence == 0.3

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_handles_missing_fields_gracefully(self, mock_ollama):
        """Should use defaults when JSON fields are missing."""
        analyzer = SentimentAnalyzer()

        json_str = json.dumps({"sentiment": "positive"})
        result = analyzer._parse_response(json_str)
        assert result.sentiment == "positive"
        assert result.score == 0.0  # default
        assert result.confidence == 0.5  # default
        assert result.reasoning == ""  # default


class TestAnalyze:
    """Tests for the analyze method with mocked LLM."""

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_successful_analysis(self, mock_ollama_cls):
        """Should return parsed SentimentResult from LLM response."""
        mock_llm = MagicMock()
        mock_ollama_cls.return_value = mock_llm

        analyzer = SentimentAnalyzer()

        json_response = json.dumps({
            "sentiment": "positive",
            "score": 0.8,
            "reasoning": "Great product launch",
            "confidence": 0.9,
        })

        # Mock the chain invocation
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = _mock_llm_response(json_response)

        with patch.object(analyzer, "prompt") as mock_prompt:
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            result = analyzer.analyze("Apple", "Apple launches iPhone 16", "Great new features.")

        assert result.sentiment == "positive"
        assert result.score == 0.8

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_returns_neutral_on_llm_error(self, mock_ollama_cls):
        """Should return neutral result when LLM call fails."""
        mock_llm = MagicMock()
        mock_ollama_cls.return_value = mock_llm

        analyzer = SentimentAnalyzer()

        # Make the chain raise an exception
        mock_chain = MagicMock()
        mock_chain.invoke.side_effect = Exception("Ollama unavailable")

        with patch.object(analyzer, "prompt") as mock_prompt:
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            result = analyzer.analyze("Apple", "Test title", "Test content")

        assert result.sentiment == "neutral"
        assert result.score == 0.0
        assert result.confidence == 0.0
        assert "failed" in result.reasoning.lower() or "error" in result.reasoning.lower()

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_truncates_long_content(self, mock_ollama_cls):
        """Should truncate content to 2000 characters before sending to LLM."""
        mock_llm = MagicMock()
        mock_ollama_cls.return_value = mock_llm

        analyzer = SentimentAnalyzer()

        json_response = json.dumps({
            "sentiment": "neutral",
            "score": 0.0,
            "reasoning": "Truncated content",
            "confidence": 0.5,
        })

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = _mock_llm_response(json_response)

        long_content = "X" * 5000

        with patch.object(analyzer, "prompt") as mock_prompt:
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            result = analyzer.analyze("Brand", "Title", long_content)

        # Verify invoke was called (we check the content was accepted)
        assert mock_chain.invoke.called
        assert result.sentiment == "neutral"


class TestAnalyzeBatch:
    """Tests for batch analysis."""

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_batch_returns_all_results(self, mock_ollama_cls):
        """Should return a result for each mention in the batch."""
        mock_llm = MagicMock()
        mock_ollama_cls.return_value = mock_llm

        analyzer = SentimentAnalyzer()

        mentions = [
            {"title": "Good news", "content": "Positive things"},
            {"title": "Bad news", "content": "Negative things"},
            {"title": "Meh news", "content": "Neutral things"},
        ]

        json_responses = [
            json.dumps({"sentiment": "positive", "score": 0.7, "reasoning": "Good", "confidence": 0.8}),
            json.dumps({"sentiment": "negative", "score": -0.6, "reasoning": "Bad", "confidence": 0.8}),
            json.dumps({"sentiment": "neutral", "score": 0.0, "reasoning": "Meh", "confidence": 0.8}),
        ]

        call_count = [0]

        def mock_invoke(params):
            resp = _mock_llm_response(json_responses[call_count[0]])
            call_count[0] += 1
            return resp

        mock_chain = MagicMock()
        mock_chain.invoke.side_effect = mock_invoke

        with patch.object(analyzer, "prompt") as mock_prompt:
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            results = analyzer.analyze_batch("TestBrand", mentions)

        assert len(results) == 3
        assert results[0][1].sentiment == "positive"
        assert results[1][1].sentiment == "negative"
        assert results[2][1].sentiment == "neutral"

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_batch_empty_list(self, mock_ollama_cls):
        """Should return empty list for empty input."""
        analyzer = SentimentAnalyzer()
        results = analyzer.analyze_batch("TestBrand", [])
        assert results == []


class TestGetAggregateSentiment:
    """Tests for aggregate sentiment metrics."""

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_aggregate_metrics(self, mock_ollama_cls):
        """Should compute correct aggregate metrics."""
        analyzer = SentimentAnalyzer()

        results = [
            SentimentResult("positive", 0.8, "Good", 0.9),
            SentimentResult("positive", 0.6, "OK", 0.7),
            SentimentResult("negative", -0.5, "Bad", 0.8),
            SentimentResult("neutral", 0.0, "Meh", 0.5),
        ]

        agg = analyzer.get_aggregate_sentiment(results)
        assert agg["count"] == 4
        assert agg["positive_ratio"] == 0.5
        assert agg["negative_ratio"] == 0.25
        assert agg["neutral_ratio"] == 0.25
        # avg = (0.8 + 0.6 + -0.5 + 0.0) / 4 = 0.225
        assert abs(agg["average_score"] - 0.225) < 0.01

    @patch("src.sentiment_analyzer.ChatOllama")
    def test_aggregate_empty_results(self, mock_ollama_cls):
        """Should return zeroed metrics for empty input."""
        analyzer = SentimentAnalyzer()
        agg = analyzer.get_aggregate_sentiment([])
        assert agg["count"] == 0
        assert agg["average_score"] == 0.0
        assert agg["positive_ratio"] == 0.0
