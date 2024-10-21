
How to use git:

**To create a new branch**
```bash
git checkout -b <branch_name>
```

**Work on the Branch**
- Make changes to the code as needed.
- Stage the changes you want to commit
```bash
git add <file_name>
```
- Alternatively, stage all changes:
```bash
git add .
```

**Commit Your Changes**
- To commit the staged changes
```bash
git commit -m "Your descriptive commit message"
```
- Make sure the commit message is clear and explains what the changes do.

**Push the Branch to the Remote Repository**
```bash
git push
```

**Sync Your Branch with the Main Branch (Rebase)**
- Before merging your branch, make sure to update your branch with the latest changes from the main branch:
1. Switch to the main branch:
2. Pull the latest changes:
3. Switch back to your branch:
4. Rebase your branch onto the latest main branch:
```bash
git rebase main
```
- Resolve any merge conflicts that arise during the rebase

**Merge Your Branch to the Main Branch**
1. After a successful rebase, switch to the main branch:
2. Merge your branch into the main branch:
```bash
git merge <branch_name>
```
After a succsefull merge push the changes
```bash
git push
```
\
\

If you want to checkout another branch whith uncommited changes
```bash
git stash
```
NB: This will discard your local changes

