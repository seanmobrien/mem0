import importlib.metadata
import os
from pathlib import Path

__version__ = importlib.metadata.version("mem0ai")


def get_build_info():
    """Get information about the current mem0ai build"""
    try:
        # Check if this is a local/development build
        package_path = Path(__file__).parent

        # Look for build metadata file
        build_info_file = package_path / ".build_info"
        if build_info_file.exists():
            # Parse build info file
            metadata = {}
            for line in build_info_file.read_text().strip().split("\n"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    metadata[key] = value

            build_type = metadata.get("build_type", "unknown")
            if build_type == "distribution-build":
                return {
                    "type": "distribution_build",
                    "info": f"CI/CD build from {metadata.get('branch', 'unknown')}",
                    "version": __version__,
                    "commit": metadata.get("commit", "unknown"),
                    "run_id": metadata.get("run_id", "unknown"),
                    "timestamp": metadata.get("timestamp", "unknown"),
                }
            else:
                return {
                    "type": "local",
                    "info": metadata.get("build_info", "local build"),
                    "path": str(package_path),
                    "timestamp": metadata.get("timestamp", "unknown"),
                }

        # Check if installed in development mode
        if str(package_path).endswith("mem0") and (package_path.parent / "pyproject.toml").exists():
            return {"type": "development", "info": "editable install", "path": str(package_path)}

        # Check for custom metadata in package
        try:
            dist = importlib.metadata.distribution("mem0ai")
            metadata = dist.metadata
            project_urls = metadata.get_all("Project-URL") or []
            if any("Distribution Source" in url for url in project_urls):
                return {"type": "distribution_build", "info": "Distribution build", "version": __version__}
        except:
            pass

        return {"type": "published", "info": "official release", "version": __version__}
    except Exception as e:
        # Don't leak internal exception details to external callers
        return {"type": "unknown", "info": "Build metadata detection failed", "version": __version__}


# Add build metadata for runtime detection
__build_info__ = get_build_info()

from mem0.client.main import AsyncMemoryClient, MemoryClient  # noqa
from mem0.memory.main import AsyncMemory, Memory  # noqa
