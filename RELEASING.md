# Releasing

## 1) Bump Version

Update `version` in `pyproject.toml`.

## 2) Validate Locally

```bash
python -m ruff check .
python -m pytest -q
python -m build
python -m twine check dist/*
```

## 3) Publish Source Changes

```bash
git add .
git commit -m "Release vX.Y.Z"
git push origin main
```

## 4) Create Tag

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

## 5) Verify GitHub Actions

- `CI` workflow passes on `main`
- `Release` workflow passes on tag (or manual dispatch with required `tag` input)
- GitHub release contains:
  - wheel (`.whl`)
  - source dist (`.tar.gz`)

## 6) Verify Repository Guards

- `main` branch protection is enabled
- PR review requirement is enabled
- required status checks include CI matrix jobs
