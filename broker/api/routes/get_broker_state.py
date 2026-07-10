import traceback
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from broker.api.common import get_broker
from broker.core.Broker import Broker
from broker.core.DatabaseHandler import DatabaseHandler
from broker.core.models.DatabaseHandler import RecordTarget

router = APIRouter()


@router.get(
    "/get_broker_state",
    description=(
        "There could be a race in between the collection, so the endpoint is supposed to deduplicate on `RecordTarget.uuid`. "
    ),
)
async def get_broker_state(broker: Broker = Depends(get_broker)) -> list[RecordTarget]:
    try:
        result: list[RecordTarget] = []
        for record in await DatabaseHandler.get_unscraped_targets():
            new_record = RecordTarget(
                id=record.id,
                url=record.url,
                antwortzeit=record.antwortzeit,
                created_at=record.created_at,
                tag=record.tag,
                flag_lazy_loading=record.flag_lazy_loading,
                is_running=False,
            )
            result.append(new_record)
        uuids_running_requests: list[UUID] = await broker.get_running_tasks()
        if uuids_running_requests:
            for record in await DatabaseHandler.get_targets_from_uuids(
                uuids_running_requests
            ):
                new_record = RecordTarget(
                    id=record.id,
                    url=record.url,
                    antwortzeit=record.antwortzeit,
                    created_at=record.created_at,
                    tag=record.tag,
                    flag_lazy_loading=record.flag_lazy_loading,
                    is_running=True,
                )
                result.append(new_record)
        # This overwrites unscraped_targets by running_results
        # return list({record.id: record for record in result}.values())
        return result

    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
