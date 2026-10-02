"""Establish the Module 1 migration baseline.

Revision ID: 20261002_0001
Revises:
Create Date: 2026-10-02
"""

from collections.abc import Sequence

revision: str = "20261002_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create no business tables in Module 1."""


def downgrade() -> None:
    """Remove no business tables in Module 1."""
