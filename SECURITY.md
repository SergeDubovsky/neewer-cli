# Security Policy

## Supported Versions

Security fixes are provided for the latest released version and the current `main` branch.

| Version | Supported |
| --- | --- |
| `main` | Yes |
| Latest release | Yes |
| Older releases | No |

## Reporting a Vulnerability

Do not open public issues for security vulnerabilities.

Please report privately via:

- GitHub Security Advisories: https://github.com/SergeDubovsky/neewer-cli/security/advisories/new

Include:

- affected version
- reproduction steps
- expected and actual behavior
- potential impact

## Triage and Response Targets

- Initial acknowledgment: within 72 hours
- Triage outcome and severity assessment: within 7 days
- Remediation timeline: shared after triage

Severity is assessed using impact, exploitability, and affected surface area.

## Disclosure Policy

- Please allow time for a fix before public disclosure.
- After a fix is available, maintainers will publish a coordinated advisory.
- Credit is given to reporters unless they request anonymity.

## Scope

This project is a local BLE CLI utility. Security reports are most useful when they involve:

- unsafe handling of untrusted input/config
- credential/token leakage risks
- supply chain risks in build/release workflows
- command execution or privilege escalation paths
