"""Add task follow-up messages and branch-continuation fields

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-31 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('base_sha', sa.String(length=40), nullable=True))
    op.add_column('tasks', sa.Column('pushed_sha', sa.String(length=40), nullable=True))
    op.add_column('tasks', sa.Column('head_repo', sa.String(), nullable=True))
    op.create_table(
        'task_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name='fk_task_messages_task_id_tasks', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_task_messages_id'), 'task_messages', ['id'], unique=False)
    op.create_index(op.f('ix_task_messages_task_id'), 'task_messages', ['task_id'], unique=False)
    op.create_index(op.f('ix_task_messages_created_at'), 'task_messages', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_task_messages_created_at'), table_name='task_messages')
    op.drop_index(op.f('ix_task_messages_task_id'), table_name='task_messages')
    op.drop_index(op.f('ix_task_messages_id'), table_name='task_messages')
    op.drop_table('task_messages')
    op.drop_column('tasks', 'head_repo')
    op.drop_column('tasks', 'pushed_sha')
    op.drop_column('tasks', 'base_sha')
