import datetime
from math import exp

from contract.schemas.architecture import BrowsingRecord

SCORE_PARAMETER_LAMBDA = 0.5


def score(browsing_history: list[BrowsingRecord]) -> float:
    def cost_function(access_record: BrowsingRecord) -> float:
        """
        density function of the exponential law
        too unexponential
        """
        if not access_record.timestamp:
            return 0.0
        time_elapsed = (
            datetime.datetime.now() - access_record.timestamp
        ).total_seconds()
        return SCORE_PARAMETER_LAMBDA * exp(-time_elapsed * SCORE_PARAMETER_LAMBDA)

    return sum([cost_function(access_record) for access_record in browsing_history])
