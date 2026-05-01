# Contributing to Eyeris

Thanks for taking the time to contribute. Here's everything you need to know.

## Before you start

- **Bug fix or small improvement?** Open a PR directly — no need to ask first.
- **New feature or significant change?** Open an issue first to discuss it. Avoids wasted effort if the direction doesn't fit the project.
- **Question or help needed?** Use [GitHub Discussions](https://github.com/vonhex/Eyeris/discussions) rather than opening an issue.

## Development setup

```bash
# Clone and set up
git clone https://github.com/vonhex/Eyeris.git
cd Eyeris
cp .env.example .env   # fill in your NAS / DB / Ollama details

# Start backend + frontend together
./start.sh

# Or separately:
source venv/bin/activate && cd backend && uvicorn main:app --reload
cd frontend && npm run dev
```

- Frontend dev server: http://localhost:5173
- Backend API + Swagger docs: http://localhost:8000/docs

## How to contribute

1. Fork the repository and create a branch from `main`
2. Make your changes — keep them focused on one thing per PR
3. Test your changes locally (both the happy path and edge cases)
4. Run the frontend linter: `cd frontend && npm run lint`
5. Open a pull request against `main` using the PR template

## What makes a good PR

- **Focused** — one logical change per PR; easier to review and revert if needed
- **No scope creep** — don't refactor surrounding code unless it's directly related
- **No unnecessary comments** — code should be self-explanatory; only comment the *why* when it's non-obvious
- **No new dependencies** without a good reason — every added package is a maintenance burden
- **Test the UI** — if you changed the frontend, actually open a browser and use it

## Code style

- **Backend (Python):** Follow existing patterns. Type hints where they add clarity. No docstrings on obvious functions.
- **Frontend (React + Tailwind):** Match the existing component style. Keep components small and single-purpose.
- Formatting is not enforced by CI yet — just try to match the surrounding code.

## Reporting bugs

Use the **Bug Report** issue template. The more detail you provide (logs, steps to reproduce, Docker version, Unraid version if applicable), the faster it gets fixed.

## Feature requests

Use the **Feature Request** issue template. Explain the use case, not just the solution — there may be a better way to solve the underlying problem.

## License note

By contributing, you agree that your contributions will be licensed under the same [noncommercial license](../LICENSE) as the rest of the project.
