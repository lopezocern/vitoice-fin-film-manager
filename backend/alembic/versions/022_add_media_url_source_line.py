"""add media_url source/line/episode columns

在线源入库时只存一条 URL 会丢掉「源 + 线路 + 集数」，详情页与播放器无法区分
同一部片的多条线路。这五个字段把这些信息留在 MediaUrl 上；手工添加的链接保持
NULL，不影响既有数据。

Revision ID: 022
Revises: 021
Create Date: 2026-11-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 全部可空：历史数据不需要回填，prod 走 create_all + _ensure_additive_columns。
_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("source_name", sa.String(length=100)),
    ("source_id", sa.String(length=100)),
    ("line_name", sa.String(length=100)),
    ("episode_name", sa.String(length=200)),
    ("episode_index", sa.Integer()),
)


def upgrade() -> None:
    for name, col_type in _COLUMNS:
        op.add_column("media_urls", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    # SQLite 的 DROP COLUMN 需要较新版本，用 batch 模式保证可回退。
    with op.batch_alter_table("media_urls") as batch:
        for name, _ in reversed(_COLUMNS):
            batch.drop_column(name)
