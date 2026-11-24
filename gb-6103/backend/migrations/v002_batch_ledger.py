from sqlalchemy import text

from src.models.base import metadata
from src.models import registers  # Register the acceptance tables.


def upgrade(connection):
    """给批号裁决台账补上资料摘要，供同批号重试比对原资料。"""
    existing = connection.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'acceptance_batch' AND column_name = 'payload_digest'
    """)).first()
    if existing is None:
        connection.execute(text("ALTER TABLE acceptance_batch ADD COLUMN payload_digest VARCHAR(64)"))
