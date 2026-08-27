"""Add user_credentials table and users.onboarding_completed

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-27 16:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add onboarding_completed to users table
    op.add_column('users', sa.Column('onboarding_completed', sa.Boolean(), server_default='false', nullable=False))

    # 2. Create user_credentials table
    op.create_table(
        'user_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('encrypted_value', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_credentials_user_id_users', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'provider', name='uq_user_credential_provider')
    )
    op.create_index(op.f('ix_user_credentials_id'), 'user_credentials', ['id'], unique=False)
    op.create_index(op.f('ix_user_credentials_user_id'), 'user_credentials', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_credentials_user_id'), table_name='user_credentials')
    op.drop_index(op.f('ix_user_credentials_id'), table_name='user_credentials')
    op.drop_table('user_credentials')
    op.drop_column('users', 'onboarding_completed')
