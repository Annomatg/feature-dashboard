# E2E Testing

## Browser Support

**Chromium only** - This project only tests on Chromium-based browsers (Chrome, Edge, etc.).

We do not support or test on:
- Firefox
- Safari
- WebKit

**Reason**: The user exclusively uses Chromium-based browsers, so cross-browser testing is unnecessary.

## Running Tests

```bash
# Run all tests
npm test

# Run tests in UI mode
npm run test:ui

# Run tests in headed mode (see browser)
npm run test:headed

# Debug tests
npm run test:debug

# Generate new test code
npm run test:codegen
```

## Configuration

See `playwright.config.js` for full configuration details.

Tests run against `http://localhost:5174` by default.
