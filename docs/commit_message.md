feat: add Python 3.15, 3.15t, 3.13t support and optimize CI/Nox workflows (v1.4.0)

- Bump version to 1.4.0 and relax Python requirement to <3.16,>=3.11
- Add official support and matrix testing for Python 3.15, 3.15t, and 3.13t
- Optimize GitHub Actions CI to single-runner parallel execution using uv + nox
- Harden noxfile sessions with --locked and guard mutating sessions against parallel runs
- Introduce on-demand prepush checklist session (lint, type check, full test matrix, coverage)
- Configure fast, non-mutating pre-commit hook (lint + type check)
- Strengthen publish workflow with tomllib tag validation and uv lock --check
- Set package version fallback to sentinel "0.0.0+dev0" when uninstalled
- Add PyPI classifiers for Free Threading, OS Independent, and CPython implementation
