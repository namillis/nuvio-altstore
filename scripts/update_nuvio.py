from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import plistlib
import re
import shutil
import subprocess
import time
import urllib.request
import zipfile
from typing import Any, NamedTuple

UPSTREAM_REPO = "NuvioMedia/NuvioMobile"
SOURCE_REPO = "namillis/nuvio-altstore"
SOURCE_PATH = "nuvio-ios.json"
README_PATH = "README.md"
SOURCE_BRANCH = "main"
BUNDLE_IDENTIFIER = "com.nuvio.media"
MAX_IPA_SIZE = 200_000_000
MAX_RELEASE_PAGES = 5


class VerifiedRelease(NamedTuple):
    version: str
    build_version: str
    date: str
    notes: str
    caption: str
    download_url: str
    size: int
    sha256: str
    minimum_os_version: str


def _gh_api(endpoint: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError("GitHub CLI is not available")

    command = [gh, "api", endpoint]
    input_text = None
    if method != "GET":
        command.extend(["--method", method, "--input", "-"])
        input_text = json.dumps(payload)

    attempts = 1 if method != "GET" else 3
    for attempt in range(attempts):
        result = subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        if attempt + 1 < attempts:
            time.sleep(2**attempt)

    error = (result.stderr or result.stdout or "unknown GitHub API error").strip()
    raise RuntimeError(error[-1000:])


def _fetch_releases() -> list[dict[str, Any]]:
    releases: list[dict[str, Any]] = []
    for page in range(1, MAX_RELEASE_PAGES + 1):
        batch = _gh_api(f"repos/{UPSTREAM_REPO}/releases?per_page=100&page={page}")
        if not isinstance(batch, list):
            raise RuntimeError("GitHub returned an invalid releases response")
        releases.extend(batch)
        if len(batch) < 100:
            break
    return releases


def _select_latest_ipa_release(
    releases: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        published_at = str(release.get("published_at") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*", published_at):
            continue
        ipa_assets = [
            asset
            for asset in release.get("assets", [])
            if str(asset.get("name") or "").lower().endswith(".ipa")
        ]
        if ipa_assets:
            candidates.append((published_at, release, ipa_assets))

    if not candidates:
        raise RuntimeError("no stable Nuvio release with an IPA asset was found")

    _, release, ipa_assets = max(candidates, key=lambda item: item[0])
    if len(ipa_assets) != 1:
        tag = str(release.get("tag_name") or "unknown")
        raise RuntimeError(f"expected one IPA asset for release {tag}, found {len(ipa_assets)}")
    return release, ipa_assets[0]


def _download_ipa(url: str, expected_size: int) -> bytes:
    if expected_size <= 0 or expected_size > MAX_IPA_SIZE:
        raise RuntimeError(f"unexpected IPA size from release metadata: {expected_size}")

    request = urllib.request.Request(url, headers={"User-Agent": "nuvio-altstore-updater/1.0"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                data = response.read(MAX_IPA_SIZE + 1)
            if len(data) > MAX_IPA_SIZE:
                raise RuntimeError("IPA exceeds the maximum allowed size")
            if len(data) != expected_size:
                raise RuntimeError(f"IPA size mismatch: expected {expected_size}, downloaded {len(data)}")
            return data
        except Exception as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(f"IPA download failed: {last_error}")


def _normalize_notes(body: Any, version: str) -> tuple[str, str]:
    raw = str(body or "").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[*\-]\s+", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"^[0-9a-fA-F]{7,40}\s+", "", line)
        line = re.sub(r"\s+@[A-Za-z0-9_-]+$", "", line).strip()
        if line:
            lines.append(line)

    notes = "\n".join(lines) or f"Nuvio {version} release."
    caption = " · ".join(lines) or f"Nuvio {version} release"
    if len(caption) > 180:
        caption = caption[:177].rstrip() + "..."
    return notes, caption


def _verify_latest_ipa_release(source: dict[str, Any]) -> VerifiedRelease | None:
    release, asset = _select_latest_ipa_release(_fetch_releases())
    tag = str(release.get("tag_name") or "")
    version_from_tag = tag[1:] if tag.startswith("v") else tag
    if not re.fullmatch(r"\d+(?:\.\d+){1,3}", version_from_tag):
        raise RuntimeError(f"unsupported release tag: {tag}")

    expected_size = int(asset.get("size") or 0)
    download_url = str(asset.get("browser_download_url") or "")
    if not download_url.startswith(f"https://github.com/{UPSTREAM_REPO}/releases/download/"):
        raise RuntimeError("IPA download URL does not belong to the expected upstream repository")

    published_digest = str(asset.get("digest") or "")
    published_sha256 = ""
    if published_digest:
        digest_match = re.fullmatch(r"sha256:([0-9a-f]{64})", published_digest)
        if not digest_match:
            raise RuntimeError(f"unsupported GitHub asset digest: {published_digest}")
        published_sha256 = digest_match.group(1)

    published_at = str(release.get("published_at") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*", published_at):
        raise RuntimeError(f"invalid release publication date: {published_at}")
    notes, caption = _normalize_notes(release.get("body"), version_from_tag)

    app, latest = _current_app(source)
    if published_sha256 and (
        str(latest.get("version")) == version_from_tag
        and str(latest.get("downloadURL")) == download_url
        and int(latest.get("size") or 0) == expected_size
        and str(latest.get("sha256")) == published_sha256
        and str(latest.get("localizedDescription")) == notes
        and str(app.get("version")) == version_from_tag
        and str(app.get("downloadURL")) == download_url
        and int(app.get("size") or 0) == expected_size
        and str(app.get("versionDescription")) == notes
    ):
        return None

    ipa = _download_ipa(download_url, expected_size)
    digest = hashlib.sha256(ipa).hexdigest()
    if published_sha256 and published_sha256 != digest:
        raise RuntimeError("IPA SHA-256 does not match GitHub release metadata")

    with zipfile.ZipFile(io.BytesIO(ipa)) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if name.startswith("Payload/") and name.endswith(".app/Info.plist") and name.count("/") == 2
        ]
        if len(candidates) != 1:
            raise RuntimeError(f"expected one top-level app Info.plist, found {len(candidates)}")
        info = plistlib.loads(archive.read(candidates[0]))

    bundle_identifier = str(info.get("CFBundleIdentifier") or "")
    version = str(info.get("CFBundleShortVersionString") or "")
    build_version = str(info.get("CFBundleVersion") or "")
    minimum_os_version = str(info.get("MinimumOSVersion") or "")
    device_family = info.get("UIDeviceFamily")

    if bundle_identifier != BUNDLE_IDENTIFIER:
        raise RuntimeError(f"unexpected IPA bundle identifier: {bundle_identifier}")
    if version != version_from_tag:
        raise RuntimeError(f"release tag {tag} does not match embedded version {version}")
    if not build_version.isdigit():
        raise RuntimeError(f"unsupported build version: {build_version}")
    if not re.fullmatch(r"\d+(?:\.\d+)*", minimum_os_version):
        raise RuntimeError(f"unsupported minimum OS version: {minimum_os_version}")
    if sorted(device_family or []) != [1, 2]:
        raise RuntimeError(f"unexpected supported device family: {device_family}")

    return VerifiedRelease(
        version=version,
        build_version=build_version,
        date=published_at[:10],
        notes=notes,
        caption=caption,
        download_url=download_url,
        size=len(ipa),
        sha256=digest,
        minimum_os_version=minimum_os_version,
    )


def _version_key(version: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(?:\.\d+){1,3}", version):
        raise RuntimeError(f"unsupported source version: {version}")
    parts = tuple(int(part) for part in version.split("."))
    return parts + (0,) * (4 - len(parts))


def _release_entry(release: VerifiedRelease) -> dict[str, Any]:
    return {
        "version": release.version,
        "buildVersion": release.build_version,
        "date": release.date,
        "localizedDescription": release.notes,
        "downloadURL": release.download_url,
        "size": release.size,
        "sha256": release.sha256,
        "minOSVersion": release.minimum_os_version,
    }


def _news_entry(release: VerifiedRelease, image_url: str, tint_color: str) -> dict[str, Any]:
    bundle_slug = BUNDLE_IDENTIFIER.replace(".", "-")
    version_slug = release.version.replace(".", "-")
    return {
        "title": f"Nuvio {release.version}",
        "identifier": f"{bundle_slug}-{version_slug}-b{release.build_version}-iphone-ipad",
        "caption": release.caption,
        "tintColor": tint_color.removeprefix("#"),
        "date": release.date,
        "notify": False,
        "appID": BUNDLE_IDENTIFIER,
        "imageURL": image_url,
    }


def _current_app(source: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    apps = source.get("apps")
    if not isinstance(apps, list):
        raise RuntimeError("source JSON is missing the apps array")
    matches = [app for app in apps if app.get("bundleIdentifier") == BUNDLE_IDENTIFIER]
    if len(matches) != 1:
        raise RuntimeError(f"expected one Nuvio app entry, found {len(matches)}")
    app = matches[0]
    versions = app.get("versions")
    if not isinstance(versions, list) or not versions:
        raise RuntimeError("Nuvio app is missing version history")
    return app, versions[0]


def _apply_release(source: dict[str, Any], release: VerifiedRelease) -> bool:
    app, current = _current_app(source)
    versions = app["versions"]
    news = source.get("news")
    if not isinstance(news, list):
        raise RuntimeError("source JSON is missing the news array")

    before = json.dumps(source, ensure_ascii=False, sort_keys=True)
    current_coordinate = (_version_key(str(current["version"])), int(current["buildVersion"]))
    release_coordinate = (_version_key(release.version), int(release.build_version))
    if release_coordinate < current_coordinate:
        raise RuntimeError(
            f"upstream latest IPA {release.version} build {release.build_version} is older than source latest "
            f"{current['version']} build {current['buildVersion']}"
        )

    entry = _release_entry(release)
    versions[:] = [
        item
        for item in versions
        if not (
            str(item.get("version")) == release.version
            and str(item.get("buildVersion")) == release.build_version
        )
    ]
    versions.insert(0, entry)

    app.update(
        {
            "version": release.version,
            "versionDate": release.date,
            "versionDescription": release.notes,
            "downloadURL": release.download_url,
            "size": release.size,
            "minOSVersion": release.minimum_os_version,
        }
    )

    news_item = _news_entry(
        release,
        str(app.get("iconURL") or ""),
        str(app.get("tintColor") or source.get("tintColor") or "4F7CFF"),
    )
    news[:] = [item for item in news if item.get("identifier") != news_item["identifier"]]
    news.insert(0, news_item)

    coordinates = [(str(item.get("version")), str(item.get("buildVersion"))) for item in versions]
    if len(coordinates) != len(set(coordinates)):
        raise RuntimeError("Nuvio version history contains duplicate version/build coordinates")
    _validate_app_mirrors(app, versions[0])

    after = json.dumps(source, ensure_ascii=False, sort_keys=True)
    return before != after


def _validate_app_mirrors(app: dict[str, Any], latest: dict[str, Any]) -> None:
    mirrors = {
        "version": "version",
        "versionDate": "date",
        "versionDescription": "localizedDescription",
        "downloadURL": "downloadURL",
        "size": "size",
        "minOSVersion": "minOSVersion",
    }
    for app_field, version_field in mirrors.items():
        if app.get(app_field) != latest.get(version_field):
            raise RuntimeError(
                f"Nuvio app field {app_field} does not mirror latest version field {version_field}"
            )


def _fetch_file(file_path: str, ref: str) -> bytes:
    response = _gh_api(f"repos/{SOURCE_REPO}/contents/{file_path}?ref={ref}")
    if not isinstance(response, dict) or response.get("encoding") != "base64":
        raise RuntimeError(f"GitHub returned an unsupported encoding for {file_path}")
    return base64.b64decode(str(response.get("content") or ""))


def _fetch_snapshot() -> tuple[str, bytes, bytes]:
    ref = _gh_api(f"repos/{SOURCE_REPO}/git/ref/heads/{SOURCE_BRANCH}")
    if not isinstance(ref, dict):
        raise RuntimeError("GitHub returned an invalid main reference")
    base_commit = str((ref.get("object") or {}).get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", base_commit):
        raise RuntimeError("GitHub returned an invalid main commit SHA")
    return (
        base_commit,
        _fetch_file(SOURCE_PATH, base_commit),
        _fetch_file(README_PATH, base_commit),
    )


def _serialize_source(source: dict[str, Any]) -> bytes:
    return (json.dumps(source, ensure_ascii=False, indent=2) + "\n").encode()


def _update_readme(readme: str, source: dict[str, Any]) -> str:
    _, latest = _current_app(source)
    expected_row = (
        f"| Nuvio | `{BUNDLE_IDENTIFIER}` | {latest['version']} "
        f"(build {latest['buildVersion']}) | {latest['minOSVersion']} | "
        f"[NuvioMobile](https://github.com/{UPSTREAM_REPO}/releases) |"
    )
    pattern = re.compile(
        r"^\| Nuvio \| `com\.nuvio\.media` \| [^|]+ \| [^|]+ \| "
        r"\[NuvioMobile\]\(https://github\.com/NuvioMedia/NuvioMobile/releases\) \|$",
        re.MULTILINE,
    )
    matches = pattern.findall(readme)
    if len(matches) != 1:
        raise RuntimeError(f"expected one Nuvio README row, found {len(matches)}")
    return pattern.sub(expected_row, readme, count=1)


def _validate_cross_file(source: dict[str, Any], readme: str) -> None:
    app, latest = _current_app(source)
    _validate_app_mirrors(app, latest)
    expected_fragment = (
        f"| Nuvio | `{BUNDLE_IDENTIFIER}` | {latest['version']} "
        f"(build {latest['buildVersion']}) | {latest['minOSVersion']} |"
    )
    if readme.count(expected_fragment) != 1:
        raise RuntimeError("README Nuvio row does not match the latest JSON version")

    coordinates = [(str(item.get("version")), str(item.get("buildVersion"))) for item in app["versions"]]
    if len(coordinates) != len(set(coordinates)):
        raise RuntimeError("Nuvio version history contains duplicate version/build coordinates")


def _create_blob(raw: bytes) -> str:
    response = _gh_api(
        f"repos/{SOURCE_REPO}/git/blobs",
        method="POST",
        payload={"content": base64.b64encode(raw).decode(), "encoding": "base64"},
    )
    blob_sha = str((response or {}).get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", blob_sha):
        raise RuntimeError("GitHub returned an invalid blob SHA")
    return blob_sha


def _commit_files(base_commit: str, files: dict[str, bytes], version: str) -> tuple[str, str]:
    base = _gh_api(f"repos/{SOURCE_REPO}/git/commits/{base_commit}")
    base_tree = str(((base or {}).get("tree") or {}).get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", base_tree):
        raise RuntimeError("GitHub returned an invalid base tree SHA")

    entries = [
        {"path": file_path, "mode": "100644", "type": "blob", "sha": _create_blob(raw)}
        for file_path, raw in sorted(files.items())
    ]
    tree = _gh_api(
        f"repos/{SOURCE_REPO}/git/trees",
        method="POST",
        payload={"base_tree": base_tree, "tree": entries},
    )
    tree_sha = str((tree or {}).get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
        raise RuntimeError("GitHub returned an invalid tree SHA")

    commit = _gh_api(
        f"repos/{SOURCE_REPO}/git/commits",
        method="POST",
        payload={
            "message": f"chore: Update Nuvio to {version}",
            "tree": tree_sha,
            "parents": [base_commit],
        },
    )
    commit_sha = str((commit or {}).get("sha") or "")
    commit_url = str((commit or {}).get("html_url") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise RuntimeError("GitHub returned an invalid commit SHA")
    if not commit_url.startswith(f"https://github.com/{SOURCE_REPO}/commit/"):
        raise RuntimeError("GitHub did not return the expected commit URL")

    current_ref = _gh_api(f"repos/{SOURCE_REPO}/git/ref/heads/{SOURCE_BRANCH}")
    current_head = str((((current_ref or {}).get("object") or {}).get("sha")) or "")
    if current_head != base_commit:
        raise RuntimeError("main changed while preparing the update; retrying on the next schedule")
    _gh_api(
        f"repos/{SOURCE_REPO}/git/refs/heads/{SOURCE_BRANCH}",
        method="PATCH",
        payload={"sha": commit_sha, "force": False},
    )

    for file_path, expected in files.items():
        if _fetch_file(file_path, commit_sha) != expected:
            raise RuntimeError(f"post-commit verification failed for {file_path}")
    return commit_url, commit_sha


def check_and_update() -> dict[str, str] | None:
    base_commit, source_raw, readme_raw = _fetch_snapshot()
    source = json.loads(source_raw)
    readme = readme_raw.decode()

    release = _verify_latest_ipa_release(source)
    source_changed = release is not None and _apply_release(source, release)
    updated_readme = _update_readme(readme, source)
    _validate_cross_file(source, updated_readme)

    files: dict[str, bytes] = {}
    if source_changed:
        files[SOURCE_PATH] = _serialize_source(source)
    if updated_readme != readme:
        files[README_PATH] = updated_readme.encode()
    if not files:
        return None

    _, latest = _current_app(source)
    commit_url, commit_sha = _commit_files(base_commit, files, str(latest["version"]))
    return {
        "version": str(latest["version"]),
        "build": str(latest["buildVersion"]),
        "files": ", ".join(sorted(files)),
        "commit_url": commit_url,
        "commit_sha": commit_sha,
    }


def _write_outputs(values: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as output:
        for name, value in values.items():
            if "\n" in value or "\r" in value:
                raise RuntimeError(f"workflow output {name} contains a newline")
            output.write(f"{name}={value}\n")


def main() -> None:
    repository = os.environ.get("GITHUB_REPOSITORY")
    if repository and repository != SOURCE_REPO:
        raise RuntimeError(f"workflow is running in unexpected repository: {repository}")

    result = check_and_update()
    if result is None:
        _write_outputs({"changed": "false", "version": "", "build": "", "commit_sha": ""})
        print("Nuvio source is already current")
        return

    _write_outputs(
        {
            "changed": "true",
            "version": result["version"],
            "build": result["build"],
            "commit_sha": result["commit_sha"],
        }
    )
    print(
        f"Updated Nuvio source to {result['version']} build {result['build']} "
        f"({result['files']}): {result['commit_url']}"
    )


if __name__ == "__main__":
    main()
