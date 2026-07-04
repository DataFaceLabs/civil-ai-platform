# CLAUDE.md for civil-ai-platform

**Canonical file: [`AGENTS.md`](AGENTS.md).** Claude Code auto-loads `CLAUDE.md`, so this
file exists to make sure it does — but `AGENTS.md` is where the real, maintained
instructions live (boundaries, security rules, IaC rules). Read that first. Don't
duplicate its content here; if you're tempted to add a rule, add it to `AGENTS.md`.

If you only read five lines: branch off `develop` (`feature/*`/`chore/*`/`fix/*`), never
commit directly to `develop`/`main`. Run `make gauntlet` before every push. Match
`civil-ai-data/CLAUDE.md`'s coding standards in spirit (complete type annotations, no
bare `except: pass`, tests use mocks not live network calls). Browser clients must never
receive AWS credentials; Athena/lake access is mediated through approved backend
contracts, never direct from a client.
