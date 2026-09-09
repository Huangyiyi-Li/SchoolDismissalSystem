from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CredentialEvent:
    credential_id: str
    credential_type: str
    reader_id: str
    reader_ip: str
    transport: str
    occurred_at: datetime
    raw_data: bytes | None = None
