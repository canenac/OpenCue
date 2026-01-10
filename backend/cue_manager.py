"""
OpenCue - Cue File Manager

Manages loading, caching, and matching of .opencue files.
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
import hashlib


@dataclass
class CueFileInfo:
    """Metadata about a loaded cue file"""
    path: str
    title: str
    duration_ms: int
    cue_count: int
    has_fingerprints: bool
    content_hash: Optional[str] = None
    imdb_id: Optional[str] = None


class CueManager:
    """Manages .opencue file loading and lookup"""

    def __init__(self, cue_directory: Optional[str] = None):
        # Default cue directory (backend/cues where recordings are saved)
        if cue_directory:
            self.cue_dir = Path(cue_directory)
        else:
            self.cue_dir = Path(__file__).parent / "cues"

        # Create directory if it doesn't exist
        self.cue_dir.mkdir(parents=True, exist_ok=True)

        # Cache of loaded cue files
        self._cache: Dict[str, dict] = {}

        # Index of available cue files
        self._index: Dict[str, CueFileInfo] = {}

        # Scan for cue files
        self.refresh_index()

    def refresh_index(self):
        """Scan cue directory and build index"""
        self._index.clear()

        for cue_path in self.cue_dir.glob("*.opencue"):
            try:
                info = self._get_cue_info(cue_path)
                if info:
                    self._index[cue_path.stem] = info
            except Exception as e:
                print(f"[OpenCue] Error indexing {cue_path}: {e}")

        print(f"[OpenCue] Indexed {len(self._index)} cue files")

    def _get_cue_info(self, path: Path) -> Optional[CueFileInfo]:
        """Extract info from cue file without full load"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            content = data.get("content", {})
            fingerprints = data.get("fingerprints", {})

            return CueFileInfo(
                path=str(path),
                title=content.get("title", path.stem),
                duration_ms=content.get("duration_ms", 0),
                cue_count=len(data.get("cues", [])),
                has_fingerprints=len(fingerprints.get("markers", [])) > 0,
                content_hash=content.get("content_hash"),
                imdb_id=content.get("imdb_id")
            )
        except Exception as e:
            print(f"[OpenCue] Error reading {path}: {e}")
            return None

    def load(self, identifier: str) -> Optional[dict]:
        """
        Load a cue file by identifier.

        Identifier can be:
        - Filename (without .opencue extension)
        - IMDB ID (tt1234567)
        - Full path
        """
        # Check cache first
        if identifier in self._cache:
            return self._cache[identifier]

        # Try direct filename match
        if identifier in self._index:
            return self._load_file(self._index[identifier].path, identifier)

        # Try IMDB ID match
        for name, info in self._index.items():
            if info.imdb_id and info.imdb_id.lower() == identifier.lower():
                return self._load_file(info.path, identifier)

        # Try as full path
        path = Path(identifier)
        if path.exists() and path.suffix == ".opencue":
            return self._load_file(str(path), identifier)

        # Try adding .opencue extension
        path = self.cue_dir / f"{identifier}.opencue"
        if path.exists():
            return self._load_file(str(path), identifier)

        print(f"[OpenCue] Cue file not found: {identifier}")
        return None

    def _load_file(self, path: str, cache_key: str) -> Optional[dict]:
        """Load and cache a cue file"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._cache[cache_key] = data
            print(f"[OpenCue] Loaded cue file: {path}")
            return data

        except Exception as e:
            print(f"[OpenCue] Error loading {path}: {e}")
            return None

    def get_available(self) -> List[CueFileInfo]:
        """Get list of available cue files"""
        return list(self._index.values())

    def search(self, query: str) -> List[CueFileInfo]:
        """Search for cue files by title"""
        query_lower = query.lower()
        results = []

        for name, info in self._index.items():
            if query_lower in info.title.lower() or query_lower in name.lower():
                results.append(info)

        return results

    def clear_cache(self):
        """Clear the loaded file cache"""
        self._cache.clear()

    def add_cue_file(self, data: dict, filename: str) -> bool:
        """Add a new cue file"""
        if not filename.endswith(".opencue"):
            filename += ".opencue"

        path = self.cue_dir / filename

        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            # Update index
            info = self._get_cue_info(path)
            if info:
                self._index[path.stem] = info

            print(f"[OpenCue] Added cue file: {path}")
            return True

        except Exception as e:
            print(f"[OpenCue] Error saving cue file: {e}")
            return False


# Global instance
_manager: Optional[CueManager] = None


def get_cue_manager() -> CueManager:
    """Get the global cue manager instance"""
    global _manager
    if _manager is None:
        _manager = CueManager()
    return _manager
