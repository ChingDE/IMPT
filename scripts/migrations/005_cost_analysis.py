"""005_cost_analysis.py — resource metrics for Cost Analysis (panel comment).

Adds measured CPU seconds, peak memory, and storage footprint to mutation_jobs.
NULL for jobs executed before this feature; the dashboard shows '—' for those.
"""
from alembic import op
import sqlalchemy as sa

revision = '005_cost_analysis'
down_revision = '004_foss_mutant_cache'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mutation_jobs', sa.Column('cpu_seconds', sa.Float(), nullable=True))
    op.add_column('mutation_jobs', sa.Column('peak_memory_mb', sa.Float(), nullable=True))
    op.add_column('mutation_jobs', sa.Column('storage_mb', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('mutation_jobs', 'storage_mb')
    op.drop_column('mutation_jobs', 'peak_memory_mb')
    op.drop_column('mutation_jobs', 'cpu_seconds')
