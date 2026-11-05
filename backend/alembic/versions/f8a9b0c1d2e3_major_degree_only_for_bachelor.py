"""major degree category only required for vocational bachelor

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-11-04 23:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "ODS_ZYSZSJ",
        "SYXWLBM",
        existing_type=sa.String(length=20),
        nullable=True,
        existing_comment="学位授予门类",
    )
    op.create_check_constraint(
        "ck_ODS_ZYSZSJ_SYXWLBM_required",
        "ODS_ZYSZSJ",
        '"ZYCCM" <> \'1\' OR "SYXWLBM" IS NOT NULL',
    )


def downgrade() -> None:
    op.drop_constraint("ck_ODS_ZYSZSJ_SYXWLBM_required", "ODS_ZYSZSJ", type_="check")
    op.alter_column(
        "ODS_ZYSZSJ",
        "SYXWLBM",
        existing_type=sa.String(length=20),
        nullable=False,
        existing_comment="学位授予门类",
    )
