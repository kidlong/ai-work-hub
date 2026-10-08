from app import worker
from app.core.config import Settings


def test_sim_job_registered_only_in_mock_mode():
    mock_jobs = {j.id for j in worker.build_scheduler(Settings(mock_connectors=True)).get_jobs()}
    real_jobs = {j.id for j in worker.build_scheduler(Settings(mock_connectors=False)).get_jobs()}
    assert "sim" in mock_jobs and {"sync", "dispatch", "brief"} <= mock_jobs
    assert "sim" not in real_jobs and {"sync", "dispatch", "brief"} <= real_jobs


def test_sim_job_runs_every_10_seconds():
    sched = worker.build_scheduler(Settings(mock_connectors=True))
    job = next(j for j in sched.get_jobs() if j.id == "sim")
    assert job.trigger.interval.total_seconds() == 10 and job.max_instances == 1


def test_job_sim_tick_delegates_to_ticker(monkeypatch, client):
    calls = []

    class FakeTicker:
        def tick(self, db, active_days):
            calls.append(active_days)
            return ["an.nguyen"]

    monkeypatch.setattr(worker, "_ticker", FakeTicker())
    worker.job_sim_tick()
    assert calls == [worker.ACTIVE_USER_DAYS]
