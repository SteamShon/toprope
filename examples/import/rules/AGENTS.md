# Working in the shop repository

## Releases

Never push a release tag to `main` by hand. The release job tags `main` after the checks pass.

- Only the release manager approves a release.
- A refund over 500 EUR must be approved by a second person before it is paid.

```bash
git push origin main   # an example, not a rule: code is skipped
```

| Change | Who approves |
|---|---|
| Schema change | the data owner only |
