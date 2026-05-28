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


def herobrine_is_here(html) -> bool:
    """
    analyze page.html to check if we were spotted by herobrine
    automatically updates the attribute spotted
    """
    if (
        sum([1 for artifact in CLOUDFLARE_ARTIFACTS if artifact in html])
        >= THRESHOLD_ARTIFACTS_DETECTION
    ):
        return True
    return False
