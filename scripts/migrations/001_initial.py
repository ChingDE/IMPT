"""001_initial.py — Initial IMPT v2 database schema."""
from alembic import op
import sqlalchemy as sa

revision  = '001_initial'
down_revision = None
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table('users',
        sa.Column('id',                    sa.String(36),  primary_key=True),
        sa.Column('email',                 sa.String(255), nullable=False, unique=True),
        sa.Column('hashed_password',       sa.String(255), nullable=False),
        sa.Column('first_name',            sa.String(100), nullable=False, server_default=''),
        sa.Column('last_name',             sa.String(100), nullable=False, server_default=''),
        sa.Column('organization',          sa.String(255), nullable=True),
        sa.Column('role',                  sa.String(50),  nullable=False, server_default='user'),
        sa.Column('is_active',             sa.Boolean(),   nullable=False, server_default=sa.true()),
        sa.Column('is_verified',           sa.Boolean(),   nullable=False, server_default=sa.false()),
        sa.Column('failed_login_attempts', sa.Integer(),   nullable=False, server_default='0'),
        sa.Column('lockout_until',         sa.DateTime(timezone=True), nullable=True),
        sa.Column('username',              sa.String(64),  nullable=True, unique=True),
        sa.Column('must_change_password',  sa.Boolean(),   nullable=False, server_default=sa.false()),
        sa.Column('last_login_at',         sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_active_at',        sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',            sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at',            sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_email',    'users', ['email'],    unique=True)
    op.create_index('ix_users_username', 'users', ['username'], unique=True)

    op.create_table('email_verification_tokens',
        sa.Column('id',             sa.String(36),  primary_key=True),
        sa.Column('user_id',        sa.String(36),  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token',          sa.String(255), nullable=False, unique=True),
        sa.Column('expires_at',     sa.DateTime(timezone=True), nullable=False),
        sa.Column('used',           sa.Boolean(),   nullable=False, server_default=sa.false()),
        sa.Column('resend_count',   sa.Integer(),   nullable=False, server_default='0'),
        sa.Column('last_resend_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',     sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table('password_reset_tokens',
        sa.Column('id',         sa.String(36),  primary_key=True),
        sa.Column('user_id',    sa.String(36),  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token',      sa.String(255), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used',       sa.Boolean(),   nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table('test_sessions',
        sa.Column('id',                 sa.String(36),   primary_key=True),
        sa.Column('owner_id',           sa.String(36),   sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',               sa.String(100),  nullable=False),
        sa.Column('description',        sa.String(500),  nullable=True),
        sa.Column('language',           sa.String(20),   nullable=False),
        sa.Column('status',             sa.String(30),   nullable=False, server_default='not_started'),
        sa.Column('upload_path',        sa.String(500),  nullable=True),
        sa.Column('upload_filename',    sa.String(255),  nullable=True),
        sa.Column('upload_size_bytes',  sa.Integer(),    nullable=True),
        sa.Column('file_count',         sa.Integer(),    nullable=True),
        sa.Column('loc',                sa.Integer(),    nullable=True),
        sa.Column('test_count',         sa.Integer(),    nullable=True),
        sa.Column('detected_framework', sa.String(50),   nullable=True),
        sa.Column('selected_operators', sa.Text(),       nullable=True),
        sa.Column('time_budget_minutes',sa.Integer(),    nullable=True),
        sa.Column('run_comparison',         sa.Boolean(),    nullable=False, server_default=sa.true()),
        sa.Column('run_operator_based',     sa.Boolean(),    nullable=False, server_default=sa.true()),
        sa.Column('estimated_mutant_count', sa.Integer(),    nullable=True),
        sa.Column('recommended_budget_min', sa.Integer(),    nullable=True),
        sa.Column('recommended_budget_max', sa.Integer(),    nullable=True),
        sa.Column('share_token',        sa.String(255),  nullable=True, unique=True),
        sa.Column('share_expires_at',   sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',         sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at',         sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at',         sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at',       sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table('mutation_jobs',
        sa.Column('id',                       sa.String(36),  primary_key=True),
        sa.Column('session_id',               sa.String(36),  sa.ForeignKey('test_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_id',                 sa.String(36),  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('strategy',                 sa.String(30),  nullable=False, server_default='impt'),
        sa.Column('time_budget_seconds',      sa.Integer(),   nullable=False, server_default='1200'),
        sa.Column('optimizer_strategy',       sa.String(20),  nullable=False, server_default='AUTO'),
        sa.Column('jaccard_threshold',        sa.Float(),     nullable=False, server_default='0.9'),
        sa.Column('factor_weights',           sa.Text(),      nullable=True),
        sa.Column('selected_operators',       sa.Text(),      nullable=True),
        sa.Column('status',                   sa.String(20),  nullable=False, server_default='PENDING'),
        sa.Column('celery_task_id',           sa.String(255), nullable=True),
        sa.Column('error_message',            sa.Text(),      nullable=True),
        sa.Column('total_mutants',            sa.Integer(),   nullable=False, server_default='0'),
        sa.Column('selected_mutants',         sa.Integer(),   nullable=False, server_default='0'),
        sa.Column('executed_mutants',         sa.Integer(),   nullable=False, server_default='0'),
        sa.Column('killed_mutants',           sa.Integer(),   nullable=False, server_default='0'),
        sa.Column('mutation_score',           sa.Float(),     nullable=False, server_default='0'),
        sa.Column('estimated_score',          sa.Float(),     nullable=False, server_default='0'),
        sa.Column('ci_lower',                 sa.Float(),     nullable=False, server_default='0'),
        sa.Column('ci_upper',                 sa.Float(),     nullable=False, server_default='0'),
        sa.Column('time_saved_pct',           sa.Float(),     nullable=False, server_default='0'),
        sa.Column('subsumption_reduction_pct',sa.Float(),     nullable=False, server_default='0'),
        sa.Column('execution_time_seconds',   sa.Float(),     nullable=False, server_default='0'),
        sa.Column('result_json',              sa.Text(),      nullable=True),
        sa.Column('created_at',              sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at',              sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at',            sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table('mutant_records',
        sa.Column('id',            sa.String(36),  primary_key=True),
        sa.Column('job_id',        sa.String(36),  sa.ForeignKey('mutation_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('mutant_hash',   sa.String(64),  nullable=False),
        sa.Column('operator',      sa.String(50),  nullable=False),
        sa.Column('file',          sa.String(500), nullable=False),
        sa.Column('line',          sa.Integer(),   nullable=False),
        sa.Column('original_code', sa.Text(),      nullable=True),
        sa.Column('mutated_code',  sa.Text(),      nullable=True),
        sa.Column('status',        sa.String(20),  nullable=False),
        sa.Column('priority_score',sa.Float(),     nullable=False, server_default='0'),
        sa.Column('execution_time',sa.Float(),     nullable=False, server_default='0'),
        sa.Column('explanation',   sa.Text(),      nullable=True),
        sa.Column('killing_test',  sa.String(500), nullable=True),
    )

    op.create_table('saved_profiles',
        sa.Column('id',          sa.String(36),  primary_key=True),
        sa.Column('owner_id',    sa.String(36),  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',        sa.String(100), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('config_json', sa.Text(),      nullable=False),
        sa.Column('is_default',  sa.Boolean(),   nullable=False, server_default=sa.false()),
        sa.Column('times_used',  sa.Integer(),   nullable=False, server_default='0'),
        sa.Column('avg_score',   sa.Float(),     nullable=False, server_default='0'),
        sa.Column('avg_time_seconds', sa.Float(),nullable=False, server_default='0'),
        sa.Column('created_at',  sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at',  sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table('audit_logs',
        sa.Column('id',         sa.String(36),  primary_key=True),
        sa.Column('user_id',    sa.String(36),  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('level',      sa.String(20),  nullable=False, server_default='INFO'),
        sa.Column('category',   sa.String(30),  nullable=False),
        sa.Column('action',     sa.String(100), nullable=False),
        sa.Column('message',    sa.Text(),      nullable=False),
        sa.Column('ip_address', sa.String(45),  nullable=True),
        sa.Column('outcome',    sa.String(20),  nullable=False, server_default='success'),
        sa.Column('extra',      sa.Text(),      nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table('system_config',
        sa.Column('key',         sa.String(100), primary_key=True),
        sa.Column('value',       sa.Text(),      nullable=False),
        sa.Column('description', sa.Text(),      nullable=True),
        sa.Column('updated_by',  sa.String(36),  nullable=True),
        sa.Column('updated_at',  sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    for table in ['system_config', 'audit_logs', 'saved_profiles', 'mutant_records',
                  'mutation_jobs', 'test_sessions', 'password_reset_tokens',
                  'email_verification_tokens', 'users']:
        op.drop_table(table)
