import datetime
from math import exp
from typing import Any, Dict, List

SCORE_PARAMETER_LAMBDA = 0.5


def score(browsing_history: List[Dict[str, Any]]) -> float:
    def cost_function(access_record: Dict[str, Any]) -> float:
        """
        density function of the exponential law
        too unexponential
        """
        time_elapsed = (
            datetime.datetime.now()
            - datetime.datetime.fromisoformat(access_record["timestamp"])
        ).total_seconds()
        return SCORE_PARAMETER_LAMBDA * exp(-time_elapsed * SCORE_PARAMETER_LAMBDA)

    return sum([cost_function(access_record) for access_record in browsing_history])
