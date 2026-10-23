#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OpenMyGlass: unit tests for check_backports.py, on throw-away git repositories.

Run: python3 -m unittest discover -s tools/glass
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "check_backports.py")


def git(repo, *args, env=None):
    full = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    full.update(env or {})
    return subprocess.run(("git", "-C", repo) + args, check=True, capture_output=True,
                          text=True, env=full).stdout.strip()


def commit(repo, path, text, msg, author="Up Stream <up@example.com>"):
    with open(os.path.join(repo, path), "w") as f:
        f.write(text)
    git(repo, "add", path)
    name, mail = author[:-1].split(" <")
    env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": mail,
           "GIT_COMMITTER_NAME": "Glass", "GIT_COMMITTER_EMAIL": "glass@example.com"}
    git(repo, "commit", "-q", "-m", msg, env=env)
    return git(repo, "rev-parse", "HEAD")


class CheckBackportsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, "init", "-q", "-b", "base")
        self.base = commit(self.repo, "a.cc", "one\ntwo\nthree\n", "base")
        git(self.repo, "checkout", "-q", "-b", "upstream")
        self.fix = commit(self.repo, "a.cc", "one\nTWO\nthree\n", "Fix two")
        git(self.repo, "checkout", "-q", "-b", "glass", self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self):
        return subprocess.run((sys.executable, SCRIPT, self.base, "glass", "upstream"),
                              cwd=self.repo, capture_output=True, text=True)

    def pick(self, text, note=""):
        msg = "Fix two\n\n(cherry picked from commit %s)\n%s" % (self.fix, note)
        return commit(self.repo, "a.cc", text, msg)

    def test_exact_pick_passes(self):
        self.pick("one\nTWO\nthree\n")
        res = self.run_check()
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("exact", res.stdout)

    def test_adapted_pick_needs_note(self):
        self.pick("one\nTWO!\nthree\n")
        self.assertEqual(self.run_check().returncode, 1)

    def test_adapted_pick_with_note_passes(self):
        self.pick("one\nTWO!\nthree\n", "\nOpenMyGlass: adapted.\n")
        res = self.run_check()
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("adapted", res.stdout)

    def test_unknown_sha_fails(self):
        commit(self.repo, "a.cc", "x\n", "Fix\n\n(cherry picked from commit %s)\n" % ("0" * 40))
        self.assertEqual(self.run_check().returncode, 1)

    def test_author_must_match(self):
        commit(self.repo, "a.cc", "one\nTWO\nthree\n",
               "Fix two\n\n(cherry picked from commit %s)\n" % self.fix,
               author="Some One <one@example.com>")
        self.assertEqual(self.run_check().returncode, 1)

    def test_own_commit_only_own_paths(self):
        os.makedirs(os.path.join(self.repo, "tools", "glass"))
        commit(self.repo, "tools/glass/x.py", "x\n", "Add a tool")
        self.assertEqual(self.run_check().returncode, 0)
        commit(self.repo, "a.cc", "changed\n", "Change runtime code")
        self.assertEqual(self.run_check().returncode, 1)


if __name__ == "__main__":
    unittest.main()
