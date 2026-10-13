"""Deterministic contract checks for generated dashboard HTML artifacts."""
from __future__ import annotations

import json
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

Issue = dict[str, str]
ASSET_ATTRIBUTES = {"script": "src", "link": "href", "img": "src", "source": "src", "video": "src", "audio": "src"}


class DashboardHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.assets: list[str] = []
        self.references: list[tuple[str, str]] = []
        self.text_chunks: list[str] = []
        self.has_doctype = self.has_charset = self.has_viewport = self.has_title = False
        self.html_lang = ""
        self._in_title = False
        self._ignored_text_depth = 0

    def handle_decl(self, decl: str) -> None:
        self.has_doctype = decl.lower().startswith("doctype html") or self.has_doctype

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(str(values["id"]))
        asset_attribute = ASSET_ATTRIBUTES.get(tag)
        if asset_attribute and values.get(asset_attribute):
            self.assets.append(str(values[asset_attribute]))
        for attribute in ("aria-controls", "for"):
            if values.get(attribute):
                self.references.append((f"{tag}[{attribute}]", str(values[attribute])))
        href = str(values.get("href") or "")
        if href.startswith("#") and len(href) > 1:
            self.references.append((f"{tag}[href]", unquote(href[1:])))
        if tag == "html":
            self.html_lang = str(values.get("lang") or "")
        elif tag == "meta":
            self.has_charset = self.has_charset or bool(values.get("charset"))
            self.has_viewport = self.has_viewport or str(values.get("name") or "").lower() == "viewport"
        elif tag == "title":
            self._in_title = True
        if tag in ("script", "style"):
            self._ignored_text_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in ("script", "style") and self._ignored_text_depth:
            self._ignored_text_depth -= 1

    def handle_data(self, data: str) -> None:
        normalized = " ".join(data.split())
        if self._in_title and normalized:
            self.has_title = True
        if normalized and not self._ignored_text_depth and not self._in_title:
            self.text_chunks.append(normalized)


def issue(code: str, path: str, message: str) -> Issue:
    return {"code": code, "path": path, "message": message}


def parse_html(path: Path) -> tuple[DashboardHTMLParser | None, str, list[Issue]]:
    if not path.is_file():
        return None, "", [issue("HTML_NOT_FOUND", str(path), "HTML file does not exist")]
    try:
        source = path.read_text(encoding="utf-8")
        parser = DashboardHTMLParser()
        parser.feed(source)
        parser.close()
        return parser, source, []
    except (OSError, UnicodeError) as exc:
        return None, "", [issue("HTML_READ_FAILED", str(path), str(exc))]


def read_manifest(path: Path | None) -> tuple[dict[str, Any] | None, list[Issue]]:
    if path is None:
        return None, []
    resolved = path.expanduser().resolve()
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [issue("MANIFEST_NOT_FOUND", str(resolved), "Preservation manifest does not exist")]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, [issue("MANIFEST_INVALID", str(resolved), str(exc))]
    if not isinstance(value, dict):
        return None, [issue("MANIFEST_INVALID", str(resolved), "Preservation manifest must contain an object")]
    return value, []


def manifest_list(manifest: dict[str, Any], key: str) -> list[Any]:
    aliases = {"requiredIds": "ids", "requiredText": "text", "requiredAssets": "assets"}
    required = manifest.get("required") if isinstance(manifest.get("required"), dict) else {}
    value = manifest.get(key, required.get(aliases.get(key, key)))
    return value if isinstance(value, list) else []


def check_manifest(parser: DashboardHTMLParser, source: str, manifest: dict[str, Any]) -> list[Issue]:
    errors: list[Issue] = []
    ids, visible_text = set(parser.ids), " ".join(parser.text_chunks)
    for value in manifest_list(manifest, "requiredIds"):
        if str(value) not in ids:
            errors.append(issue("MANIFEST_ID_MISSING", f"#{value}", f"Required DOM id is missing: {value}"))
    for value in manifest_list(manifest, "requiredText"):
        if str(value) not in visible_text:
            errors.append(issue("PRESERVED_TEXT_MISSING", f"text:{value}", f"Required text is missing: {value}"))
    for value in manifest_list(manifest, "forbiddenText"):
        if str(value).lower() in source.lower():
            errors.append(issue("FORBIDDEN_TEXT_FOUND", f"text:{value}", f"Forbidden text is present: {value}"))
    for component in manifest_list(manifest, "components"):
        value = component.get("id") if isinstance(component, dict) else component
        if value and str(value) not in ids:
            errors.append(issue("MANIFEST_COMPONENT_MISSING", f"#{value}", f"Required component is missing: {value}"))
    for value in manifest_list(manifest, "requiredAssets"):
        if str(value) not in parser.assets:
            errors.append(issue("MANIFEST_ASSET_MISSING", f"asset:{value}", f"Required asset reference is missing: {value}"))
    return errors


