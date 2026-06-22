"""002_metadata_columns.py — add project-metadata columns.

Adds, for the panel's "display project metadata" requirement:
  foss_projects.file_count       (Integer, nullable)  — pre-computed source file count
  foss_projects.test_coverage    (Float,   nullable)  — pre-computed line coverage %, 0-100
  test_sessions.test_coverage    (Float,   nullable)  — line coverage %, measured live on upload

All columns are nullable so existing rows remain valid; FOSS values are filled
by scripts/compute_foss_metadata.py and upload values by the measure_coverage task.
"""
from alembic import op
import sqlalchemy as sa

revision = '002_metadata_columns'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('foss_projects', sa.Column('file_count',    sa.Integer(), nullable=True))
    op.add_column('foss_projects', sa.Column('test_coverage', sa.Float(),   nullable=True))
    op.add_column('test_sessions', sa.Column('test_coverage', sa.Float(),   nullable=True))


def downgrade():
    op.drop_column('test_sessions', 'test_coverage')
    op.drop_column('foss_projects', 'test_coverage')
    op.drop_column('foss_projects', 'file_count')
