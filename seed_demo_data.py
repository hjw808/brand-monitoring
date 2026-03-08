#!/usr/bin/env python3
"""seed_demo_data.py — Populate the database with realistic demo data.

Run from the project root:
    python seed_demo_data.py                   # seed all 3 demo brands
    python seed_demo_data.py --brand Tesla     # seed only Tesla
    python seed_demo_data.py --clear           # wipe existing demo data first, then re-seed
    python seed_demo_data.py --db data/demo.db # use a custom DB path

After seeding, launch the dashboard and enter "Tesla", "Apple", or "Nike"
in the sidebar — all charts, the mentions table, and alerts will be populated.
"""

import argparse
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure `src` is importable when run from the project root
sys.path.insert(0, str(Path(__file__).parent))

from src.database import Database, Mention  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Reproducible randomness — same data every run
# ─────────────────────────────────────────────────────────────────────────────
_rng = random.Random(42)

# ─────────────────────────────────────────────────────────────────────────────
# Mention templates
# Tuple: (title, content, sentiment, base_score, source_type, author_hint)
#   sentiment:   "positive" | "negative" | "neutral"
#   base_score:  float  -1.0 … 1.0
#   source_type: "news" | "reddit"
#   author_hint: outlet name for news, "u/handle" for reddit
# ─────────────────────────────────────────────────────────────────────────────

MentionTemplate = Tuple[str, str, str, float, str, str]

