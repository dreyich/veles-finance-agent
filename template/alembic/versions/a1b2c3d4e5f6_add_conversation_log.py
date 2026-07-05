"""Add conversation_log table for closed learning loop.

Revision ID: a1b2c3d4e5f6
Revises: b25d38b0cd7c
Create Date: 2026-06-23

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "b25d38b0cd7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("assistant_response", sa.Text(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        # Quality signals for training data filtering
        sa.Column("has_thinking_tags", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("has_verdict", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("response_length", sa.Integer(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        # Training pipeline tracking
        sa.Column("used_for_training", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("training_version", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_log_session_id", "conversation_log", ["session_id"])
    op.create_index("ix_conversation_log_user_id", "conversation_log", ["user_id"])
    op.create_index("ix_conversation_log_created_at", "conversation_log", ["created_at"])
    op.create_index("ix_conversation_log_used_for_training", "conversation_log", ["used_for_training"])


def downgrade() -> None:
    op.drop_index("ix_conversation_log_used_for_training", table_name="conversation_log")
    op.drop_index("ix_conversation_log_created_at", table_name="conversation_log")
    op.drop_index("ix_conversation_log_user_id", table_name="conversation_log")
    op.drop_index("ix_conversation_log_session_id", table_name="conversation_log")
    op.drop_table("conversation_log")
