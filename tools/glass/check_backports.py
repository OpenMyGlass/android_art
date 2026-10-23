#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OpenMyGlass: check the commits of glass-4.4 on top of the pinned base.

Every non-merge commit after BASE must be one of:
  - a backport: its message has "(cherry picked from commit <40-hex sha>)", the sha is a
    commit of AOSP platform/art (UPSTREAM, a git remote or ref namespace that has been
    fetched), and the backport keeps the upstream author name and e-mail;
  - an OpenMyGlass commit that touches only our own files (OWN_PATHS).

A backport that differs from its upstream patch must say why, in a line starting with
"OpenMyGlass:". Exact cherry-picks (same patch id) need no note.

Usage: check_backports.py BASE HEAD UPSTREAM_REF [UPSTREAM_REF...]
Exit status 0 when every commit passes, 1 otherwise.
"""
import re
import subprocess
import sys

OWN_PATHS = (".github/", "tools/glass/")
PICK_RE = re.compile(r"^\(cherry picked from commit ([0-9a-f]{40})\)$", re.M)
NOTE_RE = re.compile(r"^OpenMyGlass: ", re.M)


def git(*args, check=True):
    res = subprocess.run(("git",) + args, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise SystemExit("git %s failed: %s" % (" ".join(args), res.stderr.strip()))
    return res


def patch_id(sha):
    diff = git("show", "--format=", sha).stdout
    out = subprocess.run(("git", "patch-id", "--stable"), input=diff,
                         capture_output=True, text=True).stdout.split()
    return out[0] if out else None


def is_upstream(sha, refs):
    if git("cat-file", "-e", sha + "^{commit}", check=False).returncode != 0:
        return False
    for ref in refs:
        if git("merge-base", "--is-ancestor", sha, ref, check=False).returncode == 0:
            return True
    return False


def check(base, head, refs):
    errors = []
    shas = git("rev-list", "--no-merges", "--reverse", "%s..%s" % (base, head)).stdout.split()
    for sha in shas:
        msg = git("log", "-1", "--format=%B", sha).stdout
        title = msg.splitlines()[0] if msg else ""
        picks = PICK_RE.findall(msg)
        where = "%s %s" % (sha[:12], title)
        if not picks:
            files = git("show", "--format=", "--name-only", sha).stdout.split()
            bad = [f for f in files if not f.startswith(OWN_PATHS)]
            if bad:
                errors.append("%s: no '(cherry picked from commit ...)' line, and it touches "
                              "files outside %s: %s" % (where, ", ".join(OWN_PATHS),
                                                        ", ".join(bad)))
            else:
                print("ok   own     %s" % where)
            continue
        if len(picks) != 1:
            errors.append("%s: more than one cherry-pick line" % where)
            continue
        up = picks[0]
        if not is_upstream(up, refs):
            errors.append("%s: %s is not a commit of %s" % (where, up, ", ".join(refs)))
            continue
        ours = git("log", "-1", "--format=%an <%ae>", sha).stdout.strip()
        theirs = git("log", "-1", "--format=%an <%ae>", up).stdout.strip()
        if ours != theirs:
            errors.append("%s: author %s, upstream author %s" % (where, ours, theirs))
            continue
        same = patch_id(sha) == patch_id(up)
        if not same and not NOTE_RE.search(msg):
            errors.append("%s: differs from %s but has no 'OpenMyGlass:' note" % (where, up))
            continue
        print("ok   %s %s (from %s)" % ("exact  " if same else "adapted", where, up[:12]))
    for e in errors:
        print("FAIL " + e)
    print("%d commits, %d failures" % (len(shas), len(errors)))
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    sys.exit(check(sys.argv[1], sys.argv[2], sys.argv[3:]))
