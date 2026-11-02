# SignPath preparation - no application submitted

RouteRefit 0.5.15 Beta is unsigned. Checksums establish file integrity, not a
verified publisher. SignPath Foundation offers free signing to accepted open-source
projects under its terms; acceptance of a new project is not guaranteed.

## Sequence

1. Publish reviewed GPL-3.0-only source in [Delnoij/RouteRefit](https://github.com/Delnoij/RouteRefit).
2. Run the GitHub Windows workflow, review its exact artifacts and publish a clearly
   labelled beta. Local builds alone do not establish hosted build provenance.
3. Gather real practical testing and project history. Apply using the actual
   repository, run, release, maintainer roles and privacy policy. Do not invent usage.
4. Only after acceptance, configure signing, artifact restrictions and deliberate
   approval for every release. Store credentials in protected settings, never source.
5. Verify signatures, timestamps and provenance. Recompute checksums after signing.

The current workflow produces unsigned files. No SignPath signing integration is
active. Responsibilities are documented in [CODE-SIGNING-POLICY.md](CODE-SIGNING-POLICY.md).

## Prepared

- GPL-3.0-only licence and separate dependency notices.
- Complete source, tests, pinned packages and a verified installer compiler.
- Empty route catalogue and reviewed synthetic demonstration assets.
- Per-user installer with privacy disclosure, optional actions and an uninstaller.
- Tests for installation, locked-file refusal, updates, retained user data,
  uninstallation and isolation from other installations' scheduled tasks.
- Public code signing policy linked from the README and release notes.

## Verify before applying

- The actual release files must match a successful hosted build and its source revision.
- MFA on GitHub and later SignPath, branch protection and effective permissions.
- Testing on a separate Windows 11 PC and genuine usage history or independent review.
  No established public reputation or independent reviewer is currently claimed.
- Network-consent requirements: visible map images can be fetched automatically,
  and the app has no global offline switch. Disclosure alone does not establish
  compliance with a signing provider's requirements; review or improve controls.
- SignPath acceptance, restrictions to the project's own files, and correct order
  for signing the application, uninstaller and enclosing installer.

Do not display acceptance or sponsorship credits before approval. Add required
credits only after acceptance. Do not claim unverified users, reviews, MFA or CI results.

Official sources, checked 2 November 2026: https://signpath.org/ and
https://signpath.org/terms.html . This is a possible next step, not an application,
promise of free signing or guarantee that signed software is free of defects.
