# Contributing Guide

Thank you for your interest in Keynote-MCP! We welcome and appreciate all forms of contribution.

## How to Contribute

### Report Issues
- Use [GitHub Issues](https://github.com/ByAxe/keynote-mcp/issues) to report bugs
- Please include as much detail as possible:
  - macOS version
  - Python version
  - Keynote version
  - Error messages and steps to reproduce

### Feature Requests
- Use the "Feature Request" template in Issues
- Describe the feature you'd like in detail
- Explain the use case and value

### Code Contributions
1. Fork the project
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Create a Pull Request

## Development Setup

### 1. Clone the project
```bash
git clone https://github.com/andyyaro/mcp-keynote.git
cd mcp-keynote
```

### 2. Install dependencies ([uv](https://docs.astral.sh/uv/) required)
```bash
uv sync --dev
pre-commit install   # optional but recommended
```

### 3. Run the checks
```bash
make test              # unit tests (no Keynote needed)
make check             # everything CI runs: ruff, mypy --strict, coverage gate
make test-integration  # against a REAL Keynote - local only, steals window focus
```

## Coding Standards

- `ruff` handles linting and formatting (`make format`); `mypy --strict`
  must pass on `src/`.
- **Never interpolate user strings into AppleScript source.** Pass them as
  osascript argv (see `utils/applescript_runner.py`); numbers only after
  validation. `tests/unit/test_injection.py` enforces this.
- No `print()` in `src/` — stdout is the JSON-RPC channel; log to stderr.

## Testing

- Unit tests (`tests/unit/`) must run without Keynote or a GUI - mock the
  runner with the fixtures in `tests/conftest.py`.
- Integration tests (`tests/integration/`) are marked `keynote` and
  deselected by default; they may only create documents under `.scratch/`
  and must close them without saving.
- New tools need: schema + method + dispatch case + unit tests + a verified
  row in `docs/TOOL_MATRIX.md`.

## Commit Convention

### Commit Message Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Commit Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation update
- `style`: Code formatting changes
- `refactor`: Code refactoring
- `test`: Test-related changes
- `chore`: Build process or tooling changes

### Example
```
feat(unsplash): add image search functionality

- Implement Unsplash API integration
- Support keyword search
- Support image orientation filtering

Closes #123
```

## Pull Request Process

### Pre-submission Checklist
- [ ] Code passes all tests
- [ ] Code follows formatting standards
- [ ] Necessary tests have been added
- [ ] Related documentation has been updated
- [ ] Commit messages follow the convention

### PR Description
Please include in your PR:
- Brief description of changes
- Related Issue number
- Test instructions
- Screenshots (if applicable)

### Code Review
- All PRs require code review
- At least one maintainer approval is needed
- Automated tests must pass

## Community Guidelines

### Code of Conduct
- Respect all participants
- Use inclusive language
- Accept constructive criticism
- Focus on what's best for the community

### Communication
- Use GitHub Issues for public discussion
- Maintain a friendly and professional attitude
- Respond promptly to comments and feedback

## Contact

If you have any questions:

- Create a [GitHub Issue](https://github.com/ByAxe/keynote-mcp/issues)

Thank you for contributing! Every PR, Issue, and suggestion makes this project better.
