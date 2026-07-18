import zendriver as uc

from scraper.core.schemas import BotSpottedError

THRESHOLD_ARTIFACTS_DETECTION = (
    2  # number of artifacts required to be considered spotted (inclusive)
)
CLOUDFLARE_ARTIFACTS = [
    "Cloudflare",
    "Just a moment...",
    "challenge-error-text",
    "/cdn-cgi/challenge-platform",
    "Why have I been blocked?",
    "You are unable to access",
]


async def check_cf_blocking_content(tab: uc.Tab) -> None:
    """
    analyze page.html to check if we were spotted by herobrine
    automatically updates the attribute spotted
    """
    html = await tab.get_content()
    if (
        sum([1 for artifact in CLOUDFLARE_ARTIFACTS if artifact in html])
        >= THRESHOLD_ARTIFACTS_DETECTION
    ):
        raise BotSpottedError(html)