TESLA_TEMPLATES: List[MentionTemplate] = [
    # ── Positive ──────────────────────────────────────────────────────────────
    (
        "Tesla Reports Record Q4 Deliveries, Beating Wall Street Estimates",
        "Tesla delivered 495,507 vehicles in Q4, smashing analyst estimates of 473,000. "
        "The milestone was driven by record demand in Europe and North America, with the "
        "Model Y retaining its position as the world's best-selling vehicle.",
        "positive", 0.87, "news", "Reuters",
    ),
    (
        "Full Self-Driving V13 Impresses Testers with Near-Zero Interventions",
        "Tesla's latest FSD update has stunned reviewers with a dramatically reduced "
        "intervention rate. Independent testers drove 500 miles across mixed urban and "
        "highway conditions with only two manual takeovers, calling it a 'watershed moment'.",
        "positive", 0.81, "news", "Electrek",
    ),
    (
        "Tesla Model Y Tops Global EV Sales Charts for Second Straight Year",
        "The Model Y has once again claimed the title of the world's best-selling EV, "
        "with 1.2 million units delivered globally. Analysts credit Tesla's Supercharger "
        "network and competitive pricing for the sustained dominance.",
        "positive", 0.78, "news", "Bloomberg",
    ),
    (
        "Tesla Supercharger Network Hits 70,000 Stalls — Competitors Scramble to Keep Up",
        "Tesla's charging network, now open to non-Tesla vehicles via CCS adapter, "
        "has expanded to 70,000 stalls across 15,000 locations worldwide, cementing "
        "its lead over rival networks and locking in charging revenue.",
        "positive", 0.74, "news", "CNBC",
    ),
    (
        "Tesla Energy Posts Record Quarter: Megapack Demand Outstrips Production Capacity",
        "Tesla's energy storage division generated $4.2B in Q3 revenue, with Megapack "
        "orders already booked through 2027. The segment is rapidly becoming a major "
        "profit driver for the company alongside vehicle sales.",
        "positive", 0.83, "news", "TechCrunch",
    ),
    (
        "Tesla Cybertruck Earns Top Safety Rating in NHTSA Tests",
        "The Cybertruck achieved a 5-star rating across all NHTSA crash-test categories, "
        "addressing one of the most common early criticisms of the vehicle's unconventional "
        "stainless steel design. Pre-orders remain at record levels.",
        "positive", 0.72, "news", "Electrek",
    ),
    (
        "50,000 miles in my Model 3 — it's still the best car I've ever owned",
        "I hit 50k miles last week and wanted to share my long-term experience. "
        "The car still drives like new, battery degradation is at just 4%, and the "
        "software keeps improving with every update. Cannot imagine going back to ICE.",
        "positive", 0.79, "reddit", "u/LongRangeEVFan",
    ),
    (
        "FSD drove me through downtown Seattle with zero interventions — I'm a convert",
        "I was a hardcore FSD skeptic until today. Took the most complex urban route "
        "I could design — construction zones, cyclists, jaywalkers — and it nailed it. "
        "This is genuinely impressive engineering. Subscribing immediately.",
        "positive", 0.85, "reddit", "u/TechSkepticNoMore",
    ),
    (
        "Tesla mobile service fixed my issue same-day — blown away by the experience",
        "Everyone talks about Tesla service being terrible but mine was the opposite. "
        "Booked a mobile appointment, tech arrived in 2 hours, fixed it on the spot. "
        "Sharing this because I think the negative stories get way more attention.",
        "positive", 0.62, "reddit", "u/ModelYOwner_PDX",
    ),
    (
        "The Supercharger network is Tesla's most underrated competitive advantage",
        "Just finished a 2,400-mile road trip in my Model S. Charged at 38 Supercharger "
        "stops, never waited more than 5 minutes. No other brand can offer this experience. "
        "Until someone matches it, Tesla wins on long-distance road trips by default.",
        "positive", 0.76, "reddit", "u/EVRoadTripper",
    ),
    (
        "Tesla Q3 Gross Margin Rebounds to 19.8%, Surpassing Analyst Expectations",
        "Tesla's automotive gross margin recovered to 19.8% in Q3 from a multi-year "
        "low, driven by cost reductions at Giga Texas and improved mix toward higher-margin "
        "configurations. Shares rose 8% in after-hours trading.",
        "positive", 0.80, "news", "Bloomberg",
    ),
    # ── Negative ──────────────────────────────────────────────────────────────
    (
        "Tesla Recalls 125,000 Vehicles Over Power Steering Warning Defect",
        "NHTSA has announced a recall of 125,000 Tesla Model 3 and Model Y vehicles "
        "over a software defect that can disable the power steering warning light. "
        "Tesla says an OTA fix is available but critics question the safety review process.",
        "negative", -0.72, "news", "Reuters",
    ),
    (
        "Elon Musk's Political Statements Dent Tesla Brand Appeal Among Key Demographics",
        "A new consumer study finds Tesla brand favorability has fallen 18 points among "
        "consumers aged 25–44 following Musk's public political commentary. Dealers report "
        "an uptick in buyers switching consideration to Rivian and BMW EVs.",
        "negative", -0.68, "news", "Bloomberg",
    ),
    (
        "BYD Overtakes Tesla in Global EV Sales for Third Consecutive Quarter",
        "Chinese automaker BYD has outsold Tesla globally for the third straight quarter, "
        "shipping 530,000 vehicles versus Tesla's 483,000. Analysts warn Tesla's dominance "
        "in Europe and the US may face growing pressure from BYD's expanding lineup.",
        "negative", -0.61, "news", "CNBC",
    ),
    (
        "Tesla Layoffs: 10% Workforce Reduction Raises Concerns Over Future Product Plans",
        "Tesla confirmed it is cutting approximately 14,000 employees globally, citing "
        "the need to reduce costs. The cuts hit the Supercharger and new product teams "
        "hardest, raising questions about the timeline for the $25K affordable model.",
        "negative", -0.75, "news", "TechCrunch",
    ),
    (
        "A software update bricked my touchscreen for 3 days — completely unacceptable",
        "Had a major OTA update push last night and now the entire center console is a "
        "black screen. Tesla support told me to book service — the earliest slot is 3 weeks "
        "away. For a $60K car this level of reliability is embarrassing.",
        "negative", -0.82, "reddit", "u/AngryModelSOwner",
    ),
    (
        "Tesla's constant price cuts are destroying resale values — early owners deserve better",
        "Bought my Model 3 LR for $52K and it's now being sold new for $38K. "
        "My car has lost nearly 40% of its value in 18 months due to Tesla's pricing strategy. "
        "There's no loyalty reward for early adopters who took the risk.",
        "negative", -0.71, "reddit", "u/EarlyAdopterRemorse",
    ),
    # ── Neutral ───────────────────────────────────────────────────────────────
    (
        "Tesla Q4 Earnings Preview: Wall Street Eyes Margin Recovery and Affordable Model",
        "Ahead of Tesla's upcoming earnings call, analysts are focused on gross margin "
        "trends, Cybertruck ramp updates, and any guidance on the affordable model launch. "
        "Consensus EPS estimate sits at $0.72, compared to $1.19 a year ago.",
        "neutral", 0.05, "news", "Bloomberg",
    ),
    (
        "Tesla vs. BYD: An Objective Look at Global EV Market Share in 2026",
        "As both companies vie for global EV leadership, a breakdown of their respective "
        "strengths reveals Tesla's dominance in the premium segment while BYD leads in "
        "volume. The competition is reshaping the global automotive landscape.",
        "neutral", -0.03, "news", "Reuters",
    ),
    (
        "Giga Texas Reaches 250,000 Annual Production Capacity — Expansion Planned",
        "Tesla's Austin factory has officially reached its 250,000-unit annual capacity "
        "milestone. Expansion plans for additional production lines are reportedly underway "
        "though no official announcement has been made.",
        "neutral", 0.08, "news", "Electrek",
    ),
    (
        "Anyone notice the HW4 cameras have a significantly wider field of view?",
        "Just picked up a new Model Y with Hardware 4 and the dashcam footage looks "
        "dramatically better than my old HW3 car. Has anyone done a proper side-by-side? "
        "Curious how much this actually helps FSD performance.",
        "neutral", 0.12, "reddit", "u/HardwareNerd42",
    ),
    (
        "Considering switching from Model 3 to BMW i4 — genuinely torn",
        "I love my Tesla but after driving the i4 at a dealer I'm genuinely curious. "
        "The interior quality feels leagues ahead, but the charging network isn't comparable. "
        "Anyone made this switch? What do you miss most about the Tesla?",
        "neutral", -0.05, "reddit", "u/UndecidedBuyer",
    ),
]

