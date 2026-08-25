"""Add repo and pr fields to tasks

Revision ID: a1b2c3d4e5f6
Revises: f21576db427c
Create Date: 2026-08-25 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f21576db427c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('repo_url', sa.String(), nullable=True))
    op.add_column('tasks', sa.Column('git_branch', sa.String(), nullable=True))
    op.add_column('tasks', sa.Column('pr_url', sa.String(), nullable=True))
    op.add_column('tasks', sa.Column('patch_diff', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'patch_diff')
    op.drop_column('tasks', 'pr_url')
    op.drop_column('tasks', 'git_branch')
    op.drop_column('tasks', 'repo_url')
