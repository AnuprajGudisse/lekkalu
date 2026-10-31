"""Initial schema and ledger immutability trigger.

Reviewed by hand. The trigger is not produced by autogenerate.

Revision ID: 0001
Revises: 
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

# Ledger rows are immutable. The only allowed UPDATE sets the void link once, from NULL.
IMMUTABILITY_SQL = """
CREATE FUNCTION ledger_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    void_link CONSTANT text[] := ARRAY['voided_at', 'voided_by_message_id', 'replaced_by_id', 'correction_reason'];
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.voided_at IS NULL
       AND NEW.voided_at IS NOT NULL
       AND (to_jsonb(NEW) - void_link) = (to_jsonb(OLD) - void_link) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'ledger rows are immutable (% rejected)', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER transactions_immutable_row
    BEFORE UPDATE OR DELETE ON transactions
    FOR EACH ROW EXECUTE FUNCTION ledger_immutable();

CREATE TRIGGER transactions_no_truncate
    BEFORE TRUNCATE ON transactions
    FOR EACH STATEMENT EXECUTE FUNCTION ledger_immutable();
"""

DROP_IMMUTABILITY_SQL = """
DROP TRIGGER transactions_no_truncate ON transactions;
DROP TRIGGER transactions_immutable_row ON transactions;
DROP FUNCTION ledger_immutable();
"""



def upgrade() -> None:
    op.create_table('businesses',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('slug', sa.Text(), nullable=False),
    sa.Column('access_token', sa.Text(), nullable=True),
    sa.Column('is_public_demo', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('is_public_demo OR access_token IS NOT NULL', name=op.f('ck_businesses_private_has_token')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_businesses')),
    sa.UniqueConstraint('access_token', name=op.f('uq_businesses_access_token')),
    sa.UniqueConstraint('slug', name=op.f('uq_businesses_slug'))
    )
    op.create_table('customers',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('business_id', sa.BigInteger(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('name_native', sa.Text(), nullable=True),
    sa.Column('normalized_name', sa.Text(), nullable=False),
    sa.Column('aliases', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_customers_business_id_businesses')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_customers')),
    sa.UniqueConstraint('business_id', 'id', name=op.f('uq_customers_business_id_id')),
    sa.UniqueConstraint('business_id', 'normalized_name', name=op.f('uq_customers_business_id_normalized_name'))
    )
    op.create_table('messages',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('business_id', sa.BigInteger(), nullable=False),
    sa.Column('channel', sa.Text(), nullable=False),
    sa.Column('external_message_id', sa.Text(), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('audio_path', sa.Text(), nullable=True),
    sa.Column('transcript_te', sa.Text(), nullable=True),
    sa.Column('transcript_en', sa.Text(), nullable=True),
    sa.Column('extraction', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.Text(), server_default='received', nullable=False),
    sa.Column('clarification_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reply_text', sa.Text(), nullable=True),
    sa.Column('replied_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("channel IN ('web', 'whatsapp')", name=op.f('ck_messages_channel')),
    sa.CheckConstraint("kind IN ('text', 'audio')", name=op.f('ck_messages_kind')),
    sa.CheckConstraint("status <> 'awaiting_clarification' OR clarification_expires_at IS NOT NULL", name=op.f('ck_messages_clarification_has_expiry')),
    sa.CheckConstraint("status IN ('received', 'processing', 'awaiting_clarification', 'expired', 'done', 'failed')", name=op.f('ck_messages_status')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_messages_business_id_businesses')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages')),
    sa.UniqueConstraint('business_id', 'id', name=op.f('uq_messages_business_id_id')),
    sa.UniqueConstraint('channel', 'external_message_id', name=op.f('uq_messages_channel_external_message_id'))
    )
    op.create_index(op.f('ix_messages_business_id_status_received_at_id'), 'messages', ['business_id', 'status', 'received_at', 'id'], unique=False)
    op.create_table('transactions',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('business_id', sa.BigInteger(), nullable=False),
    sa.Column('customer_id', sa.BigInteger(), nullable=True),
    sa.Column('source_message_id', sa.BigInteger(), nullable=False),
    sa.Column('line_no', sa.SmallInteger(), server_default='1', nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('amount_paise', sa.BigInteger(), nullable=False),
    sa.Column('cost_paise', sa.BigInteger(), nullable=True),
    sa.Column('item', sa.Text(), nullable=True),
    sa.Column('item_native', sa.Text(), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('voided_by_message_id', sa.BigInteger(), nullable=True),
    sa.Column('replaced_by_id', sa.BigInteger(), nullable=True),
    sa.Column('correction_reason', sa.Text(), nullable=True),
    sa.CheckConstraint("cost_paise IS NULL OR type IN ('sale', 'credit_sale')", name=op.f('ck_transactions_cost_only_on_sales')),
    sa.CheckConstraint("type IN ('sale', 'credit_sale', 'purchase', 'expense', 'payment_received')", name=op.f('ck_transactions_type')),
    sa.CheckConstraint("type NOT IN ('credit_sale', 'payment_received') OR customer_id IS NOT NULL", name=op.f('ck_transactions_credit_has_customer')),
    sa.CheckConstraint('(voided_at IS NULL) = (voided_by_message_id IS NULL)', name=op.f('ck_transactions_void_link_complete')),
    sa.CheckConstraint('amount_paise > 0', name=op.f('ck_transactions_amount_positive')),
    sa.CheckConstraint('cost_paise IS NULL OR cost_paise >= 0', name=op.f('ck_transactions_cost_non_negative')),
    sa.CheckConstraint('quantity IS NULL OR quantity > 0', name=op.f('ck_transactions_quantity_positive')),
    sa.CheckConstraint('replaced_by_id <> id', name=op.f('ck_transactions_not_replaced_by_self')),
    sa.CheckConstraint('replaced_by_id IS NULL OR voided_at IS NOT NULL', name=op.f('ck_transactions_replaced_implies_voided')),
    sa.ForeignKeyConstraint(['business_id', 'customer_id'], ['customers.business_id', 'customers.id'], name=op.f('fk_transactions_business_id_customer_id_customers')),
    sa.ForeignKeyConstraint(['business_id', 'source_message_id'], ['messages.business_id', 'messages.id'], name=op.f('fk_transactions_business_id_source_message_id_messages')),
    sa.ForeignKeyConstraint(['business_id', 'voided_by_message_id'], ['messages.business_id', 'messages.id'], name=op.f('fk_transactions_business_id_voided_by_message_id_messages')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_transactions_business_id_businesses')),
    sa.ForeignKeyConstraint(['business_id', 'replaced_by_id'], ['transactions.business_id', 'transactions.id'], name=op.f('fk_transactions_business_id_replaced_by_id_transactions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transactions')),
    sa.UniqueConstraint('business_id', 'id', name=op.f('uq_transactions_business_id_id')),
    sa.UniqueConstraint('source_message_id', 'line_no', name=op.f('uq_transactions_source_message_id_line_no'))
    )
    op.create_index('ix_transactions_active_business_occurred', 'transactions', ['business_id', 'occurred_at'], unique=False, postgresql_where=sa.text('voided_at IS NULL'))
    op.create_index('ix_transactions_active_customer', 'transactions', ['customer_id'], unique=False, postgresql_where=sa.text('voided_at IS NULL'))
    op.execute(IMMUTABILITY_SQL)


def downgrade() -> None:
    op.execute(DROP_IMMUTABILITY_SQL)
    op.drop_index('ix_transactions_active_customer', table_name='transactions', postgresql_where=sa.text('voided_at IS NULL'))
    op.drop_index('ix_transactions_active_business_occurred', table_name='transactions', postgresql_where=sa.text('voided_at IS NULL'))
    op.drop_table('transactions')
    op.drop_index(op.f('ix_messages_business_id_status_received_at_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_table('customers')
    op.drop_table('businesses')
