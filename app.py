"""Streamlit dashboard for Brand Monitoring."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

from src.database import Database, Mention
from src.web_scraper import WebScraper
from src.reddit_scraper import get_reddit_scraper
from src.sentiment_analyzer import SentimentAnalyzer
from src.summarizer import Summarizer
from src.alerts import AlertSystem


# Page configuration
st.set_page_config(
    page_title="Brand Monitor",
    page_icon="📊",
    layout="wide"
)


def initialize_session_state():
    """Initialize Streamlit session state."""
    if "db" not in st.session_state:
        st.session_state.db = Database()

    if "web_scraper" not in st.session_state:
        st.session_state.web_scraper = WebScraper()

    if "reddit_scraper" not in st.session_state:
        st.session_state.reddit_scraper = get_reddit_scraper()

    if "sentiment_analyzer" not in st.session_state:
        st.session_state.sentiment_analyzer = SentimentAnalyzer()

    if "summarizer" not in st.session_state:
        st.session_state.summarizer = Summarizer()

    if "alert_system" not in st.session_state:
        st.session_state.alert_system = AlertSystem(st.session_state.db)

    if "current_brand" not in st.session_state:
        st.session_state.current_brand = ""


def _is_relevant(title: str, content: str, brand: str, keywords: list) -> bool:
    """Return True if the result is relevant to the brand.

    When keywords are provided they act as a relevance filter: at least one
    must appear in the title or content.  Without keywords every result passes
    (keeps existing behaviour for unambiguous brand names like "Tesla").
    """
    if not keywords:
        return True
    text = f"{title} {content or ''}".lower()
    return any(kw.lower() in text for kw in keywords)


def scrape_mentions(brand: str, keywords: list):
    """Scrape mentions from all sources."""
    all_mentions = []

    # Scrape web news
    with st.spinner("Scraping news articles..."):
        news_results = st.session_state.web_scraper.scrape_all_news(
            brand, keywords, max_results_per_source=15
        )
        new_news = 0
        skipped_news = 0
        for result in news_results:
            if not _is_relevant(result["title"], result["content"], brand, keywords):
                skipped_news += 1
                continue
            mention = Mention(
                id=None,
                brand=brand,
                source="news",
                title=result["title"],
                content=result["content"],
                url=result["url"],
                author=result.get("source_name"),
                published_at=result["published_at"],
                scraped_at=datetime.now(),
                sentiment=None,
                sentiment_score=None,
                sentiment_reasoning=None
            )
            mention_id = st.session_state.db.add_mention(mention)
            if mention_id:
                all_mentions.append(mention)
                new_news += 1

        if new_news:
            skip_note = f" ({skipped_news} irrelevant filtered out)" if skipped_news else ""
            st.success(f"Added {new_news} new articles{skip_note}")
        else:
            st.info("No new articles found")

    # Scrape Reddit
    with st.spinner("Scraping Reddit..."):
        reddit_results = st.session_state.reddit_scraper.search_brand(
            brand, keywords, limit=20
        )
        new_reddit = 0
        skipped_reddit = 0
        for result in reddit_results:
            if not _is_relevant(result["title"], result["content"], brand, keywords):
                skipped_reddit += 1
                continue
            mention = Mention(
                id=None,
                brand=brand,
                source="reddit",
                title=result["title"],
                content=result["content"],
                url=result["url"],
                author=result.get("author"),
                published_at=result["published_at"],
                scraped_at=datetime.now(),
                sentiment=None,
                sentiment_score=None,
                sentiment_reasoning=None
            )
            mention_id = st.session_state.db.add_mention(mention)
            if mention_id:
                all_mentions.append(mention)
                new_reddit += 1

        if new_reddit:
            skip_note = f" ({skipped_reddit} irrelevant filtered out)" if skipped_reddit else ""
            st.success(f"Added {new_reddit} new Reddit posts{skip_note}")
        else:
            st.info("No new Reddit posts found")

    return all_mentions


def analyze_sentiment(brand: str) -> int:
    """Analyze sentiment of unanalyzed mentions. Returns count analyzed."""
    unanalyzed = st.session_state.db.get_unanalyzed_mentions(limit=500, brand=brand)

    if not unanalyzed:
        return 0

    progress = st.progress(0)
    status = st.empty()

    for i, mention in enumerate(unanalyzed):
        status.text(f"Analyzing mention {i+1}/{len(unanalyzed)}...")

        result = st.session_state.sentiment_analyzer.analyze(
            brand,
            mention["title"],
            mention["content"] or ""
        )

        st.session_state.db.update_sentiment(
            mention["id"],
            result.sentiment,
            result.score,
            result.reasoning
        )

        progress.progress((i + 1) / len(unanalyzed))

    status.text(f"Analyzed {len(unanalyzed)} mentions")
    progress.empty()
    return len(unanalyzed)


# ── Shared chart styling ─────────────────────────────────────────────────────
_C = {"positive": "#22c55e", "negative": "#ef4444", "neutral": "#94a3b8"}

_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(size=13),
)

# Reusable axis styles
_XAXIS = dict(showgrid=False, zeroline=False)
_YAXIS = dict(showgrid=True, gridcolor="rgba(148,163,184,0.12)", zeroline=False)


def display_sentiment_overview(brand: str, days: int):
    """Display sentiment overview metrics."""
    stats = st.session_state.db.get_sentiment_stats(brand, days)
    total = stats["total"]
    pos   = stats["positive"]["count"]
    neg   = stats["negative"]["count"]
    neu   = stats["neutral"]["count"]

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Mentions", total)
    with col2:
        pct = pos / total * 100 if total else 0
        st.metric("Positive", pos, delta=f"{pct:.1f}%")
    with col3:
        pct = neg / total * 100 if total else 0
        st.metric("Negative", neg, delta=f"{pct:.1f}%", delta_color="inverse")
    with col4:
        pct = neu / total * 100 if total else 0
        st.metric("Neutral", neu, delta=f"{pct:.1f}%", delta_color="off")


def display_sentiment_chart(brand: str, days: int):
    """Display sentiment donut chart."""
    stats = st.session_state.db.get_sentiment_stats(brand, days)

    if stats["total"] == 0:
        st.info("No data to display")
        return

    pos   = stats["positive"]["count"]
    neg   = stats["negative"]["count"]
    neu   = stats["neutral"]["count"]
    total = stats["total"]

    fig = go.Figure(data=[go.Pie(
        labels=["Positive", "Negative", "Neutral"],
        values=[pos, neg, neu],
        marker=dict(
            colors=[_C["positive"], _C["negative"], _C["neutral"]],
            line=dict(color="rgba(0,0,0,0.15)", width=2),
        ),
        hole=0.62,
        textinfo="percent",
        textfont=dict(size=13),
        direction="clockwise",
        sort=False,
        hovertemplate="<b>%{label}</b><br>%{value} mentions (%{percent})<extra></extra>",
    )])

    fig.update_layout(
        **_LAYOUT,
        height=280,
        showlegend=True,
        legend=dict(
            orientation="h",
            xanchor="center", x=0.5,
            yanchor="top", y=-0.05,
            font=dict(size=12),
        ),
        margin=dict(t=10, b=40, l=10, r=10),
        annotations=[dict(
            text=f"<b>{total}</b><br><span style='font-size:11px'>total</span>",
            x=0.5, y=0.5,
            font=dict(size=17),
            showarrow=False,
        )],
    )

    st.plotly_chart(fig, use_container_width=True)


def display_trend_chart(brand: str, days: int):
    """Display sentiment trend over time as stacked bars."""
    trend_data = st.session_state.db.get_sentiment_trend(brand, days)

    if not trend_data:
        st.info("No trend data available")
        return

    df = pd.DataFrame(trend_data)
    df_pivot = (
        df.pivot(index="date", columns="sentiment", values="count")
        .fillna(0)
        .reset_index()
        .sort_values("date")
    )

    fig = go.Figure()

    for sentiment in ["positive", "neutral", "negative"]:
        if sentiment in df_pivot.columns:
            fig.add_trace(go.Bar(
                x=df_pivot["date"],
                y=df_pivot[sentiment],
                name=sentiment.capitalize(),
                marker_color=_C[sentiment],
                hovertemplate=f"<b>{sentiment.title()}</b>: %{{y}}<br>%{{x}}<extra></extra>",
            ))

    fig.update_layout(
        **_LAYOUT,
        barmode="stack",
        height=300,
        bargap=0.25,
        margin=dict(t=30, b=10, l=10, r=10),
        showlegend=True,
        legend=dict(orientation="h", x=0, y=1.08, font=dict(size=12)),
        xaxis=dict(**_XAXIS),
        yaxis=dict(**_YAXIS, title="Mentions"),
    )

    st.plotly_chart(fig, use_container_width=True)


def display_source_distribution(brand: str, days: int):
    """Display mentions by source as a horizontal bar chart."""
    distribution = st.session_state.db.get_source_distribution(brand, days)

    if not distribution:
        st.info("No source data available")
        return

    source_colors = {"news": "#6366f1", "reddit": "#f97316"}
    sources = list(distribution.keys())
    counts  = list(distribution.values())
    colors  = [source_colors.get(s, "#64748b") for s in sources]

    fig = go.Figure(go.Bar(
        x=counts,
        y=[s.capitalize() for s in sources],
        orientation="h",
        marker_color=colors,
        text=counts,
        textposition="outside",
        hovertemplate="<b>%{y}</b>: %{x} mentions<extra></extra>",
    ))

    fig.update_layout(
        **_LAYOUT,
        height=160,
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=50),
        xaxis=dict(**_YAXIS),
        yaxis=dict(showgrid=False, zeroline=False),
    )

    st.plotly_chart(fig, use_container_width=True)


_SENTIMENT_ICON = {"positive": "🟢 Positive", "negative": "🔴 Negative", "neutral": "⚪ Neutral"}


def display_mentions_table(brand: str, source_filter: str, sentiment_filter: str, days: int):
    """Display mentions in a table."""
    mentions = st.session_state.db.get_mentions(
        brand,
        source=source_filter if source_filter != "All" else None,
        sentiment=sentiment_filter.lower() if sentiment_filter != "All" else None,
        days=days,
        limit=200
    )

    if not mentions:
        st.info("No mentions found")
        return

    df = pd.DataFrame(mentions)

    df["sentiment"] = df["sentiment"].apply(
        lambda s: _SENTIMENT_ICON.get(s, "❓ Unknown")
    )
    df["sentiment_score"] = pd.to_numeric(df["sentiment_score"], errors="coerce")

    if "published_at" in df.columns:
        df["published_at"] = (
            pd.to_datetime(df["published_at"], format="mixed")
            .dt.strftime("%Y-%m-%d %H:%M")
        )

    display_df = df[["title", "source", "sentiment", "sentiment_score", "published_at", "url"]].copy()
    display_df.columns = ["Title", "Source", "Sentiment", "Score", "Published", "URL"]

    st.dataframe(
        display_df,
        column_config={
            "Title":     st.column_config.TextColumn(width="large"),
            "Source":    st.column_config.TextColumn(width="small"),
            "Sentiment": st.column_config.TextColumn(width="small"),
            "Score":     st.column_config.ProgressColumn(
                             min_value=-1, max_value=1, format="%.2f", width="small"
                         ),
            "Published": st.column_config.TextColumn(width="medium"),
            "URL":       st.column_config.LinkColumn("Link", width="small"),
        },
        hide_index=True,
        use_container_width=True,
        height=500,
    )
    st.caption(f"{len(df)} mentions")


def display_alerts(brand: str):
    """Display active alerts."""
    alerts = st.session_state.db.get_alerts(brand, unacknowledged_only=True)

    if not alerts:
        st.success("No active alerts")
        return

    for alert in alerts:
        severity_colors = {
            "high": "🔴",
            "medium": "🟡",
            "low": "🟢"
        }

        icon = severity_colors.get(alert["severity"], "⚪")

        with st.expander(f"{icon} {alert['alert_type'].replace('_', ' ').title()}", expanded=True):
            st.write(alert["message"])
            st.caption(f"Created: {alert['created_at']}")

            if st.button("Acknowledge", key=f"ack_{alert['id']}"):
                st.session_state.db.acknowledge_alert(alert["id"])
                st.rerun()


def display_summary(brand: str, days: int):
    """Display brand summary."""
    mentions = st.session_state.db.get_mentions(brand, days=days)
    stats = st.session_state.db.get_sentiment_stats(brand, days)

    if not mentions or stats["total"] == 0:
        st.info("Not enough data for a summary. Scrape some mentions first.")
        return

    if st.button("Generate AI Summary", type="primary"):
        with st.spinner("Generating summary with local LLM..."):
            summary = st.session_state.summarizer.generate_summary(
                brand, mentions, stats
            )

        color = _C.get(summary.overall_sentiment, _C["neutral"])
        st.markdown(
            f"<div style='padding:12px 18px;border-radius:8px;"
            f"background:{color}22;border-left:4px solid {color};"
            f"margin-bottom:16px;font-size:16px'>"
            f"<b>Overall: {summary.overall_sentiment.title()}</b></div>",
            unsafe_allow_html=True,
        )

        st.markdown(summary.summary)
        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            if summary.key_themes:
                st.markdown("**Key Themes**")
                for t in summary.key_themes:
                    st.markdown(f"- {t}")
            if summary.positive_highlights:
                st.markdown("**Positive Highlights**")
                for h in summary.positive_highlights:
                    st.markdown(f"- {h}")

        with col2:
            if summary.negative_concerns:
                st.markdown("**Concerns**")
                for c in summary.negative_concerns:
                    st.markdown(f"- {c}")
            if summary.recommendations:
                st.markdown("**Recommendations**")
                for r in summary.recommendations:
                    st.markdown(f"- {r}")


def main():
    """Main application entry point."""
    initialize_session_state()

    st.title("📊 Brand Monitoring Dashboard")

    # Sidebar - Brand Input
    with st.sidebar:
        st.header("Brand Settings")

        brand = st.text_input(
            "Brand Name",
            value=st.session_state.current_brand,
            placeholder="e.g., Tesla, Apple, Nike"
        )

        keywords = st.text_input(
            "Filter Keywords (comma-separated)",
            placeholder="e.g., iPhone, Mac, iOS",
            help=(
                "When provided, only results that mention at least one of these "
                "keywords are kept. Use this to avoid false positives for "
                "ambiguous names — e.g. add 'iPhone, Mac' when monitoring 'Apple' "
                "to exclude results about the fruit."
            ),
        )
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]

        days = st.slider("Analysis Period (days)", 1, 30, 7)

        st.divider()

        # Actions
        st.header("Actions")

        if st.button("🔍 Scrape & Analyze", type="primary", disabled=not brand):
            st.session_state.current_brand = brand
            mentions = scrape_mentions(brand, keyword_list)
            analyzed = analyze_sentiment(brand)
            backlog = max(0, analyzed - len(mentions))
            st.session_state["last_scrape_result"] = (len(mentions), analyzed, backlog)
            st.rerun()

        if "last_scrape_result" in st.session_state:
            new_count, analyzed, backlog = st.session_state.pop("last_scrape_result")
            if analyzed == 0 and new_count == 0:
                st.warning("No new mentions found. Sources may be rate-limiting. Try again in a moment.")
            elif backlog > 0:
                st.success(
                    f"Analyzed {analyzed} mentions "
                    f"({new_count} new + {backlog} previously unanalyzed)."
                )
            else:
                st.success(f"Added and analyzed {new_count} new mentions.")

        if st.button("🔔 Check Alerts", disabled=not brand):
            st.session_state.current_brand = brand
            alerts = st.session_state.alert_system.run_all_checks(brand)
            if alerts:
                st.session_state.alert_system.save_alerts(brand, alerts)
                st.warning(f"Generated {len(alerts)} new alerts!")
            else:
                st.success("No new alerts")


    # Main content
    if not brand:
        st.info("👈 Enter a brand name in the sidebar to get started")
        st.markdown("""
        ### Getting Started

        **Try the demo instantly** — no setup required:
        run `py seed_demo_data.py` in your terminal, then enter **Tesla**, **Apple**, or **Nike** in the Brand Name field.

        ---

        **Step 1 — Set up your brand**
        - Enter a brand or company name in the sidebar (e.g. *Apple*, *Tesla*, *Nike*)
        - Optionally add comma-separated keywords to refine results (e.g. *iPhone, MacBook*)
        - Adjust the analysis period to control how many days of data are shown

        **Step 2 — Scrape & Analyze**
        - Click **🔍 Scrape & Analyze** to collect mentions and run sentiment analysis in one step
        - News is gathered from Google News, DuckDuckGo, and Reddit automatically
        - Sentiment analysis uses a local Ollama LLM — make sure Ollama is running with `llama3.1` pulled

        **Step 3 — Explore the dashboard**
        - **📈 Overview** — Sentiment breakdown, pie chart, source distribution, and trends over time
        - **📝 Mentions** — Browse and filter individual mentions with links to the original source
        - **🔔 Alerts** — Click *Check Alerts* to detect negative spikes or unusual volume
        - **📊 Summary** — Generate an AI-powered summary of your brand's perception
        """)
        return

    st.session_state.current_brand = brand

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Overview",
        "📝 Mentions",
        "🔔 Alerts",
        "📊 Summary"
    ])

    with tab1:
        display_sentiment_overview(brand, days)
        st.divider()

        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown("##### Sentiment Distribution")
            display_sentiment_chart(brand, days)
        with col2:
            st.markdown("##### Mentions by Source")
            display_source_distribution(brand, days)

        st.markdown("##### Sentiment Over Time")
        display_trend_chart(brand, days)

    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            source_filter = st.selectbox("Source", ["All", "news", "reddit"])
        with col2:
            sentiment_filter = st.selectbox("Sentiment", ["All", "Positive", "Negative", "Neutral"])

        display_mentions_table(brand, source_filter, sentiment_filter, days)

    with tab3:
        display_alerts(brand)

    with tab4:
        display_summary(brand, days)


if __name__ == "__main__":
    main()
