from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("gstin", sa.String(), nullable=True),
        sa.Column("vendor_code", sa.String(), nullable=True),
    )
    op.create_table(
        "entity_field_definitions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("field_type", sa.String(), nullable=False),
    )
    op.create_table(
        "source_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_table(
        "source_field_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("source_field", sa.String(), nullable=False),
        sa.Column("target_field", sa.String(), nullable=False),
        sa.Column("field_role", sa.String(), nullable=False),
        sa.Column("storage", sa.String(), nullable=False),
    )
    op.create_table(
        "entity_field_values",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
    )
    op.create_table(
        "entity_identifiers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("identifier_type", sa.String(), nullable=False),
        sa.Column("identifier_value", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
    )
    op.create_table(
        "entity_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("entity_history")
    op.drop_table("entity_identifiers")
    op.drop_table("entity_field_values")
    op.drop_table("source_field_mappings")
    op.drop_table("source_records")
    op.drop_table("entity_field_definitions")
    op.drop_table("vendors")
