from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_container_runs_single_process_as_non_root_and_excludes_private_inputs():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "USER huiyan" in dockerfile
    assert 'CMD ["python", "scripts/start_production.py"]' in dockerfile
    assert ".env*" in dockerignore
    assert "data" in dockerignore
    assert "赛事资料" in dockerignore
    assert "samples" in dockerignore


def test_compose_requires_access_control_and_persists_data():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    start_script = (ROOT / "scripts" / "start_production.py").read_text(
        encoding="utf-8"
    )

    assert 'REQUIRE_ACCESS_CONTROL: "true"' in compose
    assert "./data:/app/data" in compose
    assert "workers=1" in start_script
    assert "proxy_headers=False" in start_script
