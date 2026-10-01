"""Business failures that cannot advance by replaying the same checkpoints."""


def report_review_exhausted(error: str | None) -> bool:
    return bool(error and "report narrative did not pass independent review after three drafts"
                in error.casefold())
