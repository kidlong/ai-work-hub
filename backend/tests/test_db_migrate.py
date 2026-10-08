from sqlalchemy import create_engine, inspect, text

from app.db.session import ensure_dev_columns


def test_adds_missing_column_with_default_true_and_is_idempotent(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE user_settings (username VARCHAR(128) PRIMARY KEY, brief_time VARCHAR(5))"))
        c.execute(text("INSERT INTO user_settings VALUES ('an.nguyen', '07:30')"))

    ensure_dev_columns(eng)
    ensure_dev_columns(eng)  # chạy lần 2 không lỗi

    assert "live_sim_enabled" in {c["name"] for c in inspect(eng).get_columns("user_settings")}
    with eng.connect() as c:
        assert c.execute(text("SELECT live_sim_enabled FROM user_settings")).scalar() == 1


def test_noop_when_table_missing(tmp_path):
    ensure_dev_columns(create_engine(f"sqlite:///{tmp_path / 'empty.db'}"))


def test_settings_roundtrip_live_sim_flag(client, login):
    h = login()
    st = client.get("/api/v1/settings", headers=h).json()
    assert st["live_sim_enabled"] is True
    st["live_sim_enabled"] = False
    assert client.put("/api/v1/settings", json=st, headers=h).json()["live_sim_enabled"] is False
    st["live_sim_enabled"] = True
    assert client.put("/api/v1/settings", json=st, headers=h).json()["live_sim_enabled"] is True
