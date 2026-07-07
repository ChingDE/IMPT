"""004_foss_mutant_cache.py — cache full mutant list on exhaustive baselines.

Adds exhaustive_baselines.mutants_json (Text): the serialized full mutant list
(with real PIT statuses) so live FOSS-Java sessions load the cache instead of
re-running exhaustive PIT.
"""
from alembic import op
import sqlalchemy as sa

revision = '004_foss_mutant_cache'
down_revision = '003_github_account'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('exhaustive_baselines', sa.Column('mutants_json', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('exhaustive_baselines', 'mutants_json')
