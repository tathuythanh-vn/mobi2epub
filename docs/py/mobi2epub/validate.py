"""EPUB validation: sanity-check zip container, mimetype, container.xml, OPF, and content."""

from __future__ import annotations

import os
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    title: Optional[str] = None
    spine_items_count: int = 0

    @property
    def error_summary(self) -> str:
        return "; ".join(self.errors)


def validate_epub(epub_path: str | Path) -> ValidationResult:
    """Validate EPUB file structure and required specifications."""
    path = Path(epub_path)
    errors: list[str] = []
    warnings: list[str] = []

    if not path.exists():
        return ValidationResult(is_valid=False, errors=[f"File does not exist: {path}"])

    if path.stat().st_size == 0:
        return ValidationResult(is_valid=False, errors=["EPUB file is empty (0 bytes)"])

    if not zipfile.is_zipfile(path):
        return ValidationResult(is_valid=False, errors=["File is not a valid ZIP archive"])

    try:
        with zipfile.ZipFile(path, "r") as zf:
            file_list = zf.namelist()

            # 1. mimetype check
            if not file_list:
                return ValidationResult(is_valid=False, errors=["ZIP archive is empty"])

            if file_list[0] != "mimetype":
                errors.append(f"First entry in ZIP must be 'mimetype', found: '{file_list[0]}'")

            if "mimetype" in file_list:
                info = zf.getinfo("mimetype")
                if info.compress_type != zipfile.ZIP_STORED:
                    errors.append(f"mimetype must be uncompressed (ZIP_STORED), was: {info.compress_type}")

                content = zf.read("mimetype").strip()
                if content != b"application/epub+zip":
                    errors.append(f"mimetype content must be 'application/epub+zip', was: {content!r}")
            else:
                errors.append("Archive lacks required 'mimetype' file")

            # 2. META-INF/container.xml check
            if "META-INF/container.xml" not in file_list:
                errors.append("Missing 'META-INF/container.xml'")
                return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

            try:
                container_xml = zf.read("META-INF/container.xml")
                c_root = ET.fromstring(container_xml)
            except Exception as e:
                errors.append(f"Invalid XML in META-INF/container.xml: {e}")
                return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

            # Find rootfile
            ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
            rootfiles = c_root.findall(".//c:rootfile", ns)
            if not rootfiles:
                # Try without namespace in case generator omitted it
                rootfiles = c_root.findall(".//rootfile")

            if not rootfiles:
                errors.append("container.xml does not contain any <rootfile> element")
                return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

            opf_path = rootfiles[0].attrib.get("full-path")
            if not opf_path:
                errors.append("Rootfile element in container.xml missing 'full-path' attribute")
                return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

            # Normalize opf_path for zip
            opf_path = opf_path.replace("\\", "/")
            if opf_path not in file_list:
                errors.append(f"OPF package file declared in container.xml not found in archive: '{opf_path}'")
                return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

            # 3. OPF Package document check
            try:
                opf_data = zf.read(opf_path)
                opf_root = ET.fromstring(opf_data)
            except Exception as e:
                errors.append(f"Invalid XML in OPF package file '{opf_path}': {e}")
                return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

            opf_dir = os.path.dirname(opf_path)

            # Strip namespaces for easier tag inspection
            def local_tag(elem: ET.Element) -> str:
                return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

            metadata_elem = None
            manifest_elem = None
            spine_elem = None

            for child in opf_root:
                tag = local_tag(child).lower()
                if tag == "metadata":
                    metadata_elem = child
                elif tag == "manifest":
                    manifest_elem = child
                elif tag == "spine":
                    spine_elem = child

            if metadata_elem is None:
                errors.append("OPF package lacks <metadata> section")
            if manifest_elem is None:
                errors.append("OPF package lacks <manifest> section")
            if spine_elem is None:
                errors.append("OPF package lacks <spine> section")

            title = None
            if metadata_elem is not None:
                for meta_child in metadata_elem:
                    if local_tag(meta_child).lower() == "title" and meta_child.text:
                        title = meta_child.text.strip()
                        break

            # 4. Manifest and Spine check
            manifest_items: dict[str, str] = {}
            if manifest_elem is not None:
                for item in manifest_elem:
                    if local_tag(item).lower() == "item":
                        item_id = item.attrib.get("id")
                        href = item.attrib.get("href")
                        if item_id and href:
                            manifest_items[item_id] = href

            spine_count = 0
            if spine_elem is not None:
                for itemref in spine_elem:
                    if local_tag(itemref).lower() == "itemref":
                        spine_count += 1
                        idref = itemref.attrib.get("idref")
                        if not idref:
                            errors.append("Spine itemref missing idref attribute")
                        elif idref not in manifest_items:
                            errors.append(f"Spine itemref '{idref}' not found in manifest")
                        else:
                            # Verify target file exists in ZIP
                            href = manifest_items[idref]
                            target_path = f"{opf_dir}/{href}" if opf_dir else href
                            # Normalize path
                            target_norm = os.path.normpath(target_path).replace("\\", "/")
                            if target_norm not in file_list and target_path not in file_list:
                                errors.append(f"Spine content file missing from archive: '{target_path}'")

            if spine_count == 0:
                warnings.append("Spine has no items")

    except zipfile.BadZipFile as e:
        errors.append(f"Corrupt ZIP file: {e}")
    except Exception as e:
        errors.append(f"Unexpected error during validation: {e}")

    return ValidationResult(
        is_valid=(len(errors) == 0),
        errors=errors,
        warnings=warnings,
        title=title,
        spine_items_count=spine_count,
    )
