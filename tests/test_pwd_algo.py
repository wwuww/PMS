"""M32.18 口令加固（P0-3）测试：sha256 → argon2id 透明升级 + bootstrap 口令来源。

不依赖第三方时序库或重构现有 conftest，直接复用 ``client`` + ``tmp_path`` 路径。
"""

from __future__ import annotations

import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.services.rbac_service import _hash_legacy, _resolve_bootstrap_password


def _db_path(tmp_path) -> str:
    return str(tmp_path / "test.db")


def _seed_tenant(client: TestClient, code: str = "t_pwd1") -> dict:
    t = client.post("/api/v1/tenants", json={"code": code, "name": "口令测试"}).json()
    return t


def _read_user_row(db_path: str, username: str) -> tuple[str, str, str]:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT pwd_algo, password_hash, salt FROM users WHERE username=?",
            (username,),
        ).fetchone()
        assert row is not None, f"user {username} not found"
        return row[0], row[1], row[2]
    finally:
        conn.close()


def _downgrade_admin_to_sha256(db_path: str, password: str) -> None:
    """手动把 admin 改回 sha256 算法，模拟「存量老账号」。"""
    salt = "deadbeef" * 4  # 32 字符，符合字段长度约束
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE users SET pwd_algo=?, salt=?, password_hash=? WHERE username='admin'",
            ("sha256", salt, _hash_legacy(password, salt)),
        )
        conn.commit()
    finally:
        conn.close()


class TestPwdAlgoUpgrade:
    def test_legacy_sha256_account_can_login_and_is_transparently_upgraded(
        self, client: TestClient, tmp_path
    ) -> None:
        """老算法（sha256）存量账号：原口令能登录，登录后自动升级到 argon2id。"""
        t = _seed_tenant(client, "t_pwd_up")
        db_path = _db_path(tmp_path)

        # 1) 模拟「老账号」：把 admin 改回 sha256
        _downgrade_admin_to_sha256(db_path, "admin123")
        algo, _, _ = _read_user_row(db_path, "admin")
        assert algo == "sha256", "前提：已降级为老算法"

        # 2) 用原口令登录 —— 应走老算法校验通过
        login = client.post(
            f"/api/v1/tenants/{t['code']}/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert login.status_code == 200, login.text
        assert login.json()["status"] == "ok"

        # 3) 落库：pwd_algo 应已升级为 argon2id，且 password_hash 已换
        algo, pwhash, salt = _read_user_row(db_path, "admin")
        assert algo == "argon2id"
        # argon2 编码的 hash 以 $argon2 开头
        assert pwhash.startswith("$argon2"), pwhash
        # salt 字段保留（NOT NULL 兼容老 schema），argon2 不再使用，但保持可观测
        assert salt == "deadbeef" * 4

    def test_argon2id_account_can_login_without_modifying_hash(
        self, client: TestClient, tmp_path
    ) -> None:
        """新算法（argon2id）账号登录：校验通过且 password_hash 不被改写。"""
        t = _seed_tenant(client, "t_pwd_argon")
        db_path = _db_path(tmp_path)

        # 前提：admin 是 seed_default_admin 创建的，pwd_algo 应已是 argon2id
        algo0, pwhash0, salt0 = _read_user_row(db_path, "admin")
        assert algo0 == "argon2id"

        login = client.post(
            f"/api/v1/tenants/{t['code']}/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert login.status_code == 200, login.text

        algo1, pwhash1, salt1 = _read_user_row(db_path, "admin")
        assert algo1 == "argon2id"
        # 升级幂等：hash 不变（maybe_upgrade_to_argon2id 在已是 argon2id 时直接返回 False）
        assert pwhash1 == pwhash0
        assert salt1 == salt0

    def test_wrong_password_does_not_trigger_upgrade(
        self, client: TestClient, tmp_path
    ) -> None:
        """错误口令登录失败，老账号不会被改写。"""
        t = _seed_tenant(client, "t_pwd_bad")
        db_path = _db_path(tmp_path)
        _downgrade_admin_to_sha256(db_path, "admin123")

        # 错口令（≥6 字符满足 Pydantic 约束，期望 status=bad_credentials）
        bad = client.post(
            f"/api/v1/tenants/{t['code']}/auth/login",
            json={"username": "admin", "password": "WRONG-password"},
        )
        assert bad.status_code == 200
        assert bad.json()["status"] == "bad_credentials"
        # 失败路径不应触发透明升级
        algo, pwhash, _ = _read_user_row(db_path, "admin")
        assert algo == "sha256"
        # hash 仍是旧 hash
        assert pwhash == _hash_legacy("admin123", "deadbeef" * 4)


class TestBootstrapPassword:
    """``_resolve_bootstrap_password()``：环境变量与 PMS_ENV 的优先级。"""

    def test_explicit_env_var_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PMS_BOOTSTRAP_ADMIN_PASSWORD", "FromEnv!2026")
        monkeypatch.setenv("PMS_ENV", "prod")
        assert _resolve_bootstrap_password() == "FromEnv!2026"

    def test_prod_without_env_generates_random_and_logs_critical(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv("PMS_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
        monkeypatch.setenv("PMS_ENV", "prod")
        with caplog.at_level("CRITICAL", logger="app.services.rbac_service"):
            pwd = _resolve_bootstrap_password()
        assert len(pwd) >= 24
        # 不应是默认 dev 口令
        assert pwd != "admin123"
        assert any("Randomly generated" in r.message for r in caplog.records)

    def test_dev_without_env_falls_back_to_admin123(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv("PMS_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
        monkeypatch.delenv("PMS_ENV", raising=False)
        with caplog.at_level("WARNING", logger="app.services.rbac_service"):
            pwd = _resolve_bootstrap_password()
        assert pwd == "admin123"
        assert any("Falling back" in r.message for r in caplog.records)
