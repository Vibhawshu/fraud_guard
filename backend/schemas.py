from pydantic import BaseModel
from typing import List, Optional


class PredictRequest(BaseModel):
    text: str
    message_type: str = "sms"


class TokenHighlight(BaseModel):
    token: str
    weight: float


class PredictResponse(BaseModel):
    id: int
    label: str
    confidence: float
    explanation: List[TokenHighlight]
    raw_text: str
    created_at: str


class HistoryItem(BaseModel):
    id: int
    message_type: str
    source: str
    subject: Optional[str] = None
    sender: Optional[str] = None
    original_text: str
    label: str
    confidence: float
    explanation: List[TokenHighlight]
    created_at: str


class HistoryResponse(BaseModel):
    items: List[HistoryItem]
    total: int
    page: int
    page_size: int
    stats: dict


class HistoryDetail(BaseModel):
    id: int
    message_type: str
    source: str
    subject: Optional[str] = None
    sender: Optional[str] = None
    original_text: str
    label: str
    confidence: float
    explanation: List[TokenHighlight]
    created_at: str


class DeleteResponse(BaseModel):
    deleted: int
    message: str