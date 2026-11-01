import os

import pytest
from starlette.testclient import TestClient

from mcp_readonly import auth, tools_k8s, tools_mariadb, tools_nfs
from mcp_readonly.server import build_app

TOKENS = {"claude": "tok-claude", "gemini": "tok-gemini"}


@pytest.mark.parametrize("sql", [
    "SELECT 1", "select * from t where a=1;", "SHOW DATABASES", "DESCRIBE t",
    "EXPLAIN SELECT * FROM t",
])
def test_sql_allowed(sql):
    assert tools_mariadb.validate_sql(sql)


@pytest.mark.parametrize("sql", [
    "", "DELETE FROM t", "DROP TABLE t", "INSERT INTO t VALUES (1)", "UPDATE t SET a=1",
    "SELECT 1; DROP TABLE t", "SELECT 1 /*! ; DROP TABLE t */", "SELECT 1 -- x",
    "SELECT 1 # x", "SELECT * FROM t INTO OUTFILE '/tmp/x'", "SELECT LOAD_FILE('/etc/passwd')",
    "SELECT SLEEP(100)", "SELECT * FROM t FOR UPDATE", "WITH x AS (SELECT 1) DELETE FROM t",
    "CALL evil()", "SET GLOBAL x=1", "GRANT ALL ON *.* TO a",
])
def test_sql_rejected(sql):
    with pytest.raises(ValueError):
        tools_mariadb.validate_sql(sql)


def test_nfs_confinement(tmp_path, monkeypatch):
    root = tmp_path / "share"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "a.csv").write_text("x")
    outside = tmp_path / "secret"
    outside.write_text("nope")
    (root / "link").symlink_to(outside)
    monkeypatch.setenv("NFS_ROOT", str(root))
    assert tools_nfs.resolve("sub/a.csv").endswith("a.csv")
    assert tools_nfs.resolve("/sub") == str(root / "sub")
    for bad in ["../secret", "sub/../../secret", "link", "/../secret"]:
        with pytest.raises(ValueError):
            tools_nfs.resolve(bad)


def test_k8s_redact():
    out = tools_k8s.redact({"metadata": {"managedFields": [1], "name": "p"},
                            "spec": {"containers": [{"env": [{"name": "A", "value": "s3cret"},
                                                             {"name": "B", "valueFrom": {}}]}]}})
    assert "managedFields" not in out["metadata"]
    env = out["spec"]["containers"][0]["env"]
    assert env[0]["value"] == "<redacted>" and "valueFrom" in env[1]


def test_k8s_unknown_kind():
    with pytest.raises(ValueError):
        tools_k8s._check_kind("secrets")


def test_token_matching():
    assert auth.match_client("Bearer tok-claude", TOKENS) == "claude"
    assert auth.match_client("bearer tok-gemini", TOKENS) == "gemini"
    for bad in ["", "Bearer", "Bearer wrong", "Basic tok-claude", "tok-claude"]:
        assert auth.match_client(bad, TOKENS) is None


def test_load_tokens_requires_some():
    with pytest.raises(RuntimeError):
        auth.load_tokens({"PATH": "/bin"})
    assert auth.load_tokens({"MCP_TOKEN_CLAUDE": "a", "MCP_TOKEN_X": ""}) == {"claude": "a"}


def test_http_auth_and_tool_listing():
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    with TestClient(build_app(TOKENS)) as c:
        assert c.post("/mcp", json=body, headers=headers).status_code == 401
        bad = {**headers, "Authorization": "Bearer nope"}
        assert c.post("/mcp", json=body, headers=bad).status_code == 401
        ok = c.post("/mcp", json=body, headers={**headers, "Authorization": "Bearer tok-claude"})
        assert ok.status_code == 200, ok.text
        names = {t["name"] for t in ok.json()["result"]["tools"]}
    assert names == {"k8s_list", "k8s_get", "k8s_top", "db_query", "db_schema",
                     "kafka_list_topics", "kafka_describe_topic", "kafka_read_messages",
                     "nfs_list", "nfs_stat", "nfs_find"}
