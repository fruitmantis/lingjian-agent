"""SQLite fixture compatibility; runtime PostgreSQL uses an explicit migration."""
from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateTable, CreateIndex
from .storage_models import feedback_issue, feedback_attachment


def initialize_feedback_fixture(connection):
    for table in (feedback_issue, feedback_attachment):
        connection.execute(str(CreateTable(table, if_not_exists=True).compile(dialect=sqlite.dialect())))
        for index in table.indexes:
            connection.execute(str(CreateIndex(index, if_not_exists=True).compile(dialect=sqlite.dialect())))
