import nox

nox.options.default_venv_backend = "uv"
nox.options.reuse_existing_virtualenvs = True


PYTHON_VERSIONS = ["3.11", "3.12", "3.13", "3.14"]


@nox.session(python=PYTHON_VERSIONS, tags=["tests"])
def tests(session):
    session.run_install(
        "uv",
        "sync",
        "--all-extras",
        "--group",
        "test",
        f"--python={session.virtualenv.location}",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    session.run("pytest", *session.posargs, env={"PYTHON_GIL": "1"})


@nox.session(python=["3.14t"], tags=["ft_tests"])
def free_threaded_tests(session):
    session.run_install(
        "uv",
        "sync",
        "--all-extras",
        "--group",
        "test",
        f"--python={session.virtualenv.location}",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    session.run("pytest", *session.posargs, env={"PYTHON_GIL": "0"})


@nox.session(tags=["lint"], python="3.11")
def lint(session: nox.Session):
    session.run_install("uv", "pip", "install", "ruff")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session(tags=["style"], python="3.11")
def apply_style(session: nox.Session):
    session.run_install("uv", "pip", "install", "ruff")
    session.run("ruff", "check", "--fix", ".")
    session.run("ruff", "format", ".")


@nox.session(tags=["type"], python="3.11")
def type_check(session: nox.Session):
    session.run("uv", "sync", "--active", "--all-extras", "--all-groups")
    session.run("pyrefly", "check")


@nox.session(tags=["quality", "static_analysis"], python="3.11")
def quality(session: nox.Session):
    """Run linting, formatting check, and type check."""
    session.run("uv", "sync", "--active", "--all-extras", "--all-groups")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")
    session.run("pyrefly", "check")


@nox.session(python="3.11", tags=["coverage"])
def coverage(session: nox.Session):
    import os
    import re

    session.run_install(
        "uv",
        "sync",
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
    if not match:
        session.error("Could not parse coverage percentage from output")

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


@nox.session(tags=["precommit"])
def precommit(session: nox.Session):
    """Run quality session, followed by all tests and free-threaded tests."""
    session.notify("quality")
    for py in PYTHON_VERSIONS:
        session.notify(f"tests-{py}")
    session.notify("free_threaded_tests")
    session.notify("coverage")
