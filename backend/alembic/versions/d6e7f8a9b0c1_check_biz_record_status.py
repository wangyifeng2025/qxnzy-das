"""check biz record status

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-11-04 18:10:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_biz_record_status",
        "biz_record",
        "status IN ('draft', 'pending_dept', 'pending_domain', 'pending_center', "
        "'returned', 'published', 'archived')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_biz_record_status", "biz_record", type_="check")
