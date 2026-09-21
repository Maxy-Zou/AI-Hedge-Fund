"""Natural language summary formatters for financial data.

Converts structured financial data (with monetary values in cents) into
readable prose for LLM consumption. LLMs should never receive raw XBRL
JSON or tabular data -- these formatters produce the natural language
summaries that agents consume.
"""

from __future__ import annotations

from datetime import date


def _format_dollars(cents: int) -> str:
    """Format a value in cents to a human-readable dollar string.

    Uses appropriate scaling: $X.XB for billions, $X.XM for millions,
    $X,XXX for smaller values.

    Args:
        cents: Monetary value in cents (can be negative).

    Returns:
        Formatted dollar string (e.g., "$394.3B", "$12.5M", "$1,234").
    """
    negative = cents < 0
    abs_cents = abs(cents)
    dollars = abs_cents / 100

    prefix = "-$" if negative else "$"

    if dollars >= 1_000_000_000:
        return f"{prefix}{dollars / 1_000_000_000:.1f}B"
    if dollars >= 1_000_000:
        return f"{prefix}{dollars / 1_000_000:.1f}M"
    if dollars >= 1_000:
        return f"{prefix}{dollars:,.0f}"
    return f"{prefix}{dollars:,.2f}"


def _pct_change(current: float, prior: float) -> float:
    """Calculate percentage change from prior to current.

    Args:
        current: Current period value.
        prior: Prior period value.

    Returns:
        Percentage change (e.g., 5.2 for 5.2% increase).
    """
    if prior == 0:
        return 0.0
    return ((current - prior) / abs(prior)) * 100


def _format_pct(value: float) -> str:
    """Format a percentage to one decimal place.

    Args:
        value: Percentage value (e.g., 5.2 for 5.2%).

    Returns:
        Formatted string (e.g., "5.2%").
    """
    return f"{value:.1f}%"


def format_financial_summary(
    *,
    ticker: str,
    revenue_current_cents: int,
    revenue_prior_cents: int,
    net_income_current_cents: int,
    net_income_prior_cents: int,
    operating_margin_current: float,
    operating_margin_prior: float,
    fiscal_period: str,
    eps_current: float,
    eps_prior: float,
) -> str:
    """Format financial data into a natural language summary.

    All monetary values are in cents to avoid floating point errors.
    Output includes revenue, net income, operating margin, and EPS
    with YoY percentage changes.

    Args:
        ticker: Stock ticker symbol.
        revenue_current_cents: Current period revenue in cents.
        revenue_prior_cents: Prior period revenue in cents.
        net_income_current_cents: Current period net income in cents (negative = loss).
        net_income_prior_cents: Prior period net income in cents.
        operating_margin_current: Current operating margin as decimal (e.g., 0.305).
        operating_margin_prior: Prior operating margin as decimal.
        fiscal_period: Period label (e.g., "FY2025", "Q1 2024").
        eps_current: Current diluted EPS.
        eps_prior: Prior diluted EPS.

    Returns:
        Natural language paragraph describing financial performance.
    """
    rev_change = _pct_change(revenue_current_cents, revenue_prior_cents)
    rev_direction = "up" if rev_change >= 0 else "down"

    ni_change = _pct_change(net_income_current_cents, net_income_prior_cents)

    eps_change = _pct_change(eps_current, eps_prior)
    eps_direction = "up" if eps_change >= 0 else "down"

    margin_current_pct = operating_margin_current * 100
    margin_prior_pct = operating_margin_prior * 100

    # Build net income description
    if net_income_current_cents < 0:
        ni_str = _format_dollars(net_income_current_cents)
        ni_desc = f"Net loss was {ni_str}"
        if net_income_prior_cents < 0:
            improvement = abs(net_income_current_cents) < abs(net_income_prior_cents)
            qualifier = "narrowing" if improvement else "widening"
            ni_desc += f" ({qualifier} from {_format_dollars(net_income_prior_cents)} YoY)"
        else:
            ni_desc += f" (vs net income of {_format_dollars(net_income_prior_cents)} YoY)"
    else:
        ni_direction = "up" if ni_change >= 0 else "down"
        ni_desc = (
            f"Net income was {_format_dollars(net_income_current_cents)} "
            f"({ni_direction} {_format_pct(abs(ni_change))} YoY)"
        )

    return (
        f"{ticker} {fiscal_period}: "
        f"Revenue was {_format_dollars(revenue_current_cents)} "
        f"({rev_direction} {_format_pct(abs(rev_change))} YoY). "
        f"{ni_desc}. "
        f"Operating margin was {_format_pct(margin_current_pct)} "
        f"(vs {_format_pct(margin_prior_pct)} prior year). "
        f"Diluted EPS was ${eps_current:.2f} "
        f"({eps_direction} {_format_pct(abs(eps_change))} YoY)."
    )