def inspect_html(path: Path, strict: bool = False, manifest_path: Path | None = None) -> dict[str, Any]:
    html_path = path.expanduser().resolve()
    parser, source, errors = parse_html(html_path)
    warnings: list[Issue] = []
    manifest, manifest_errors = read_manifest(manifest_path)
    errors.extend(manifest_errors)
    if parser is None:
        return result("dashboard.inspect-html", html_path, errors, warnings, {}, manifest_path)
    duplicates = sorted(value for value, count in Counter(parser.ids).items() if count > 1)
    errors.extend(issue("DOM_ID_DUPLICATE", f"#{value}", f"DOM id must be unique: {value}") for value in duplicates)
    ids = set(parser.ids)
    missing_refs = {(origin, target) for origin, reference in parser.references for target in reference.split() if target and target not in ids}
    errors.extend(issue("DOM_REFERENCE_MISSING", f"{origin}->#{target}", f"DOM reference targets a missing id: {target}") for origin, target in sorted(missing_refs))
    local_assets = []
    for asset in sorted(set(parser.assets)):
        parts = urlsplit(asset)
        if parts.scheme or parts.netloc or asset.startswith(("//", "data:", "#")):
            continue
        local_assets.append(asset)
        if not (html_path.parent / unquote(parts.path)).resolve().is_file():
            errors.append(issue("ASSET_NOT_FOUND", asset, f"Referenced local asset does not exist: {asset}"))
    checks = ((parser.has_doctype, "HTML_DOCTYPE_MISSING", "doctype", "HTML5 doctype is required"), (bool(parser.html_lang), "HTML_LANG_MISSING", "html.lang", "HTML language is required"), (parser.has_charset, "HTML_CHARSET_MISSING", "head.meta[charset]", "UTF-8 charset metadata is required"), (parser.has_viewport, "HTML_VIEWPORT_MISSING", "head.meta[name=viewport]", "Viewport metadata is required"), (parser.has_title, "HTML_TITLE_MISSING", "head.title", "Document title is required"))
    for passed, code, check_path, message in checks:
        if not passed:
            (errors if strict else warnings).append(issue(code, check_path, message))
    if manifest is not None:
        errors.extend(check_manifest(parser, source, manifest))
    summary = {"ids": len(parser.ids), "duplicateIds": len(duplicates), "assets": len(parser.assets), "localAssets": len(local_assets), "domReferences": len(parser.references)}
    return result("dashboard.inspect-html", html_path, errors, warnings, summary, manifest_path)


def compare_html(before: Path, after: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    before_path, after_path = before.expanduser().resolve(), after.expanduser().resolve()
    before_parser, _, errors = parse_html(before_path)
    after_parser, _, after_errors = parse_html(after_path)
    errors.extend(after_errors)
    candidate_inspection = inspect_html(after_path, strict=True, manifest_path=manifest_path)
    errors.extend(candidate_inspection["errors"])
    if before_parser and after_parser:
        errors.extend(issue("PRESERVED_ID_MISSING", f"#{value}", f"Baseline DOM id is missing: {value}") for value in sorted(set(before_parser.ids) - set(after_parser.ids)))
        errors.extend(issue("PRESERVED_TEXT_MISSING", f"text:{value}", f"Baseline text is missing: {value}") for value in before_parser.text_chunks if value not in after_parser.text_chunks)
        errors.extend(issue("PRESERVED_ASSET_MISSING", f"asset:{value}", f"Baseline asset reference is missing: {value}") for value in sorted(set(before_parser.assets) - set(after_parser.assets)))
    payload = result("dashboard.compare-html", after_path, errors, [], {"baselineIds": len(before_parser.ids) if before_parser else 0, "candidateIds": len(after_parser.ids) if after_parser else 0, "regressions": len(errors)}, manifest_path)
    payload["before"], payload["after"] = str(before_path), payload.pop("html")
    return payload


def inventory_html(path: Path) -> tuple[dict[str, Any], list[Issue]]:
    """Create an editable preservation baseline from an existing HTML page."""
    parser, _, errors = parse_html(path.expanduser().resolve())
    if parser is None:
        return {}, errors
    return {
        "requiredIds": list(dict.fromkeys(parser.ids)),
        "requiredText": list(dict.fromkeys(parser.text_chunks)),
        "requiredAssets": list(dict.fromkeys(parser.assets)),
        "components": [],
        "forbiddenText": [],
    }, errors


def result(command: str, path: Path, errors: list[Issue], warnings: list[Issue], summary: dict[str, Any], manifest_path: Path | None) -> dict[str, Any]:
    evidence: dict[str, Any] = {"parser": "html.parser", "mode": "static"}
    if manifest_path is not None:
        evidence["manifest"] = str(manifest_path.expanduser().resolve())
    return {"ok": not errors, "command": command, "html": str(path), "summary": summary, "errors": errors, "warnings": warnings, "evidence": evidence}
