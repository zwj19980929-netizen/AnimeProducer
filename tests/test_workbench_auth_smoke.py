import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

import core.database as database_module


class TestDatabaseFallback(unittest.TestCase):
    def test_debug_mode_falls_back_to_local_sqlite_when_remote_db_is_unreachable(self):
        with (
            patch.object(database_module.settings, "DEBUG", True),
            patch.object(database_module.settings, "ALLOW_DATABASE_FALLBACK_IN_DEBUG", True),
            patch.object(database_module.settings, "DATABASE_URL", "postgresql://unreachable.example.com:5432/app"),
            patch.object(database_module.settings, "DEV_DATABASE_FALLBACK_URL", "sqlite:///./fallback.db"),
            patch("core.database._can_connect", return_value=False),
        ):
            self.assertEqual(
                database_module._resolve_database_url(),
                "sqlite:///./fallback.db",
            )


class TestAuthWorkbenchSmoke(unittest.TestCase):
    def test_register_create_project_and_fetch_workbench_in_isolated_process(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = os.path.join(tmpdir, "smoke.db")
            script = textwrap.dedent(
                """
                from uuid import uuid4
                from fastapi.testclient import TestClient
                from main import app

                username = f"smoke_{uuid4().hex[:8]}"
                password = "smoke-pass-123"

                with TestClient(app) as client:
                    bootstrap = client.get('/api/v1/auth/bootstrap')
                    assert bootstrap.status_code == 200, bootstrap.text

                    register = client.post('/api/v1/auth/register', json={
                        'username': username,
                        'password': password,
                    })
                    assert register.status_code == 201, register.text
                    token = register.json()['access_token']
                    headers = {'Authorization': f'Bearer {token}'}

                    me = client.get('/api/v1/auth/me', headers=headers)
                    assert me.status_code == 200, me.text

                    created = client.post('/api/v1/projects', headers=headers, json={
                        'name': 'Smoke Test Project',
                        'description': 'workbench smoke test',
                        'style_preset': 'Warm Studio Console',
                    })
                    assert created.status_code == 201, created.text
                    project_id = created.json()['id']

                    projects = client.get('/api/v1/workbench/projects', headers=headers)
                    assert projects.status_code == 200, projects.text
                    assert projects.json()['total'] == 1, projects.text

                    dashboard = client.get(f'/api/v1/workbench/projects/{project_id}/dashboard', headers=headers)
                    assert dashboard.status_code == 200, dashboard.text
                    assert dashboard.json()['project']['name'] == 'Smoke Test Project', dashboard.text

                    workspace = client.get(f'/api/v1/workbench/projects/{project_id}/workspace', headers=headers)
                    assert workspace.status_code == 200, workspace.text
                    assert len(workspace.json()['stage_summaries']) == 7, workspace.text

                print('SMOKE_OK')
                """
            )

            env = os.environ.copy()
            env.update(
                {
                    "DATABASE_URL": f"sqlite:///{database_path}",
                    "DEBUG": "false",
                    "REDIS_URL": "redis://localhost:6379/0",
                }
            )

            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env=env,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                self.fail(
                    "Smoke script failed.\n"
                    f"STDOUT:\n{result.stdout}\n"
                    f"STDERR:\n{result.stderr}"
                )

            self.assertIn("SMOKE_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
