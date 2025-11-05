"""create logs and dlq tables

Revision ID: 0001_create_logs_dlq
Revises:
Create Date: 2025-08-24 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001_create_logs_dlq'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create logs table
    op.create_table(
        'logs',
        sa.Column('log_id', sa.Text, primary_key=True),
        sa.Column('ts', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('sender_id', sa.Text, nullable=False),
        sa.Column('kind', sa.Text, nullable=False),
        sa.Column('routed_agents', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    
    # Create indexes for logs table
    op.create_index('ix_logs_sender_id', 'logs', ['sender_id'])
    op.create_index('ix_logs_ts_desc', 'logs', ['ts'])
    
    # Create DLQ table
    op.create_table(
        'dlq',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('ts', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('log_id', sa.Text, nullable=False),
        sa.Column('reason', sa.Text, nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('attempts', sa.Integer, nullable=False, server_default='0'),
    )
    
    op.create_index('ix_dlq_log_id', 'dlq', ['log_id']) 
    op.create_index('ix_dlq_replay_order', 'dlq', ['ts', 'attempts'])

def downgrade():
    op.drop_index('ix_dlq_replay_order', table_name='dlq')
    op.drop_index('ix_dlq_log_id', table_name='dlq')
    op.drop_table('dlq')
    op.drop_index('ix_logs_ts_desc', table_name='logs')
    op.drop_index('ix_logs_sender_id', table_name='logs')
    op.drop_table('logs')
