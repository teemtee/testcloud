import datetime
import logging
import os
from datetime import datetime, timezone

import peewee as pw

from . import config

__all__ = ["DB", "DBImage"]

# DEBUG level writes all SQL queries to output
logger = logging.getLogger("peewee")
logger.setLevel(logging.ERROR)


cfg = config.get_config()
if os.path.exists(cfg.DATA_DIR) and os.access(cfg.DATA_DIR, os.W_OK):
    DB = pw.SqliteDatabase(os.path.join(cfg.DATA_DIR, "testcloud.sqlite"))
else:
    DB = pw.SqliteDatabase(":memory:")


# Peewee does not support datetimes with tzinfo...
class DateTimeTzField(pw.Field):
    field_type = "TEXT"

    def db_value(self, value: datetime) -> str:
        if value:
            return value.isoformat()

    def python_value(self, value: str) -> datetime:
        if value:
            return datetime.fromisoformat(value)


def utcnow():
    return datetime.now(timezone.utc)


class DBImage(pw.Model):
    id = pw.AutoField()
    name = pw.CharField(unique=True)
    status = pw.CharField(default="unknown")
    remote_path = pw.CharField()
    local_path = pw.CharField()
    last_used = DateTimeTzField(default=utcnow)

    class Meta:
        database = DB
        table_name = "image"


def data_dir_changed(pth):
    global DB
    DB.init(os.path.join(pth, "testcloud.sqlite"))
    DB.connect()
    DB.create_tables([DBImage])

DB.connect()
DB.create_tables([DBImage])
