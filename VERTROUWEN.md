# Windows signing and trust

This beta is not digitally signed. A SHA-256 checksum verifies that a file matches
the published bytes; it does not verify the publisher's identity.

A trusted code-signing certificate is needed for a verified publisher name.
SmartScreen also considers file/publisher reputation. A correctly signed new
application may still trigger warnings. A self-signed certificate does not solve
this for public distribution.

RouteRefit's source, release information, network behaviour, tests, limitations
and checksums are public. GPL-3.0-only is included; personal GPX files and map caches
are excluded. See the [code signing policy](CODE-SIGNING-POLICY.md) and
[SignPath preparation](SIGNPATH-VOORBEREIDING.md).

No signing certificate, SignPath acceptance or active signing integration is
claimed. Do not disable Windows security to run the application. A beta label,
passing tests or antivirus scan does not replace signing or provenance review.

Official background information:
- https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation
- https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options
- https://signpath.org/terms.html
