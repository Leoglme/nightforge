"""
Queue sync — propagate run message outcomes back to linked queue items.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from enums.queue_item_status import QueueItemStatus
from models.queue_item import QueueItem
from models.run_message import RunMessage


def sync_queue_items_for_run_message(
    db: Session,
    run_message: RunMessage,
    new_status: str,
    error: Optional[str] = None,
) -> None:
    """
    Update queue items referenced by a run message when its status changes.

    Args:
        db: Database session.
        run_message: The run message whose linked queue items should be updated.
        new_status: New run message status (RUNNING, DONE, FAILED, …).
        error: Optional error text when failed.
    """
    ids = run_message.source_item_ids
    if not ids:
        return

    for raw_id in ids:
        try:
            item_id = int(raw_id)
        except (TypeError, ValueError):
            continue

        item = (
            db.query(QueueItem)
            .filter(
                QueueItem.id == item_id,
                QueueItem.project_id == run_message.project_id,
            )
            .first()
        )
        if item is None:
            continue

        if new_status == QueueItemStatus.DONE.value:
            item.status = QueueItemStatus.DONE.value
            item.error = None
        elif new_status == QueueItemStatus.RUNNING.value:
            if item.status in (
                QueueItemStatus.PENDING.value,
                QueueItemStatus.FAILED.value,
            ):
                item.status = QueueItemStatus.RUNNING.value
        elif new_status == QueueItemStatus.FAILED.value:
            item.status = QueueItemStatus.FAILED.value
            if error:
                item.error = error
