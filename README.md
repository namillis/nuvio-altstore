# Nuvio — Unofficial AltStore Source

[![One-tap install](https://img.shields.io/badge/Install-one--tap-4F7CFF)](https://namillis.github.io/nuvio-altstore/)
[![AltStore source](https://img.shields.io/badge/AltStore-source-4F7CFF)](https://namillis.github.io/nuvio-altstore/nuvio-ios.json)
[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-live-2ea44f)](https://namillis.github.io/nuvio-altstore/)
[![Update source](https://github.com/namillis/nuvio-altstore/actions/workflows/source-updater.yml/badge.svg)](https://github.com/namillis/nuvio-altstore/actions/workflows/source-updater.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![iOS](https://img.shields.io/badge/iOS-Nuvio-4F7CFF)](nuvio-ios.json)

An **unofficial, community-maintained AltStore-format source** for [Nuvio](https://nuvio.tv/) on iPhone and iPad. Nuvio is a free, open-source media app that turns your own sources into a library with artwork, ratings, subtitles, and synchronized progress.

IPAs are downloaded directly from Nuvio's public GitHub releases. This repository publishes source metadata only and is not affiliated with or supported by NuvioMedia.

## Quick start

### One-tap install

Open the live installation page on your iPhone or iPad:

[**Add Nuvio source →**](https://namillis.github.io/nuvio-altstore/)

The page can open the source directly in AltStore, SideStore, or LiveContainer. It also provides a copy button for other signing apps.

### Add the source manually

Paste the live source URL into your signing app's **Sources** or **Repositories** section:

```text
https://namillis.github.io/nuvio-altstore/nuvio-ios.json
```

Raw GitHub fallback:

```text
https://raw.githubusercontent.com/namillis/nuvio-altstore/main/nuvio-ios.json
```

## Available app

| App | Bundle identifier | Latest version | Minimum iOS | Upstream |
|---|---|---:|---:|---|
| Nuvio | `com.nuvio.media` | 0.4.11 (build 115) | 16.1 | [NuvioMobile](https://github.com/NuvioMedia/NuvioMobile/releases) |

## Compatible signing apps

Any signing app that consumes the standard AltStore source format can use this repository. Known-compatible options include:

- **[AltStore Classic](https://altstore.io/)** — the original desktop-paired signer, using AltServer on a Mac or PC
- **[AltStore PAL](https://altstore.io/)** — AltStore's alternative app marketplace for users in the European Union
- **[Scarlet](https://usescarlet.com/)** — an on-device IPA installer
- **[Sideloadly](https://sideloadly.io/)** — a desktop-based sideloader with source support
- **[LiveContainer](https://github.com/LiveContainer/LiveContainer)** — an app launcher that imports and runs compatible IPA files inside a container

Apps that accept a source URL can use the hosted JSON directly.

## Metadata verification

Published metadata is read directly from each IPA's main `Info.plist`, including:

- Bundle identifier
- Marketing version and build number
- Minimum supported iOS version
- iPhone and iPad device support
- Download size
- SHA-256 integrity hash

The source uses version-pinned GitHub release URLs so a future release cannot silently change an older entry's file, size, or hash.

## Live endpoints

GitHub Pages is deployed by the updater workflow and serves both the installation page and source JSON.

| Resource | Live URL |
|---|---|
| One-tap installation page | [namillis.github.io/nuvio-altstore/](https://namillis.github.io/nuvio-altstore/) |
| AltStore source JSON | [namillis.github.io/nuvio-altstore/nuvio-ios.json](https://namillis.github.io/nuvio-altstore/nuvio-ios.json) |
| Raw JSON fallback | [raw.githubusercontent.com/.../nuvio-ios.json](https://raw.githubusercontent.com/namillis/nuvio-altstore/main/nuvio-ios.json) |

GitHub Pages serves the source with an `application/json` content type. Deployments may take up to 10 minutes to propagate through the Pages cache after an update.

## Repository contents

```text
nuvio-altstore/
├── .github/workflows/source-updater.yml
├── scripts/
│   ├── test_update_nuvio.py
│   └── update_nuvio.py
├── README.md
├── LICENSE
├── install.html
└── nuvio-ios.json
```

## Limitations

- **Unofficial source:** NuvioMedia does not maintain or support this repository.
- **Sporadic iOS assets:** Most upstream releases are Android-only. The updater keeps the newest stable release that actually includes an IPA.
- **Sideloading requirements:** You need a compatible signing app and Apple ID.
- **Signature expiry:** Apps signed with a free Apple ID normally expire after 7 days. Paid developer signatures can last up to 1 year.
- **Upstream dependency:** Downloads stop working if NuvioMedia removes or renames its GitHub release assets.

## Links

- [Nuvio website](https://nuvio.tv/)
- [NuvioMobile source code](https://github.com/NuvioMedia/NuvioMobile)
- [NuvioMobile releases](https://github.com/NuvioMedia/NuvioMobile/releases)
- [AltStore](https://altstore.io/)
- [SideStore](https://sidestore.io/)
- [LiveContainer](https://github.com/LiveContainer/LiveContainer)

## License and attribution

This metadata repository is licensed under the [MIT License](LICENSE).

Nuvio belongs to NuvioMedia and is licensed separately under GPL-3.0. AltStore, SideStore, and LiveContainer belong to their respective projects. Their names and assets are used only to identify compatibility and upstream downloads.
