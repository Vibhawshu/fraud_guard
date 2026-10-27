from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from datetime import datetime
from backend.database import Base


class AnalysisRecord(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    message_type = Column(String(20), nullable=False, index=True)
    source = Column(String(20), nullable=False, default="manual")  # "manual" | "gmail"
    subject = Column(String(500), nullable=True)
    sender = Column(String(300), nullable=True)
    original_text = Column(Text, nullable=False)
    label = Column(String(30), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    explanation_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "message_type": self.message_type,
            "source": self.source or "manual",
            "subject": self.subject,
            "sender": self.sender,
            "original_text": self.original_text,
            "label": self.label,
            "confidence": self.confidence,
            "explanation": json.loads(self.explanation_json),
            "created_at": self.created_at.isoformat() + "Z",
        }