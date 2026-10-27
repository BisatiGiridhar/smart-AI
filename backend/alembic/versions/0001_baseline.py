"""Baseline schema created from the SQLAlchemy models.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-27

Later schema changes should be generated with `alembic revision --autogenerate -m "..."`
so they are applied incrementally on top of this baseline.
"""
from alembic import op

from app import models  # noqa: F401
from app.db import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(bind=op.get_bind())


def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
