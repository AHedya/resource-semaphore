import nox

nox.options.default_venv_backend = "uv"
nox.options.reuse_existing_virtualenvs = True
nox.options.allow_parallel = True

DEV_PYTHON = "3.11"
PYTHON_VERSIONS = ["3.11", "3.12", "3.13", "3.14", "3.15"]
FT_PYTHON_VERSIONS = ["3.13t", "3.14t", "3.15t"]


@nox.session(python=PYTHON_VERSIONS, tags=["tests", "all_tests"])
def tests(session: nox.Session):
    session.run_install(
        "uv",
        "sync",
        "--active",
        "--locked",
        "--all-extras",
        "--group",
        "test",
    )
    session.run("pytest", *session.posargs, env={"PYTHON_GIL": "1"})


@nox.session(python=FT_PYTHON_VERSIONS, tags=["ft_tests", "all_tests"])
def free_threaded_tests(session: nox.Session):
    session.run_install(
        "uv",
        "sync",
        "--active",
        "--locked",
        "--all-extras",
        "--group",
        "test",
    )
    session.run("pytest", *session.posargs, env={"PYTHON_GIL": "0"})


@nox.session(tags=["lint", "precommit", "quality"], python=DEV_PYTHON)
def lint(session: nox.Session):
    session.run_install(
        "uv",
        "sync",
        "--active",
        "--locked",
        "--only-group",
        "dev",
    )
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session(tags=["type", "precommit", "quality"], python=DEV_PYTHON)
def type_check(session: nox.Session):
    session.run_install(
        "uv",
        "sync",
        "--active",
        "--locked",
        "--all-extras",
        "--all-groups",
    )
    session.run("pyrefly", "check")


@nox.session(tags=["style"], python=DEV_PYTHON, default=False, allow_parallel=False)
def apply_style(session: nox.Session):
    session.run_install(
        "uv",
        "sync",
        "--active",
        "--locked",
        "--only-group",
        "dev",
    )
    session.run("ruff", "check", "--fix", ".")
    session.run("ruff", "format", ".")


@nox.session(
    python=DEV_PYTHON,
    tags=["coverage"],
    default=False,
    allow_parallel=False,
)
def coverage(session: nox.Session):
    import os
    import re

    session.run_install(
        "uv",
        "sync",
        "--active",
        "--locked",
        "--all-extras",
        "--group",
        "test",
    )

    output = session.run(
        "pytest",
        "--cov=src/",
        "--cov-report=term",
        env={"COVERAGE_FILE": ".nox/.coverage"},
        silent=True,
    )
    assert output is not None
    match = re.search(r"TOTAL.*?(\d+)%", output)
    if match is None:
        session.error("Could not parse coverage percentage from output")
        return

    pct = int(match.group(1))

    for f in ["coverage.json", ".coverage"]:
        try:
            os.remove(f)
        except FileNotFoundError:
            pass

    if pct >= 95:
        color = "brightgreen"
    elif pct >= 90:
        color = "green"
    elif pct >= 80:
        color = "yellowgreen"
    elif pct >= 70:
        color = "yellow"
    elif pct >= 60:
        color = "orange"
    else:
        color = "red"

    badge_url = f"https://img.shields.io/badge/Coverage-{pct}%25-{color}.svg"

    with open("README.md") as f:
        readme = f.read()

    new_readme = re.sub(
        r"!\[Coverage\]\(https://img\.shields\.io/badge/Coverage-[^\)]+\)",
        f"![Coverage]({badge_url})",
        readme,
    )

    with open("README.md", "w") as f:
        f.write(new_readme)

    print(f"Updated README.md coverage badge to {pct}% ({color})")


@nox.session(
    python=DEV_PYTHON,
    tags=["prepush"],
    default=False,
    allow_parallel=False,
    venv_backend="none",
)
def prepush(session: nox.Session):
    """Run local pre-push checklist: precommit, all tests, coverage, and clean working tree."""
    print("\n" + "=" * 50)
    print("🚀 [1/3] Running precommit quality checks (lint + type_check)...")
    print("=" * 50)
    session.run("nox", "-t", "precommit", "-j", "auto", external=True)

    print("\n" + "=" * 50)
    print("🧪 [2/3] Running all tests (3.11-3.15, 3.13t-3.15t in parallel)...")
    print("=" * 50)
    session.run("nox", "-t", "all_tests", "-j", "auto", external=True)

    print("\n" + "=" * 50)
    print("📊 [3/3] Updating test coverage & checking README.md badge...")
    print("=" * 50)
    session.run("nox", "-s", "coverage", external=True)

    try:
        session.run("git", "diff", "--exit-code", "README.md", external=True)
    except Exception:
        session.error(
            "README.md coverage badge was updated! Please stage and commit the updated README.md before pushing."
        )

    print("\n" + "=" * 50)
    print("✅ Pre-Push Checklist Passed:")
    print("  ✓ Precommit quality checks (lint + type_check)")
    print("  ✓ All tests passed across all supported Python versions")
    print("  ✓ Coverage badge is synchronized with README.md")
    print("=" * 50 + "\n")
