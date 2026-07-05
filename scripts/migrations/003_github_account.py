"""003_github_account.py — add GitHub account-linking columns to users.

  users.github_token        (Text, nullable)      — encrypted OAuth token
  users.github_login        (String, nullable)    — GitHub username
  users.github_connected_at (DateTime, nullable)
"""
from alembic import op
import sqlalchemy as sa

revision = '003_github_account'
down_revision = '002_metadata_columns'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('github_token', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('github_login', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('github_connected_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('users', 'github_connected_at')
    op.drop_column('users', 'github_login')
    op.drop_column('users', 'github_token')