APPLE_TEMPLATES: List[MentionTemplate] = [
    # ── Positive ──────────────────────────────────────────────────────────────
    (
        "Apple Reports Strongest Services Quarter Ever with $28B in Revenue",
        "Apple's services segment set a new all-time record this quarter with $28B in "
        "revenue, driven by App Store, Apple TV+, and iCloud subscriptions. The segment "
        "now contributes 26% of total company revenue, up from 19% two years ago.",
        "positive", 0.84, "news", "Bloomberg",
    ),
    (
        "iPhone 17 Pre-Orders Shatter Records in 24-Hour Launch Window",
        "Apple's iPhone 17 generated the highest-ever 24-hour pre-order volume, with an "
        "estimated 12 million units reserved. The titanium design and improved camera "
        "system are cited as the top purchase drivers in consumer surveys.",
        "positive", 0.88, "news", "Reuters",
    ),
    (
        "Apple Vision Pro Enterprise Adoption Accelerates Across Healthcare and Aviation",
        "More than 2,000 enterprise customers have deployed Apple Vision Pro in production "
        "environments, with healthcare and aviation leading adoption. Apple's enterprise "
        "sales team is now its fastest-growing division.",
        "positive", 0.76, "news", "TechCrunch",
    ),
    (
        "Apple Intelligence Is Driving the Biggest iPhone Upgrade Cycle Since the iPhone X",
        "Analysts at Morgan Stanley estimate Apple Intelligence is motivating 43% of users "
        "on 3-year-old devices to upgrade — a rate not seen since the iPhone X. "
        "The AI-powered writing and summarization features are resonating most.",
        "positive", 0.81, "news", "CNBC",
    ),
    (
        "M4 MacBook Pro Benchmarks Are Historically Wide — Industry Stunned",
        "Apple's M4 chip in the MacBook Pro has produced single-core scores beating "
        "competing laptops costing nearly twice as much. The performance-per-watt "
        "advantage is described as 'the widest it has ever been' by independent reviewers.",
        "positive", 0.86, "news", "The Verge",
    ),
    (
        "Apple Market Cap Briefly Crosses $4 Trillion for the First Time in History",
        "Apple's market capitalization touched $4 trillion on Thursday, making it "
        "the first company to achieve that milestone. Shares are up 34% year-to-date "
        "on strong earnings and iPhone demand exceeding guidance.",
        "positive", 0.79, "news", "Bloomberg",
    ),
    (
        "Switched from Android after 10 years — the ecosystem is everything they say",
        "Finally made the jump after using Android since 2013. AirDrop, Handoff, "
        "iMessage, AirPods together — everything just works in a way I didn't expect. "
        "The integration is completely real and it's remarkable.",
        "positive", 0.80, "reddit", "u/AndroidToAppleConvert",
    ),
    (
        "Apple Watch caught my AFib before my cardiologist did — genuinely saved my life",
        "Three weeks ago my Apple Watch alerted me to an irregular heartbeat. "
        "Went to the doctor, confirmed atrial fibrillation. Now on medication and great. "
        "I cannot overstate how important this device has been to my health.",
        "positive", 0.94, "reddit", "u/GratefulHearted",
    ),
    (
        "AirPods Pro 3 are the best earbuds money can buy — it's not close",
        "Tested AirPods Pro 3 against Sony WF-1000XM6 and Bose QC45 earbuds. "
        "The noise cancellation and Transparency mode are both class-leading, and "
        "Personalized Spatial Audio is genuinely mind-blowing. Apple wins clearly.",
        "positive", 0.77, "reddit", "u/AudioReviewGuy",
    ),
    (
        "Apple's Customer Satisfaction Score Reaches 10-Year High in ACSI Survey",
        "The American Customer Satisfaction Index has awarded Apple its highest-ever "
        "score of 84 out of 100, up 3 points from last year. Apple leads the smartphone "
        "category by 9 points over its nearest competitor.",
        "positive", 0.73, "news", "9to5Mac",
    ),
    # ── Negative ──────────────────────────────────────────────────────────────
    (
        "EU Hits Apple with €2.1B Fine in App Store Antitrust Ruling",
        "European regulators imposed a record €2.1 billion fine on Apple following "
        "findings that the company abused its dominant market position through App Store "
        "policies. Apple says it will appeal the decision but faces further scrutiny.",
        "negative", -0.76, "news", "Reuters",
    ),
    (
        "Apple iPhone Sales in China Fall 18% as Huawei Reclaims Premium Market Share",
        "New data from IDC shows Apple's China iPhone market share dropped to 14.2%, "
        "down from 17.3% a year ago, as Huawei's Mate series continues its resurgence. "
        "Analysts warn the China headwinds could persist through 2027.",
        "negative", -0.69, "news", "Bloomberg",
    ),
    (
        "App Store Commission Fight Escalates as Spotify and Epic Renew Regulatory Push",
        "A coalition of app developers including Spotify and Epic Games filed new "
        "complaints with US and EU regulators challenging Apple's 27% commission structure. "
        "The case could force a fundamental restructuring of App Store economics.",
        "negative", -0.64, "news", "TechCrunch",
    ),
    (
        "iCloud pricing is insulting compared to Google One and Microsoft 365",
        "Apple charges $2.99/month for 200GB of iCloud storage. Google gives 100GB "
        "for $1.99. Microsoft bundles 1TB with Office 365 for $9.99/month. "
        "For a company with $400B in cash, this is embarrassing pricing.",
        "negative", -0.58, "reddit", "u/CloudStorageRant",
    ),
    (
        "My MacBook Air M3 throttles so aggressively it becomes unusable for video work",
        "I do video editing on my M3 MacBook Air and it throttles in sustained workloads "
        "to the point of being unusable. Apple should add a fan at this price point. "
        "Paying $400 more for the Pro just for adequate thermal management is absurd.",
        "negative", -0.62, "reddit", "u/OverheatedEditor",
    ),
    (
        "Apple's repairability stance remains deeply frustrating — paid $580 for a screen",
        "Just paid $580 for an out-of-warranty display repair that a third-party shop "
        "quoted at $120 with a genuine panel. Apple's parts pairing and repair restrictions "
        "are an anti-consumer practice that right-to-repair legislation hasn't fixed.",
        "negative", -0.71, "reddit", "u/RightToRepairAdvocate",
    ),
    # ── Neutral ───────────────────────────────────────────────────────────────
    (
        "WWDC 2026 Preview: What to Expect from iOS 20 and macOS Sequoia 2",
        "Apple's Worldwide Developers Conference kicks off next month, with industry "
        "insiders predicting major Apple Intelligence updates, a redesigned home screen, "
        "and new APIs for Vision Pro. Here's everything currently known.",
        "neutral", 0.06, "news", "9to5Mac",
    ),
    (
        "Apple Accelerates India Manufacturing as Foxconn Expands Chennai Facility",
        "Apple now produces approximately 14% of global iPhone volume in India, up from "
        "7% two years ago. The shift is part of Apple's supply chain risk diversification "
        "strategy following the pandemic-era disruptions.",
        "neutral", 0.04, "news", "Reuters",
    ),
    (
        "Apple vs Google: Which AI Assistant Is Actually Better in 2026?",
        "Six months after Apple Intelligence launched, I compared Siri and Gemini "
        "across 50 real-world tasks. The results were more nuanced than I expected, "
        "with each excelling in different categories. Full breakdown in comments.",
        "neutral", -0.02, "reddit", "u/AIAssistantReview",
    ),
    (
        "What's everyone's experience with the new MacBook Air design change?",
        "Considering upgrading from my 2022 M2 MacBook Air to the new design. "
        "Is the additional screen real estate practically meaningful in daily use? "
        "Does the thinner bezel make it feel noticeably more modern?",
        "neutral", 0.03, "reddit", "u/MacUpgradeDebate",
    ),
]

