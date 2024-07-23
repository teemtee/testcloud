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
if os.path.exists(cfg.DATA_DIR):
    DB = pw.SqliteDatabase(os.path.join(cfg.DATA_DIR, "testcloud.sqlite"))
else:
    DB = pw.SqliteDatabase(":memory:")


def utcnow():
    return datetime.now(timezone.utc)


class DBImage(pw.Model):
    id = pw.AutoField()
    name = pw.CharField(unique=True)
    status = pw.CharField(default="unknown")
    remote_path = pw.CharField()
    local_path = pw.CharField()
    last_used = pw.DateTimeField(default=utcnow)

    class Meta:
        database = DB
        table_name = "image"


DB.connect()
DB.create_tables([DBImage])
