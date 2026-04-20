# Contributing to Info-Spider

Thank you for your interest in contributing to Info-Spider! This document provides guidelines and instructions for contributing.

## 🤝 How to Contribute

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When creating a bug report, include:

- **Clear title and description** of the problem
- **Steps to reproduce** the issue
- **Expected behavior** vs. **actual behavior**
- **Environment details** (OS, Python version, browser type)
- **Logs/screenshots** if applicable

### Suggesting Enhancements

Enhancement suggestions are welcome! Please provide:

- **Clear description** of the suggested feature
- **Use cases** for the feature
- **Potential implementation** ideas (if you have any)

### Adding New Actors

We welcome contributions for new platforms! To add a new actor:

1. **Create the actor file** in `actors/your_platform_actor.py`
2. **Inherit from `BaseActor`** and implement required methods
3. **Register actions** using `self.register_action()`
4. **Add tests** in `tests/`
5. **Update documentation** in `README.md` and `config.yaml`

Example structure:
```python
from core.base_actor import BaseActor

class YourPlatformActor(BaseActor):
    actor_name = "your_platform_actor"
    actor_description = "Description here"

    def setup_actions(self):
        self.register_action("create", self.action_create, ...)

    async def action_create(self, task, params):
        # Your implementation
        pass
```

## 🛠️ Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/info-spider.git
cd info-spider

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install in development mode
pip install -e .

# Install development dependencies
pip install pytest black mypy flake8

# Install Playwright browsers
playwright install
```

## 📝 Code Style

- **PEP 8** compliant code
- **Black** for formatting (`black .`)
- **Type hints** where appropriate
- **Docstrings** for public methods and classes

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=core --cov=actors

# Run specific test file
pytest tests/test_actor.py
```

## 📤 Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add/update tests
5. Ensure all tests pass
6. Commit with clear messages
7. Push to your fork
8. Create a Pull Request

### Pull Request Checklist

- [ ] Code follows project style guidelines
- [ ] Tests added/updated and passing
- [ ] Documentation updated
- [ ] Commit messages are clear and descriptive
- [ ] No merge conflicts

## 📜 License

By contributing, you agree that your contributions will be licensed under the **MIT License**.

## 💬 Communication

- **GitHub Issues** - Bug reports and feature requests
- **GitHub Discussions** - General questions and ideas

Thank you for contributing! 🎉
