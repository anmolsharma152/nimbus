import unittest
from app.github_client import parse_github_repo
from app.main import TaskCreate


class TestGitHubClient(unittest.TestCase):
    def test_parse_github_repo_formats(self):
        self.assertEqual(parse_github_repo("https://github.com/anmolsharma152/nimbus.git"), ("anmolsharma152", "nimbus"))
        self.assertEqual(parse_github_repo("https://github.com/anmolsharma152/nimbus"), ("anmolsharma152", "nimbus"))
        self.assertEqual(parse_github_repo("git@github.com:anmolsharma152/nimbus.git"), ("anmolsharma152", "nimbus"))
        self.assertEqual(parse_github_repo("anmolsharma152/nimbus"), ("anmolsharma152", "nimbus"))
        self.assertIsNone(parse_github_repo(""))
        self.assertIsNone(parse_github_repo(None))


class TestTaskSchemas(unittest.TestCase):
    def test_task_create_schema(self):
        payload = {
            "prompt": "Fix bug in authentication",
            "repo_url": "https://github.com/test/repo",
            "git_branch": "nimbus/task-42"
        }
        task_req = TaskCreate(**payload)
        self.assertEqual(task_req.prompt, "Fix bug in authentication")
        self.assertEqual(task_req.repo_url, "https://github.com/test/repo")
        self.assertEqual(task_req.git_branch, "nimbus/task-42")

    def test_task_create_schema_minimal(self):
        task_req = TaskCreate(prompt="Quick prompt")
        self.assertEqual(task_req.prompt, "Quick prompt")
        self.assertIsNone(task_req.repo_url)
        self.assertIsNone(task_req.git_branch)


if __name__ == "__main__":
    unittest.main()