def format_price_summary(
    *,
    ticker: str,
    current_price_cents: int,
    period_return_pct: float,
    annualized_volatility_pct: float,
    high_52w_cents: int,
    low_52w_cents: int,
    avg_volume: int,
    as_of_date: date,
) -> str:
    """Format price data into a natural language summary.

    Args:
        ticker: Stock ticker symbol.
        current_price_cents: Current price in cents.
        period_return_pct: Period return percentage.
        annualized_volatility_pct: Annualized volatility percentage.
        high_52w_cents: 52-week high in cents.
        low_52w_cents: 52-week low in cents.
        avg_volume: Average daily volume.
        as_of_date: Date of the data.

    Returns:
        Natural language paragraph describing price action.
    """
    price = current_price_cents / 100
    high = high_52w_cents / 100
    low = low_52w_cents / 100
    pct_from_high = ((price - high) / high) * 100 if high > 0 else 0.0

    return (
        f"{ticker} as of {as_of_date.isoformat()}: "
        f"Trading at ${price:,.2f} with a period return of {_format_pct(period_return_pct)}. "
        f"Annualized volatility is {_format_pct(annualized_volatility_pct)}. "
        f"52-week range: ${low:,.2f} - ${high:,.2f} "
        f"({_format_pct(abs(pct_from_high))} below 52-week high). "
        f"Average daily volume: {avg_volume:,}."
    )


def format_insider_summary(
    *,
    ticker: str,
    clusters: list[dict],
    as_of_date: date,
) -> str:
    """Format insider trade cluster data into a natural language summary.

    Args:
        ticker: Stock ticker symbol.
        clusters: List of cluster dicts with keys: insiders (list[str]),
            total_shares (int), total_value_cents (int), start_date, end_date.
        as_of_date: Date of the data.

    Returns:
        Natural language paragraph describing insider activity, or
        "No significant insider activity" if no clusters.
    """
    if not clusters:
        return f"{ticker}: No significant insider activity as of {as_of_date.isoformat()}."

    parts = [f"{ticker} insider activity as of {as_of_date.isoformat()}:"]
    for cluster in clusters:
        insiders = cluster["insiders"]
        n_insiders = len(insiders)
        shares = cluster["total_shares"]
        value = _format_dollars(cluster["total_value_cents"])
        start = cluster["start_date"]
        end = cluster["end_date"]

        names = ", ".join(insiders[:3])
        if n_insiders > 3:
            names += f" and {n_insiders - 3} others"

        parts.append(
            f" Cluster buy: {n_insiders} insiders ({names}) purchased "
            f"{shares:,} shares worth {value} between {start} and {end}."
        )

    return "".join(parts)


def format_news_summary(
    *,
    ticker: str,
    articles: list[dict],
    as_of_date: date,
) -> str:
    """Format news articles into a daily sentiment digest.

    Args:
        ticker: Stock ticker symbol.
        articles: List of article dicts with keys: headline (str),
            source (str), sentiment_score (float, -1 to 1), published_date.
        as_of_date: Date of the data.

    Returns:
        Natural language digest of news sentiment, or
        "No recent news" if no articles.
    """
    if not articles:
        return f"{ticker}: No recent news as of {as_of_date.isoformat()}."

    avg_sentiment = sum(a["sentiment_score"] for a in articles) / len(articles)
    sentiment_label = (
        "positive" if avg_sentiment > 0.2 else "negative" if avg_sentiment < -0.2 else "neutral"
    )

    headlines = []
    for article in articles[:5]:
        source = article["source"]
        headline = article["headline"]
        score = article["sentiment_score"]
        tone = "positive" if score > 0.2 else "negative" if score < -0.2 else "neutral"
        headlines.append(f'  - "{headline}" ({source}, {tone})')

    headline_text = "\n".join(headlines)

    return (
        f"{ticker} news digest as of {as_of_date.isoformat()} "
        f"({len(articles)} articles, overall sentiment: {sentiment_label}):\n"
        f"{headline_text}"
    )


def format_macro_summary(
    *,
    fed_funds_rate: float,
    cpi_yoy_pct: float,
    gdp_growth_pct: float,
    yield_spread: float,
    treasury_10y: float,
    as_of_date: date,
) -> str:
    """Format macro indicators into a natural language summary.

    Args:
        fed_funds_rate: Federal funds rate percentage.
        cpi_yoy_pct: CPI year-over-year percentage.
        gdp_growth_pct: GDP growth percentage.
        yield_spread: 10Y-2Y yield spread in percentage points.
        treasury_10y: 10-year Treasury yield percentage.
        as_of_date: Date of the data.

    Returns:
        Natural language paragraph describing the macro environment.
    """
    curve_desc = "inverted" if yield_spread < 0 else "normal"

    return (
        f"Macro environment as of {as_of_date.isoformat()}: "
        f"Federal funds rate at {_format_pct(fed_funds_rate)}. "
        f"Inflation (CPI YoY) at {_format_pct(cpi_yoy_pct)}. "
        f"GDP growth at {_format_pct(gdp_growth_pct)}. "
        f"10-year Treasury yield at {_format_pct(treasury_10y)}. "
        f"Yield curve (10Y-2Y spread): {yield_spread:+.2f}pp ({curve_desc})."
    )
