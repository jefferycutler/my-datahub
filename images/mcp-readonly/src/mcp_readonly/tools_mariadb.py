"""MariaDB read-only tools. The DB user should be SELECT-only on the replica; the
guard below is defence in depth, not the only control."""
import os
import re

import pymysql

from .common import audited, jsonable

ALLOWED_FIRST_WORDS = {"select", "show", "describe", "desc", "explain"}
FORBIDDEN = re.compile(
    r"\b(into\s+(outfile|dumpfile|@)|load_file|sleep|benchmark|get_lock|release_lock"
    r"|for\s+update|lock\s+in\s+share\s+mode)\b",
    re.I,
)


def validate_sql(sql: str) -> str:
    """Return the cleaned statement or raise ValueError. Single read statement only."""
    stmt = sql.strip().rstrip(";").strip()
    if not stmt:
        raise ValueError("empty statement")
    # Comments (including MariaDB /*! executable */ ones) are a bypass vector: refuse all.
    if "/*" in stmt or "--" in stmt or "#" in stmt:
        raise ValueError("SQL comments are not allowed")
    if ";" in stmt:
        raise ValueError("only a single statement is allowed")
    if stmt.split(None, 1)[0].lower() not in ALLOWED_FIRST_WORDS:
        raise ValueError(f"only {sorted(ALLOWED_FIRST_WORDS)} statements are allowed")
    if FORBIDDEN.search(stmt):
        raise ValueError("statement uses a forbidden construct")
    return stmt


def _connect(database: str | None = None):
    conn = pymysql.connect(
        host=os.environ["MARIADB_HOST"],
        port=int(os.environ.get("MARIADB_PORT", "3306")),
        user=os.environ["MARIADB_USER"],
        password=os.environ["MARIADB_PW"],
        database=database,
        connect_timeout=5,
        read_timeout=20,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    with conn.cursor() as cur:
        cur.execute("SET SESSION TRANSACTION READ ONLY")
        cur.execute("SET SESSION max_statement_time = 15")
    return conn


def register(mcp):
    @mcp.tool()
    @audited
    def db_query(sql: str, database: str | None = None, max_rows: int = 200) -> dict:
        """Run ONE read-only statement (SELECT/SHOW/DESCRIBE/EXPLAIN) on the MariaDB replica."""
        stmt = validate_sql(sql)
        max_rows = max(1, min(max_rows, 1000))
        conn = _connect(database)
        try:
            with conn.cursor() as cur:
                cur.execute(stmt)
                rows = cur.fetchmany(max_rows + 1)
        finally:
            conn.close()
        truncated = len(rows) > max_rows
        return jsonable({"rows": rows[:max_rows], "truncated": truncated})

    @mcp.tool()
    @audited
    def db_schema(database: str | None = None, table: str | None = None) -> dict:
        """List databases; with database, list its tables; with both, describe the table."""
        conn = _connect()
        try:
            with conn.cursor() as cur:
                if not database:
                    cur.execute("SHOW DATABASES")
                elif not table:
                    cur.execute(
                        "SELECT table_name, table_rows, data_length, engine "
                        "FROM information_schema.tables WHERE table_schema = %s", (database,))
                else:
                    cur.execute(
                        "SELECT column_name, column_type, is_nullable, column_key "
                        "FROM information_schema.columns "
                        "WHERE table_schema = %s AND table_name = %s "
                        "ORDER BY ordinal_position", (database, table))
                return jsonable({"rows": cur.fetchall()})
        finally:
            conn.close()
