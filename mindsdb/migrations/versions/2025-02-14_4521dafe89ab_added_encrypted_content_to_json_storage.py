"""added_encrypted_content_to_json_storage

Revision ID: 4521dafe89ab
Revises: c06c35f7e8e1
Create Date: 2025-02-14 12:05:13.102594

"""
from alembic import op
import sqlalchemy as sa
import mindsdb.interfaces.storage.db  # noqa


# revision identifiers, used by Alembic.
revision = '4521dafe89ab'
down_revision = 'c06c35f7e8e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('json_storage', schema=None) as batch_op:
        batch_op.add_column(sa.Column('encrypted_content', sa.LargeBinary(), nullable=True))


def downgrade():
    with op.batch_alter_table('json_storage', schema=None) as batch_op:
        batch_op.drop_column('encrypted_content')
