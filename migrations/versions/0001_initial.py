"""Initial immutable v2 schema."""
from alembic import op
import sqlalchemy as sa
revision='0001'
down_revision=None
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('users',sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('username',sa.String(64),nullable=False,unique=True),
        sa.Column('password_hash',sa.Text,nullable=False),sa.Column('role',sa.String(16),nullable=False),
        sa.Column('active',sa.Boolean,nullable=False))
    op.create_table('transactions',sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('transaction_id',sa.String(64),unique=True,nullable=False),
        sa.Column('payload_hash',sa.String(64),nullable=False),sa.Column('payer_id',sa.String(64),nullable=False),
        sa.Column('event_time',sa.DateTime(timezone=True),nullable=False),sa.Column('payload',sa.JSON,nullable=False),
        sa.Column('features',sa.JSON,nullable=False),sa.Column('score',sa.Float,nullable=True),
        sa.Column('decision',sa.String(16),nullable=False),sa.Column('reasons',sa.JSON,nullable=False),
        sa.Column('model_version',sa.String(128),nullable=False),sa.Column('model_status',sa.String(20),nullable=False),
        sa.Column('latency_ms',sa.Float,nullable=False),sa.Column('actor_id',sa.Integer,sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_transactions_payer_id','transactions',['payer_id'])
    op.create_index('ix_payer_event_time','transactions',['payer_id','event_time'])
    op.create_table('cases',sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('transaction_id',sa.Integer,sa.ForeignKey('transactions.id'),unique=True,nullable=False),
        sa.Column('status',sa.String(20),nullable=False),sa.Column('outcome',sa.String(20)),
        sa.Column('assigned_to',sa.Integer,sa.ForeignKey('users.id')),sa.Column('notes',sa.Text,nullable=False),
        sa.Column('revision',sa.Integer,nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('audit_events',sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('actor_id',sa.Integer,sa.ForeignKey('users.id')),sa.Column('action',sa.String(64),nullable=False),
        sa.Column('target',sa.String(128),nullable=False),sa.Column('details',sa.JSON,nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('rate_events',sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('bucket',sa.String(128),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_rate_events_bucket','rate_events',['bucket'])
    op.create_index('ix_rate_events_created_at','rate_events',['created_at'])


def downgrade():
    for table in ['rate_events','audit_events','cases','transactions','users']:op.drop_table(table)
