# Contributing to UFCStats Parser

Thank you for considering contributing to **UFCStats Parser**! We welcome bug reports, feature suggestions, documentation improvements, and pull requests.

## How to Contribute

### 1. Reporting Bugs
- Search existing issues to ensure the bug hasn't been reported.
- Open a new issue using the **Bug Report** template.
- Include Python version, OS, CLI command executed, and error log traceback.

### 2. Suggesting Features
- Open a new issue using the **Feature Request** template.
- Describe the use case and why this feature would benefit users.

### 3. Submitting Pull Requests
1. Fork the repository and create a feature branch (`git checkout -b feature/amazing-feature`).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the pytest suite to ensure all tests pass:
   ```bash
   pytest
   ```
4. Commit your changes following clean commit messages.
5. Push to your branch and open a Pull Request.

## Code Style Guidelines

- Follow PEP 8 standards.
- Ensure all function parameters and return types use type hints where appropriate.
- Include unit tests in `tests/` for new parser logic or storage handlers.
