# Security policy

python-discovery is a Python library that finds Python interpreters on a machine and reports their metadata. This policy
says how to report a security problem and how we decide whether a report is one.

## Reporting a vulnerability

**Do not open a public issue for a security problem.** Use
[GitHub's private vulnerability reporting](https://github.com/tox-dev/python-discovery/security/advisories/new). If
neither works for you, email [gaborjbernat@gmail.com](mailto:gaborjbernat@gmail.com).

Include what the attacker controls and what they gain, the steps or a proof of concept, and the versions and platform
you tested. Write the report yourself; unreviewed tool or model output takes longer to triage.

## What to expect

Volunteers maintain python-discovery, with no on-call rotation. We aim to acknowledge a report within **5 working days**
and assess it within **15 working days**. Fixes are developed in a private fork attached to the draft advisory, ship in
a new release, and the advisory, with a CVE requested through GitHub, goes out with that release. The default embargo is
**90 days** from the report; we agree any change with the reporter. We credit reporters in the advisory under the name
they choose, or not at all. There is no bug bounty.

## Supported versions

Only the latest release receives fixes. Confirm the problem reproduces on it before reporting.

## Vulnerability or bug

A report is a vulnerability when an attacker who controls only an input that the [threat model](THREAT_MODEL.md) lists
as untrusted breaks a guarantee python-discovery makes. A report that first needs control of something the threat model
trusts, such as an executable on `PATH` or in a version manager's directory, is a bug: we fix it in the open and publish
no advisory. Classify by who supplies the dangerous input, not by how bad the outcome sounds.

**In scope**

- Executing a binary from a location the documented search order does not include, such as the current directory through
  an empty `PATH` entry.
- A cache entry from one interpreter being reported for another, or surviving a change of the binary.
- Interrogation output from one candidate being parsed as another candidate's metadata.
- A spec's version, implementation, architecture, free-threading or debug constraint passing for a shim or launcher
  while the interpreter it resolves to fails it.
- A PEP 514 record or a spec making discovery run a program other than the candidate with its registered arguments.
- Another local user writing a shared cache directory so a victim accepts an interpreter, or metadata, that discovery
  would otherwise reject.
- A small candidate response exhausting memory or processes.

**Out of scope**

- A malicious interpreter in a searched location: python-discovery runs candidates to learn about them, so whoever can
  place one there already runs code as the user.
- Values in the process environment (`PATH`, `PYENV_ROOT`, `UV_PYTHON_INSTALL_DIR`, `PY_DISCOVERY_TIMEOUT`) and the
  Windows registry entries of PEP 514.
- A `.python-version` file choosing among interpreters that discovery would find anyway.
- Tampering with a cache directory only the caller can write.

If you cannot tell which side a finding falls on, report it privately and we will decide.
