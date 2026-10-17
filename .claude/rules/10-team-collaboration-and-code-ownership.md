# 10-team-collaboration-and-code-ownership.md — Team Collaboration & Code Ownership Standards

## 1. Context & Core Philosophy (Meeting 16/10/2026, Point g)

- In team development without an overriding corporate framework, clear code ownership and respectful collaboration are mandatory to prevent regressions, merge conflicts, and accidental disruptions.
- All contributors (engineers and AI assistants) must strictly honor ownership boundaries and communicate proactively before altering existing functionality.

## 2. Dual-Zone Architecture: Shared Area vs. Personal Area

1. **Shared Area (Vùng Dùng Chung)**:
   - **Scope**: Core project configuration (`config/`), database definitions (`db/`), common domain models, base services/selectors, shared middlewares, common serializers, CI workflows (`.github/`), and project governance rules (`.claude/`).
   - **Governance**: Universal adherence to project coding conventions (PEP 8, Ruff, Mypy typing, 3-tier architecture). Changes affecting the Shared Area require prior team agreement and mandatory Pull Request review with at least 01 peer approval (`ADR-0002`).
2. **Personal Area (Vùng Độc Lập Cá Nhân)**:
   - **Scope**: Dedicated feature/bugfix branches (`feature/<issue-id>-*`, `bugfix/<issue-id>-*`), module-specific services assigned to a single developer, and individual test cases.
   - **Governance**: The assigned author has full autonomy in technical organization within their scope, provided they honor established API contracts, database schemas, and shared interfaces.

## 3. Principles of Code Ownership & Respectful Collaboration

- **Zero Unauthorized Modifications**: Never modify, refactor, or delete another team member's code, schema, or feature without explicit prior consent from the author.
- **Read-Understand-Ask Workflow**: Before reading another member's code with the intention to modify or remove it, you MUST thoroughly study its original design rationale and proactively discuss/ask the author for alignment.
- **Branch & PR Ownership**: Each feature branch belongs strictly to its designated owner. Never commit or push directly to another member's branch without authorization.

## 4. AI Agent Scope Governance & Operational Boundaries

- **Strict Task Scope Boundary**: An AI agent is strictly forbidden from creating or modifying files outside the explicit scope of its assigned task or designated subfolder.
- **Foreign Area Inviolability**: An AI agent must NEVER touch files belonging to another member's module or feature branch without explicit, verifiable instruction from the Owner or Team Lead.
- **File Boundary Pre-Verification**: Before executing any file write/edit tool, the AI agent must verify that the target path falls strictly within its authorized working area.
