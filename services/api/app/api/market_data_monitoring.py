
from fastapi import APIRouter, HTTPException, Query, Request

from app.market_data.services.feed_health_service import (
    FeedHealthTracker,
)

router = APIRouter(tags=["market-data"])


def serialize_feed(feed) -> dict:
    """Convert a feed-health record into an API response."""

    return {
        "provider": feed.provider,
        "symbol": feed.symbol,
        "timeframe": feed.timeframe,
        "connected": feed.connected,
        "data_status": feed.data_status.value,
        "last_message_at": (
            feed.last_message_at.isoformat()
            if feed.last_message_at
            else None
        ),
        "last_candle_at": (
            feed.last_candle_at.isoformat()
            if feed.last_candle_at
            else None
        ),
        "last_completed_candle_at": (
            feed.last_completed_candle_at.isoformat()
            if feed.last_completed_candle_at
            else None
        ),
        "message": feed.message,
    }


def get_tracker(request: Request) -> FeedHealthTracker:
    """Retrieve the application-wide feed-health tracker."""

    tracker: FeedHealthTracker | None = getattr(
        request.app.state,
        "feed_health_tracker",
        None,
    )

    if tracker is None:
        raise HTTPException(
            status_code=503,
            detail="Feed-health monitoring is not initialized.",
        )

    return tracker


@router.get("/market-data/feeds")
def get_market_data_feeds(request: Request) -> dict:
    """Return the current health of all tracked market-data feeds."""

    tracker = get_tracker(request)
    feeds = tracker.evaluate_all()

    return {
        "count": len(feeds),
        "feeds": [
            serialize_feed(feed)
            for feed in feeds
        ],
    }


@router.get("/market-data/feeds/{symbol}")
def get_market_data_feed_by_symbol(
    symbol: str,
    request: Request,
    provider: str | None = Query(default=None, min_length=1, max_length=50),
) -> dict:
    """Return health information for all tracked timeframes of a symbol."""

    normalized_symbol = symbol.strip().upper()

    if not normalized_symbol:
        raise HTTPException(
            status_code=422,
            detail="Symbol cannot be empty.",
        )

    tracker = get_tracker(request)
    feeds = tracker.evaluate_all()

    matching_feeds = [
        feed
        for feed in feeds
        if (
            feed.symbol == normalized_symbol
            and (
                provider is None
                or feed.provider == provider.strip().lower()
            )
        )
    ]

    if not matching_feeds:
        raise HTTPException(
            status_code=404,
            detail=f"No tracked feed found for symbol '{normalized_symbol}'.",
        )

    return {
        "symbol": normalized_symbol,
        "provider": provider.strip().lower() if provider else None,
        "count": len(matching_feeds),
        "feeds": [
            serialize_feed(feed)
            for feed in matching_feeds
        ],
    }
