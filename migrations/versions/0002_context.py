"""Receiver indexes and frozen scoring context, including late-arrival metadata."""
from alembic import op
import sqlalchemy as sa
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('transactions', sa.Column('payee_id', sa.String(64), nullable=True))
    op.add_column('transactions', sa.Column('context', sa.JSON(), nullable=True))
    table=sa.table('transactions',sa.column('id'),sa.column('payload',sa.JSON()),
                   sa.column('payee_id'),sa.column('context',sa.JSON()))
    conn=op.get_bind()
    for row in conn.execute(sa.select(table.c.id,table.c.payload)).mappings():
        conn.execute(table.update().where(table.c.id==row['id']).values(
            payee_id=row['payload']['payee_id'],context={'legacy':True,'feature_version':'2.0.0'}))
    with op.batch_alter_table('transactions') as batch:
        batch.alter_column('payee_id',existing_type=sa.String(64),nullable=False)
        batch.alter_column('context',existing_type=sa.JSON(),nullable=False)
        batch.create_index('ix_transactions_payee_id',['payee_id'])
        batch.create_index('ix_payee_event_time',['payee_id','event_time'])


def downgrade():
    with op.batch_alter_table('transactions') as batch:
        batch.drop_index('ix_payee_event_time')
        batch.drop_index('ix_transactions_payee_id')
        batch.drop_column('context')
        batch.drop_column('payee_id')
