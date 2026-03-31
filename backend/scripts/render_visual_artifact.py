from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.visual_artifacts import render_poster_artifact  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a static visual artifact to PNG or PDF.")
    parser.add_argument("--brief", required=True, help="Visual brief for the deliverable.")
    parser.add_argument(
        "--format",
        default="auto",
        choices=["auto", "png", "pdf"],
        help="Preferred output format.",
    )
    parser.add_argument(
        "--workspace",
        default="default",
        help="Workspace name used for output directory grouping.",
    )
    parser.add_argument(
        "--filename-stem",
        default=None,
        help="Optional filename stem for generated files.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    result = render_poster_artifact(
        brief=args.brief,
        workspace=args.workspace,
        preferred_format=args.format,
        filename_stem=args.filename_stem,
    )
    payload = {
        "ok": True,
        "summary": result.summary,
        "title": result.title,
        "format": result.format,
        "file_paths": list(result.file_paths),
        "artifact_count": len(result.artifacts),
        "artifacts": [
            {
                "path": artifact.path,
                "relative_path": artifact.relative_path,
                "name": artifact.name,
                "mime_type": artifact.mime_type,
                "size_bytes": artifact.size_bytes,
                "preview_kind": artifact.preview_kind,
            }
            for artifact in result.artifacts
        ],
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
