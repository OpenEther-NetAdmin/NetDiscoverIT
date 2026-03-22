# Testing Guide

This guide covers testing procedures for NetDiscoverIT, including running tests, writing new tests, and maintaining test coverage.

## Running Tests

All tests run within Docker containers to ensure consistent environments.

### Run All Tests

```bash
make test
```

### Run Tests with Coverage

```bash
make test-cov
```

Coverage reports are generated in `htmlcov/`.

### Run Specific Test File

```bash
pytest tests/path/test_file.py -v
```

### Run Specific Test

```bash
pytest tests/path/test_file.py::test_name -v
```

## Test Structure

Tests are organized in the `tests/` directory:

```
tests/
├── agent/              # Agent service tests
│   ├── fixtures/       # Test configuration files
│   ├── test_sanitizer_*.py
│   └── ...
├── api/               # API service tests
│   ├── api/           # API endpoint tests
│   ├── core/          # Core functionality tests
│   └── tasks/         # Background task tests
└── ...
```

## Agent Service Tests

### Sanitizer Tests

The sanitizer module has comprehensive test coverage:

- `test_sanitizer_with_fixtures.py` - Integration tests with fixture configs
- `test_sanitizer_units.py` - Unit tests for individual components

### Fixtures

Test fixtures are in `tests/agent/fixtures/`:

- `cisco_ios_router.cfg` - Sample Cisco IOS configuration
- `juniper_junos_router.cfg` - Sample Juniper JunOS configuration

These fixtures contain realistic network device configurations with sensitive data that should be sanitized.

### Writing Tests

Follow this pattern for new tests:

```python
import pytest
from agent.sanitizer import ConfigSanitizer

class TestSanitizerBehavior:
    @pytest.fixture
    def sanitizer(self):
        return ConfigSanitizer(org_id="test-org")

    def test_something(self, sanitizer):
        config = "device config with sensitive data"
        result = sanitizer.sanitize(config)
        assert "<password>" in result["sanitized"]
```

## API Service Tests

### Running API Tests

```bash
pytest tests/api/ -v
```

### Test Fixtures

API tests use pytest fixtures defined in `tests/conftest.py`. These provide database sessions, test clients, and authentication.

## Test Best Practices

1. **Use descriptive names** - Test names should describe what is being tested
2. **Test both success and failure** - Cover error cases, not just happy paths
3. **Keep tests isolated** - Each test should be independent
4. **Use fixtures** - Reusable test data goes in fixtures
5. **Assert specifically** - Check exact values, not just that no exception raised
6. **Maintain coverage** - Aim for >80% coverage on new code

## Coverage Requirements

- New code should have >80% coverage
- Critical paths (sanitizer, auth) should have >90% coverage
- Include coverage reports in PR reviews

## Continuous Integration

Tests run automatically on:

- Pull requests
- Pushes to main branch
- Scheduled nightly runs

## Troubleshooting

### Tests Fail in Container

Ensure you're running tests inside the container:

```bash
docker compose exec api pytest tests/
```

### Import Errors

Ensure Python path includes the service directory:

```bash
docker compose exec api python -c "import sys; print(sys.path)"
```

### Database Errors

Reset the test database:

```bash
make db-migrate
```