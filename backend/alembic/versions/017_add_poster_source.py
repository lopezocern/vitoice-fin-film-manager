"""Add poster_source to media for custom-cover protection.

Distinguishes a user-uploaded cover ("custom") from a scraped one
("scraped"). Scraping skips cover download when the user uploaded their
own cover; only after the user deletes it will scraping re-download.

Revision ID: 017
Revises: 016
Create Date: 2026-08-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "media",
        sa.Column("poster_source", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("media", "poster_source")
