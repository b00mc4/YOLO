from __future__ import annotations
from pydantic import BaseModel

class SSETicketResponse(BaseModel):
    ticket: str