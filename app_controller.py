from __future__ import annotations

from queue_service import QueueService


class AppController:
    def __init__(self) -> None:
        self.queue_service = QueueService()
