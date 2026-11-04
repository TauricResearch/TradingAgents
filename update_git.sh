git fetch upstream
git switch main && git merge --ff-only upstream/main && git push origin main
git switch custom && git rebase main && git push --force-with-lease
