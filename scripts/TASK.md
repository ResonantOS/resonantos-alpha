## Root Cause
morning-digest.py contains personal email addresses from the source system. It should not be in Alpha.

## Fix
Delete the file ~/resonantos-alpha/scripts/morning-digest.py entirely. Also clean up artifacts from shield-gate extension: delete ~/resonantos-alpha/extensions/shield-gate/.git directory, ~/resonantos-alpha/extensions/shield-gate/index.js.bak, and ~/resonantos-alpha/extensions/shield-gate/TASK.md.

## Files to Modify
- ~/resonantos-alpha/scripts/morning-digest.py (DELETE)
- ~/resonantos-alpha/extensions/shield-gate/.git (DELETE directory)
- ~/resonantos-alpha/extensions/shield-gate/index.js.bak (DELETE)
- ~/resonantos-alpha/extensions/shield-gate/TASK.md (DELETE)

## Test Command
Run: test ! -f ~/resonantos-alpha/scripts/morning-digest.py && test ! -d ~/resonantos-alpha/extensions/shield-gate/.git && test ! -f ~/resonantos-alpha/extensions/shield-gate/index.js.bak && echo CLEAN

## Acceptance Criteria
- morning-digest.py no longer exists in Alpha
- shield-gate extension has only index.js and openclaw.plugin.json
- No personal data remains in scripts/

## Data Context
morning-digest.py has augmentor.bot@gmail.com and manolorem@gmail.com hardcoded.

## Preferences
Use rm for files and rm -rf for .git directory. These are deletions, not modifications.