NIKE_TEMPLATES: List[MentionTemplate] = [
    # ── Positive ──────────────────────────────────────────────────────────────
    (
        "Nike Reports 14% Revenue Growth Driven by Direct-to-Consumer Acceleration",
        "Nike's fiscal Q3 results beat expectations with $14.2B in revenue, up 14% YoY. "
        "The direct-to-consumer strategy is showing results, with Nike.com and the "
        "Nike app growing 24% as the company reduces reliance on wholesale partners.",
        "positive", 0.82, "news", "Reuters",
    ),
    (
        "Nike Vaporfly 4 Worn by Top Finishers at Six World Marathon Majors",
        "Nike's latest marathon racing shoe was worn by the top finishers at six of "
        "the last eight World Marathon Major events. The carbon plate technology "
        "continues to set the standard for elite performance footwear.",
        "positive", 0.79, "news", "Runner's World",
    ),
    (
        "Nike and LeBron James Launch $100M Community Basketball Initiative",
        "Nike and LeBron James' foundation announced a $100 million, 10-year commitment "
        "to build and renovate basketball facilities in underserved communities. "
        "The initiative will reach an estimated 2.5 million young athletes.",
        "positive", 0.86, "news", "ESPN",
    ),
    (
        "Nike SNKRS App Sets Single-Day Sales Record During Jordan Collaboration Drop",
        "Nike's exclusive sneaker app generated $340M in a single day during a limited "
        "Jordan collaboration drop, breaking all previous records. The SNKRS platform "
        "now has over 100M registered users globally.",
        "positive", 0.74, "news", "Bloomberg",
    ),
    (
        "Nike Q3 DTC Gross Margin Expands 240 Basis Points — Analysts Cheer",
        "Nike's decision to shift away from wholesale has paid off in margin terms, "
        "with direct-to-consumer gross margin expanding 240bps year-over-year. "
        "The company reiterated its FY27 margin recovery targets.",
        "positive", 0.71, "news", "CNBC",
    ),
    (
        "Just finished my first marathon in the Nike Vaporfly — it genuinely changed my race",
        "I PR'd by 8 minutes wearing the Vaporfly 4. I know the carbon plate debate "
        "is ongoing but I don't care — the difference in energy return is palpable. "
        "Best running investment I've ever made, absolutely no question.",
        "positive", 0.84, "reddit", "u/MarathonFirstTimer",
    ),
    (
        "Nike By You custom shoes arrived — quality exceeded every expectation I had",
        "Spent way too long designing a custom Dunk Low on Nike By You. "
        "The final product is perfect — materials are premium, color accuracy is spot-on, "
        "and the fit is identical to the standard retail version. Worth every penny.",
        "positive", 0.71, "reddit", "u/SneakerCustomizer",
    ),
    (
        "Nike Adapt auto-lacing is the future and it's available right now",
        "Just spent a week in the Nike Adapt BB 3.0 and I'm genuinely impressed. "
        "The self-lacing works flawlessly, the fit customization via app is real and "
        "useful, and the battery holds all week. This is what shoes should be.",
        "positive", 0.68, "reddit", "u/BasketballTechNerd",
    ),
    # ── Negative ──────────────────────────────────────────────────────────────
    (
        "Nike Faces $3B Inventory Overhang as Wholesale Partners Push Back on Orders",
        "Nike's aggressive production ramp has left major retail partners sitting on "
        "excess inventory, forcing widespread discounting that erodes brand premium. "
        "Analysts warn the clearance cycle could persist through Q2.",
        "negative", -0.71, "news", "Bloomberg",
    ),
    (
        "Labor Activists Renew Pressure on Nike Over Vietnam Factory Conditions",
        "A new report by the Worker Rights Consortium documents excessive overtime and "
        "below-minimum wages at two Nike contract factories in Vietnam. "
        "Nike says it takes the findings 'very seriously' and has launched an investigation.",
        "negative", -0.78, "news", "Reuters",
    ),
    (
        "Adidas Samba and New Balance Are Eating Into Nike's Lifestyle Market Share",
        "In a reversal that would have seemed impossible three years ago, Nike's lifestyle "
        "category has ceded significant ground. Analysts say Nike's fashion-forward designs "
        "missed the current retro sneaker trend that competitors capitalized on.",
        "negative", -0.63, "news", "Business of Fashion",
    ),
    (
        "Nike China Sales Decline 11% Amid Domestic Brand Competition",
        "Li-Ning and Anta continue to gain ground in China, with Nike's market share "
        "dropping to 12.4% — its lowest level since 2017. National pride campaigns "
        "by domestic brands are proving highly effective with younger consumers.",
        "negative", -0.67, "news", "CNBC",
    ),
    (
        "Nike shoes fell apart at 180 miles — quality control has clearly declined",
        "Bought a pair of Pegasus 41 and the upper started delaminating at 180 miles. "
        "I've been running in Nike for 10 years and this has never happened before. "
        "Quality control feels noticeably worse than 3 years ago. Very disappointed.",
        "negative", -0.73, "reddit", "u/DisappointedRunner",
    ),
    (
        "The SNKRS app is still dominated by bots — Nike has clearly given up fixing it",
        "Every limited release I've entered for in the last year has been an L. "
        "Meanwhile resellers are immediately listing on StockX within minutes of the drop. "
        "Regular customers have basically stopped trying. This ruins the brand experience.",
        "negative", -0.66, "reddit", "u/SneakerBotVictim",
    ),
    # ── Neutral ───────────────────────────────────────────────────────────────
    (
        "Nike Q4 Earnings Preview: Analysts Focus on DTC Margins and China Recovery",
        "Analysts are looking for improvement in Nike's direct-to-consumer gross margin "
        "and any signs of China business stabilization. Consensus revenue estimate is "
        "$12.8B with EPS of $0.84, up modestly from the year-ago period.",
        "neutral", 0.04, "news", "Bloomberg",
    ),
    (
        "Nike's 2026 Sustainability Report: Progress Toward Zero Carbon — But Critics Remain",
        "Nike released its annual sustainability report showing a 12% reduction in Scope 1 "
        "and 2 emissions year-over-year. Critics argue Scope 3 supply chain emissions, "
        "which represent 90% of total footprint, remain largely unaddressed.",
        "neutral", -0.03, "news", "Reuters",
    ),
    (
        "Breaking Down Nike's Royalty Deal with the Jordan Brand — The Numbers Are Staggering",
        "The Jordan Brand generates over $7B annually and Michael Jordan receives a 5% "
        "royalty — roughly $350M per year for a deal signed in 1984. "
        "As Jordan Brand grows, this arrangement becomes one of sports' best contracts.",
        "neutral", 0.05, "news", "Forbes",
    ),
    (
        "Nike vs Adidas vs New Balance for marathon training — honest comparison needed",
        "Starting marathon training in April and deciding between the Nike Pegasus 42, "
        "Adidas Ultraboost 24, and New Balance 1080v14 for daily training miles. "
        "Has anyone compared all three? Especially interested in sub-3:30 runners.",
        "neutral", 0.07, "reddit", "u/MarathonTrainingNewbie",
    ),
    (
        "What running shoes is everyone using for spring racing season?",
        "Curious what everyone has laced up for their spring races. I'm debating sticking "
        "with my Vaporfly 3 for my half-marathon or trying the new Adidas Adizero Pro 4. "
        "Has anyone raced in both? How do they compare at threshold pace?",
        "neutral", 0.02, "reddit", "u/SpringRacer2026",
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# Brand configuration
# ─────────────────────────────────────────────────────────────────────────────
BrandConfig = Dict

BRANDS: Dict[str, BrandConfig] = {
    "Tesla": {
        "templates": TESLA_TEMPLATES,
        "target": 72,
        "reddit_subs": ["teslamotors", "electricvehicles", "stocks", "investing"],
        "news_outlets": ["Reuters", "Bloomberg", "Electrek", "CNBC", "TechCrunch"],
        "alert": {
            "type": "negative_spike",
            "severity": "medium",
            "message": (
                "Negative sentiment spike detected for Tesla\n\n"
                "Details: {'recent_negative_ratio': 38.5, "
                "'historical_negative_ratio': 22.1, 'increase_percent': 74.2, "
                "'recent_mentions': 13, 'recent_negative': 5}\n\n"
                "Primary drivers appear to be recall coverage and resale-value "
                "discussion on Reddit."
            ),
        },
    },
    "Apple": {
        "templates": APPLE_TEMPLATES,
        "target": 62,
        "reddit_subs": ["apple", "iphone", "technology", "MacOS"],
        "news_outlets": ["Reuters", "Bloomberg", "9to5Mac", "TechCrunch", "The Verge"],
        "alert": {
            "type": "volume_spike",
            "severity": "low",
            "message": (
                "Unusual mention volume detected for Apple\n\n"
                "Details: {'recent_count': 31, 'average_daily': 12.4, "
                "'increase_percent': 150.0}\n\n"
                "Spike is likely driven by WWDC preview coverage cycle."
            ),
        },
    },
    "Nike": {
        "templates": NIKE_TEMPLATES,
        "target": 52,
        "reddit_subs": ["sneakers", "running", "investing", "frugalmalefashion"],
        "news_outlets": ["Reuters", "Bloomberg", "ESPN", "Business of Fashion", "CNBC"],
        "alert": None,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _slug(text: str, max_len: int = 40) -> str:
    """Convert text to a URL-safe slug."""
    s = text[:max_len].lower()
    return "".join(c if c.isalnum() else "-" for c in s).strip("-")


def _make_url(brand: str, source: str, idx: int, title: str, sub: str = "") -> str:
    """Build a unique, realistic-looking URL for a mention."""
    s = _slug(title)
    if source == "reddit":
        return f"https://www.reddit.com/r/{sub}/comments/{idx:06x}/{s}/"
    domain = brand.lower().replace(" ", "")
    return f"https://demo-news.{domain}.io/{idx:06x}/{s}"


def _random_date(days_back_max: int, days_back_min: int = 0) -> datetime:
    """Return a random datetime within the specified window from now."""
    hours_back = _rng.randint(days_back_min * 24, days_back_max * 24)
    base = datetime.now() - timedelta(hours=hours_back)
    return base.replace(
        hour=_rng.randint(6, 23),
        minute=_rng.randint(0, 59),
        second=_rng.randint(0, 59),
        microsecond=0,
    )


def _pick(pool: list, n: int) -> list:
    """Draw n items from pool, cycling if necessary."""
    out = []
    while len(out) < n:
        out.extend(pool[: n - len(out)])
    return out[:n]


# ─────────────────────────────────────────────────────────────────────────────
# Core seeding function
# ─────────────────────────────────────────────────────────────────────────────

def seed_brand(db: Database, brand: str, config: BrandConfig, url_counter: list) -> int:
    """Insert demo mentions and alerts for one brand.

    Args:
        db:          Initialised Database instance.
        brand:       Brand name string.
        config:      Entry from BRANDS dict.
        url_counter: Single-element list used as a mutable integer counter so
                     every URL remains unique across all brands.

    Returns:
        Number of mentions successfully inserted.
    """
    templates = config["templates"]
    target = config["target"]
    subs = config["reddit_subs"]

    # Split templates by sentiment
    pos_t = [t for t in templates if t[2] == "positive"]
    neg_t = [t for t in templates if t[2] == "negative"]
    neu_t = [t for t in templates if t[2] == "neutral"]

    # Build target mention list (~50 % positive, 25 % negative, 25 % neutral)
    pos_n = int(target * 0.50)
    neg_n = int(target * 0.26)
    neu_n = target - pos_n - neg_n

    chosen = _pick(pos_t, pos_n) + _pick(neg_t, neg_n) + _pick(neu_t, neu_n)
    _rng.shuffle(chosen)

    # 60 % of mentions land in the last 7 days so charts are full on default view
    recent_cutoff = int(len(chosen) * 0.60)

    inserted = 0
    for i, (title, content, sentiment, base_score, source_type, author_hint) in enumerate(chosen):
        # Add a small random jitter to the score for variety
        score = round(max(-1.0, min(1.0, base_score + _rng.uniform(-0.06, 0.06))), 3)

        if i < recent_cutoff:
            pub_date = _random_date(days_back_max=7, days_back_min=0)
        else:
            pub_date = _random_date(days_back_max=30, days_back_min=8)

        scrape_date = pub_date + timedelta(minutes=_rng.randint(5, 120))

        sub = _rng.choice(subs) if source_type == "reddit" else ""

        url_counter[0] += 1
        url = _make_url(brand, source_type, url_counter[0], title, sub)

        reasoning_map = {
            "positive": (
                f"The content highlights positive developments, strong performance, "
                f"or favourable user sentiment toward {brand}."
            ),
            "negative": (
                f"The content focuses on challenges, criticism, or unfavourable events "
                f"that reflect negatively on {brand}."
            ),
            "neutral": (
                f"The content is factual and balanced with no strong directional "
                f"sentiment toward {brand}."
            ),
        }

        mention = Mention(
            id=None,
            brand=brand,
            source=source_type,
            title=title,
            content=content,
            url=url,
            author=author_hint,
            published_at=pub_date,
            scraped_at=scrape_date,
            sentiment=sentiment,
            sentiment_score=score,
            sentiment_reasoning=reasoning_map[sentiment],
        )

        if db.add_mention(mention) is not None:
            inserted += 1

    # Seed alert if configured
    if config.get("alert"):
        a = config["alert"]
        db.add_alert(
            brand=brand,
            alert_type=a["type"],
            severity=a["severity"],
            message=a["message"],
        )
        print(f"  [ALERT] Seeded: [{a['severity'].upper()}] {a['type']}")

    return inserted


def clear_brands(db_path: str, brands: List[str]) -> None:
    """Delete all rows for the given brands from every table."""
    placeholders = ",".join("?" * len(brands))
    conn = sqlite3.connect(db_path)
    for table in ("mentions", "alerts", "summaries"):
        conn.execute(f"DELETE FROM {table} WHERE brand IN ({placeholders})", brands)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the Brand Monitor database with realistic demo data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python seed_demo_data.py\n"
            "  python seed_demo_data.py --brand Apple\n"
            "  python seed_demo_data.py --clear\n"
            "  python seed_demo_data.py --db data/demo.db\n"
        ),
    )
    parser.add_argument(
        "--brand",
        metavar="NAME",
        help=f"Seed only this brand. Choices: {', '.join(BRANDS)}",
    )
    parser.add_argument(
        "--db",
        default="data/brand_monitoring.db",
        metavar="PATH",
        help="Path to the SQLite database file (default: data/brand_monitoring.db)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing demo data for the target brand(s) before seeding",
    )
    args = parser.parse_args()

    # Validate --brand
    if args.brand and args.brand not in BRANDS:
        print(f"Error: unknown brand '{args.brand}'. "
              f"Valid options are: {', '.join(BRANDS)}")
        sys.exit(1)

    brands_to_seed = {args.brand: BRANDS[args.brand]} if args.brand else BRANDS

    db = Database(db_path=args.db)

    if args.clear:
        targets = list(brands_to_seed.keys())
        print(f"[CLEAR] Clearing existing data for: {', '.join(targets)} ...")
        clear_brands(args.db, targets)

    print(f"\nSeeding demo data -> {args.db}\n")

    url_counter = [0]  # mutable counter shared across brands
    total = 0

    for brand, config in brands_to_seed.items():
        print(f"[{brand}]  (target {config['target']} mentions)")
        n = seed_brand(db, brand, config, url_counter)
        total += n
        print(f"  OK  {n} mentions inserted\n")

    print(f"Done -- {total} total mentions seeded across {len(brands_to_seed)} brand(s).")
    print()
    print("Launch the dashboard:")
    print("  streamlit run app.py")
    print()
    print("Then enter any of the following brands in the sidebar:")
    for brand in brands_to_seed:
        print(f"  - {brand}")
    print()
    if args.brand:
        print("Tip: run without --brand to seed all three demo brands at once.")


if __name__ == "__main__":
    main()
