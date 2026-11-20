"""Port invariants; no application execution or live GitHub calls."""

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

import gates
from policy import PolicyError, load_policy

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("stamphog_publish", ROOT / ".github/scripts/stamphog-publish.py")
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


@pytest.mark.parametrize("path,category", [
    ("package.json", "deps_toolchain"),
    ("packages/cli-v3/package.json", "deps_toolchain"),
    ("pnpm-lock.yaml", "deps_toolchain"),
    ("pnpm-workspace.yaml", "deps_toolchain"),
    ("turbo.json", "deps_toolchain"),
    (".github/workflows/garnet-record.yml", "infra_cicd"),
    ("internal-packages/database/prisma/schema.prisma", "migrations"),
    (".github/scripts/stamphog-publish.py", "stamphog_policy"),
    (".github/merge-gate/gate.py", "stamphog_policy"),
    ("owners.yaml", "stamphog_policy"),
])
def test_sensitive_paths(path, category):
    assert category in gates.detect_deny_categories([path])


def test_empty_files_and_minimal_ownership():
    assert gates.detect_deny_categories([]) == []
    resolvers = gates.build_ownership(ROOT, gates.POLICY.ownership)
    assert resolvers[0].owners("apps/webapp/app/routes/index.tsx") == set()
    assert yaml.safe_load((ROOT / "owners.yaml").read_text()) == {"version": 1, "owners": None}


def test_malformed_policy_fails_closed(tmp_path):
    path = tmp_path / "policy.yml"
    path.write_text("version: 1\n")
    with pytest.raises(PolicyError):
        load_policy(path, lockfile_names=gates._ALL_LOCKFILE_NAMES, ownership_formats=gates.OWNERSHIP_FORMAT_LOCATORS)


def test_recorder_static_contract():
    workflow = yaml.safe_load((ROOT / ".github/workflows/garnet-record.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"pull_request", "push"}
    assert triggers["push"]["branches"] == ["main"]
    job = workflow["jobs"]["dep-install"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["timeout-minutes"] == 15
    assert job["permissions"] == {"contents": "read", "id-token": "write"}
    steps = job["steps"]
    sensor = next(i for i, s in enumerate(steps) if s.get("uses", "").startswith("garnet-org/action@"))
    assert steps[sensor]["uses"] == "garnet-org/action@673a06d87748bec49e4d8df22d371b2a3420aba4"
    assert all("secrets." not in str(s) and "api_token" not in str(s) for s in steps)
    assert all(i > sensor for i, s in enumerate(steps) if s.get("run", "").startswith("pnpm "))


@pytest.mark.parametrize("verdict", ["APPROVED", "REFUSED", "ERROR", "AUTO-APPROVED"])
def test_publish_head_and_marker(verdict):
    body = publisher.render_comment({"head_sha": "a" * 40, "final_verdict": verdict, "review_body": "Exact engine body"})
    assert body.startswith("<!-- stamphog-sticky-review -->")
    assert f"reviewed `{'a' * 40}` — verdict: **{verdict}**" in body
    assert body.endswith("Exact engine body")


def test_empty_publish_does_not_claim_head_bound_verdict():
    body = publisher.render_comment({})
    assert "review failed" in body
    assert "— verdict:" not in body


def test_publish_uses_mocked_gh_and_ignores_spoofed_author(tmp_path, monkeypatch):
    verdict = tmp_path / "verdict.json"
    verdict.write_text(json.dumps({"head_sha": "b" * 40, "final_verdict": "APPROVED"}))
    calls = []
    def fake_gh(args):
        calls.append(args)
        if len(args) == 3:
            return json.dumps([{"id": 1, "user": {"login": "attacker"}, "body": publisher.MARKER}])
        return "{}"
    monkeypatch.setattr(publisher, "gh", fake_gh)
    monkeypatch.setattr(publisher.sys, "argv", ["publisher", str(verdict), "garnet-labs/trigger.dev", "1"])
    publisher.main()
    assert calls[1][2] == "POST"
    assert all("DELETE" not in args for args in calls)
