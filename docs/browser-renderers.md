# Browser renderers

FormalPrompt serves one semantic HTML application. Renderer selection changes only how the local URL is opened.

## Graphical browser

`--renderer browser` calls the operating system's default web-browser integration. This is the normal choice on Windows, macOS, and graphical Linux desktops.

The UI uses native inputs, keyboard-operable ARIA tabs, text provenance badges, reduced-motion support, forced-color fallbacks, and responsive layout. Document strings are assigned through text nodes; agents cannot supply scripts or markup.

## Carbonyl

`--renderer carbonyl` requires a `carbonyl` executable on `PATH` and launches it with the canvas URL as one literal process argument. No shell is involved.

Upstream installation examples include:

```text
npm install --global carbonyl
carbonyl https://example.com
```

Carbonyl upstream currently publishes Linux and macOS binaries. Native Windows users should use Chrome or Edge; Carbonyl can be used from a compatible Linux environment such as WSL or a container. FormalPrompt does not silently install Carbonyl.

## Automatic selection

`--renderer auto` selects:

- graphical browser on native desktop sessions;
- Carbonyl for SSH or headless Linux when it is installed;
- URL-only mode for SSH or headless Linux without Carbonyl.

`--renderer none` always prints the URL and launches nothing. This supports port forwarding, automated tests, and callers that manage the browser themselves.

## Authentication

The ready URL places the per-run token in its fragment. URL fragments are not sent in HTTP requests. The application transfers the token to browser session storage, clears the fragment with `history.replaceState`, and sends the token only in the `Authorization` header for state APIs.

## Smoke testing

`scripts/browser-smoke.mjs` launches an isolated headless Chrome-family process, connects through the DevTools protocol, and exercises the full edit, validation, approval, and compilation journey. It does not use or modify the user's normal browser profile.

Carbonyl launcher selection and failure behavior are covered in `tests/test_launchers.py`. A true terminal-rendering smoke test requires a Linux/macOS TTY with Carbonyl installed; native Windows CI must not claim that coverage.
