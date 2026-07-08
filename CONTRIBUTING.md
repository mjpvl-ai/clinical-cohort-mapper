# Contributing Guidelines

Thank you for your interest in contributing to the **Clinical Cohort Query Mapper (CDGR)**! We welcome bug reports, feature requests, documentation improvements, and code contributions.

Please follow these guidelines to set up your environment, follow code style standards, and submit pull requests.

---

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please report any unacceptable behavior to [engineering@srotas.ai](mailto:engineering@srotas.ai).

---

## Getting Started

### Prerequisites
- Python 3.11 or 3.12
- [uv](https://docs.astral.sh/uv/) (highly recommended for dependency management)

### Development Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/mjpvl-ai/clinical-cohort-mapper.git
   cd clinical-cohort-mapper
   ```

2. Create a virtual environment and install development dependencies:
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
   uv pip install -e ".[dev]"
   ```

3. Install the pre-commit hooks:
   ```bash
   uv run pre-commit install
   ```

---

## Code Quality Standards

We use [Ruff](https://github.com/astral-sh/ruff) for linting and code formatting.

### Formatting
Check formatting without applying changes:
```bash
uv run ruff format --check .
```

Auto-format files:
```bash
uv run ruff format .
```

### Linting
Run static analysis and check for quality issues:
```bash
uv run ruff check .
```

Automatically fix safe lint issues:
```bash
uv run ruff check --fix .
```

---

## Testing

We use [pytest](https://docs.pytest.org/) for automated testing.

Run all tests:
```bash
uv run pytest tests/ -v
```

Ensure all tests pass successfully before submitting a pull request.

---

## Pull Request Process

1. Create a new branch for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-name
   ```
2. Commit your changes. Ensure commit messages are clear, concise, and descriptive.
3. Keep your branch up to date with the `main` branch.
4. Run formatting, linting, and tests to verify your changes.
5. Push to your fork and submit a Pull Request to the `main` branch.
6. A maintainer will review your pull request shortly.
