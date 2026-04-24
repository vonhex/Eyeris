# Security Policy

## Supported Versions

Currently, only the latest release of Eyeris is supported for security updates.

| Version | Supported          |
| ------- | ------------------ |
| v1.1.x  | :white_check_mark: |
| < v1.1  | :x:                |

## Reporting a Vulnerability

**Do not open a GitHub Issue for security vulnerabilities.**

If you discover a potential security risk, please report it privately by emailing **lucashjantzen@gmail.com**.

Please include:
- A description of the vulnerability.
- Steps to reproduce the issue.
- Potential impact if exploited.

I will acknowledge your report within 48 hours and provide a timeline for a fix.

## Security Assumption
As noted in the README, Eyeris is designed for **trusted local networks only**. It does not currently include:
- Rate limiting or brute-force protection.
- Multi-user RBAC (Role-Based Access Control).
- Encrypted internal communication (HTTPS should be handled by your own reverse proxy like Nginx or Traefik).

Always run Eyeris behind a VPN or a secure tunnel (like Cloudflare Access) if remote access is required.
