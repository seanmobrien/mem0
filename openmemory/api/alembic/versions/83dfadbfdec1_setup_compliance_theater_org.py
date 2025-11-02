"""setup compliance-theater org

Revision ID: 83dfadbfdec1
Revises: afd00efbd06b
Create Date: 2025-11-01 20:19:27.469114

"""
import datetime
import json
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '83dfadbfdec1'
down_revision: Union[str, None] = 'afd00efbd06b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    
    conn = op.get_bind()
    now = datetime.datetime.utcnow().isoformat()
    app_id = str(uuid.uuid4())
    # Get the owner_id for "Default User"
    result = conn.execute(
        sa.text("SELECT id FROM users WHERE name = :name"),
        {"name": "Default User"}
    )
    row = result.fetchone()
    
    if row is None:
        # Create a new Default User if it doesn't exist
        owner_id = str(uuid.uuid4())
        conn.execute(
            sa.text("""
                INSERT INTO users (id, user_id, name, email, metadata, created_at, updated_at)
                VALUES (:id, :user_id, :name, :email, :metadata::jsonb, :created_at, :updated_at)
            """),
            {
                "id": owner_id,
                "user_id": "johnconner",
                "name": "Default User",
                "email": None,
                "metadata": json.dumps({"origin": "migration"}),
                "created_at": now,
                "updated_at": now,
            }
        )
    else:
        owner_id = str(row[0])
    
    stmt = sa.text("""
    INSERT INTO apps (id, owner_id, name, description, metadata, is_active, created_at, updated_at)
    VALUES (:id, :owner_id, :name, :description, :metadata::jsonb, :is_active, :created_at, :updated_at)
    ON CONFLICT (name) DO UPDATE
      SET description = EXCLUDED.description,
          metadata = EXCLUDED.metadata,
          is_active = EXCLUDED.is_active,
          updated_at = EXCLUDED.updated_at
    """)
    conn.execute(stmt, {
       "id": app_id,
       "owner_id": owner_id,
       "name": "school-law",
       "description": "Compliance Theater 2000 application",
       "metadata": json.dumps({"origin": "migration", "seed": True}),
       "is_active": True,
       "created_at": now,
       "updated_at": now,
    })

def downgrade() -> None:
    """Downgrade schema."""
    op.execute(sa.text("DELETE FROM apps WHERE name = :name"), {"name": "school-law"})
