"""class approvals recorded in the tool

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-14 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('class_approvals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(), server_default='erp', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('class_approvals', schema=None) as batch_op:
        batch_op.drop_column('source')
