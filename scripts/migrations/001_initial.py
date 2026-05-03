"""Initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2026-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=True),
        sa.Column('role', sa.String(50), default='student'),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
    )
    op.create_table(
        'projects',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('framework', sa.String(20), nullable=False),
        sa.Column('upload_path', sa.String(512), nullable=True),
        sa.Column('loc', sa.Integer, default=0),
        sa.Column('test_count', sa.Integer, default=0),
        sa.Column('is_foss', sa.Boolean, default=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
    )
    op.create_table(
        'mutation_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('celery_task_id', sa.String(255), nullable=True),
        sa.Column('time_budget_seconds', sa.Integer, default=1800),
        sa.Column('optimizer_strategy', sa.String(20), default='AUTO'),
        sa.Column('jaccard_threshold', sa.Float, default=0.90),
        sa.Column('factor_weights', sa.JSON, nullable=True),
        sa.Column('status', sa.String(20), default='PENDING', index=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_mutants', sa.Integer, default=0),
        sa.Column('selected_mutants', sa.Integer, default=0),
        sa.Column('executed_mutants', sa.Integer, default=0),
        sa.Column('killed_mutants', sa.Integer, default=0),
        sa.Column('mutation_score', sa.Float, default=0.0),
        sa.Column('estimated_score', sa.Float, default=0.0),
        sa.Column('ci_lower', sa.Float, default=0.0),
        sa.Column('ci_upper', sa.Float, default=0.0),
        sa.Column('time_saved_pct', sa.Float, default=0.0),
        sa.Column('subsumption_reduction_pct', sa.Float, default=0.0),
        sa.Column('execution_time_seconds', sa.Float, default=0.0),
        sa.Column('result_json', sa.JSON, nullable=True),
    )
    op.create_table(
        'mutant_records',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('mutation_jobs.id'), nullable=False),
        sa.Column('mutant_hash', sa.String(16), nullable=False),
        sa.Column('operator', sa.String(30), nullable=False),
        sa.Column('file', sa.String(512), nullable=False),
        sa.Column('line', sa.Integer, nullable=False),
        sa.Column('original_code', sa.Text, nullable=False),
        sa.Column('mutated_code', sa.Text, nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('priority_score', sa.Float, default=0.0),
        sa.Column('execution_time', sa.Float, default=0.0),
        sa.Column('explanation', sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table('mutant_records')
    op.drop_table('mutation_jobs')
    op.drop_table('projects')
    op.drop_table('users')
