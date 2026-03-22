# Testing Guidelines

## Framework

- pytest with asyncio support
- Tests directory at repo root (`tests/`)

## Running Tests

```bash
make test                          # Run all tests
make test-cov                      # Run tests with coverage report
pytest tests/path/test_file.py::test_name -v   # Single test
```

## Coverage

- Coverage target: include in PR reviews
- Aim for >80% coverage on new code

## Agent Service Tests

Tests for the agent service are located in `tests/agent/`:

```
tests/
├── agent/
│   ├── fixtures/           # Test config files
│   ├── test_sanitizer_*.py
│   └── ...
└── api/                    # API tests
```

## Best Practices

- Use fixtures for reusable test data
- Test both success and failure cases
- Mock external dependencies
- Keep tests isolated and independent
