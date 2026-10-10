# Security Policy

## Supported versions

Only the latest release of `docrot` is supported with security fixes.

## Reporting a vulnerability

Please do **not** open a public issue for security vulnerabilities.

Report privately via GitHub's [Security Advisories](https://github.com/auroraxo/docrot/security/advisories/new) or by email to **aurora@sprintcx.de**.

You will receive an acknowledgement within 72 hours. Once a fix is verified, we will publish the advisory and credit the reporter (unless anonymity is requested).

## Scope

- Scanner false negatives/positives that mislead security decisions are treated as bugs;phantom results are treated as defects per CONTRIBUTING.md.
- The scan API must never fetch credentials or execute fetched content.
