# Code signing policy

Status: **unsigned; no SignPath Foundation acceptance or certificate yet**.

## Responsibilities

- Maintainer, author and reviewer: GitHub user **Delnoij**, as designated by the owner.
- Release and signing approver: **Delnoij**. Signing must require a deliberate human approval for each release.
- There is currently one maintainer; an independent reviewer has not been appointed. Do not claim independent review until it has taken place. External contributions must go through reviewed pull requests.

## Build and release rules

Only builds from this project's reviewed source revision are eligible for submission. Dependencies, the installer compiler and Actions revisions are pinned. The workflow runs tests and source checks, records provenance and creates unsigned review artifacts. Modified release binaries must go through a new build and review. Proposed signing targets are the application's own executable and its installer/uninstaller built from this repository's installation script. Third-party DLLs are not signed as if maintained by this project. Verification and checksums must be regenerated after signing. See [RELEASING.md](RELEASING.md) for the required order and outstanding integration.

Current Windows packages are unsigned. No keys or tokens are stored in the repository. Repository and signing accounts must use multifactor authentication. A person must explicitly approve a signing request; no pull-request event may request a production signature. Current CI has no signing credentials and no publishing permission.

## Privacy and credits

See [PRIVACY.md](PRIVACY.md). Signing-service credits will be added only after actual acceptance and configuration. We make no present claim of free signing, a SignPath certificate, or a verified publisher.

The project repository is [Delnoij/RouteRefit](https://github.com/Delnoij/RouteRefit). Marco Delnoij is a private individual in the Netherlands. A signing application will follow only after reviewed public builds, testing and a separate decision by the maintainer.
