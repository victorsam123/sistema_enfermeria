from logging.config import fileConfig
from alembic import context
from flask import current_app

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = current_app.extensions['migrate'].db.metadata

if context.is_offline_mode():
    context.configure(url=str(current_app.extensions['migrate'].db.engine.url), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with current_app.extensions['migrate'].db.engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
