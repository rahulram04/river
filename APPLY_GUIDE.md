# Apply the River MVP to your existing GitHub checkout

This archive is a **complete project tree** to merge into an existing `~/river` checkout. It does not contain Git history, the old tracked Jira JSON export or any Jira credentials.

First make sure your local repository is clean (`git status`). Commit or stash your own changes before replacing files.

```bash
# 1. Extract river-mvp.zip to your Downloads folder in a separate tree.
cd ~/Downloads
unzip river-mvp.zip

# 2. Create a local feature branch in your already-cloned repository.
cd ~/river
git status
git switch -c feature/river-mvp

# 3. Copy the implementation, retaining your existing .git directory.
rsync -av ~/Downloads/river/ ~/river/

# 4. The old Jira export was already tracked despite being ignored.
# Remove it from Git's index, preserving your local file.
git rm --cached jira_issue.json

# 5. Review the change before committing.
git status
git add -A
git diff --cached --check
git diff --cached --stat
```

Review file changes and your own pending work before optionally running `git commit -m "Build River prediction market MVP"`. Nothing in this archive automatically pushes to GitHub or edits Jira.

Run the tests, then follow `README.md` to start the app. For local macOS setup without Docker, use a Python virtual environment and SQLite for single-user development. PostgreSQL is necessary to validate concurrency semantics.

**Historical data warning:** Removing `jira_issue.json` from the new Git index does not remove the file from older commits. Have your co-founder review whether the public history should be separately purged, and rotate any credentials that were disclosed. Do not paste tokens into code or chat.
