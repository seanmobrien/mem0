#!/usr/bin/env python3
"""
Build script for local mem0ai package with custom metadata
"""
import os
import subprocess
import datetime
from pathlib import Path

def get_git_commit():
    """Get current git commit hash"""
    try:
        result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], 
                              capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except:
        return "unknown"

def sanitize_version_component(component):
    """Sanitize a component for use in version strings per PEP 440"""
    # Replace problematic characters with hyphens
    import re
    # Replace forward slashes, backslashes, and other problematic chars with hyphens
    sanitized = re.sub(r'[/\\:]', '-', component)
    # Remove or replace other non-alphanumeric chars except dots, hyphens, and underscores
    sanitized = re.sub(r'[^a-zA-Z0-9.\-_]', '-', sanitized)
    # Remove consecutive hyphens
    sanitized = re.sub(r'-+', '-', sanitized)
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')
    return sanitized or 'unknown'

def get_build_info():
    """Generate build information based on environment"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d.%H%M%S")
    commit = get_git_commit()
    
    # Check if running in CI/CD environment
    if os.getenv('GITHUB_ACTIONS'):
        # GitHub Actions environment
        build_type = os.getenv('BUILD_TYPE', 'distribution-build')
        branch = sanitize_version_component(os.getenv('GITHUB_REF_NAME', 'unknown'))
        run_id = os.getenv('GITHUB_RUN_ID', 'unknown')
        sha = os.getenv('GITHUB_SHA', commit)[:7] if os.getenv('GITHUB_SHA') else commit
        
        return f"{build_type}.{branch}.{sha}.{run_id}"
    else:
        # Local build
        return f"local.{timestamp}.{commit}"

def update_version_with_metadata():
    """Update version in pyproject.toml with build metadata"""
    pyproject_file = Path("pyproject.toml")
    content = pyproject_file.read_text()
    
    build_info = get_build_info()
    
    # Check if we're in CI and should update version
    if os.getenv('GITHUB_ACTIONS'):
        # Extract current version
        import re
        version_match = re.search(r'version = "([^"]+)"', content)
        if version_match:
            base_version = version_match.group(1)
            # Add build metadata to version
            new_version = f"{base_version}+{build_info}"
            content = content.replace(
                f'version = "{base_version}"',
                f'version = "{new_version}"'
            )
            pyproject_file.write_text(content)
            print(f"Updated version to: {new_version}")

def update_init_file():
    """Add build metadata to __init__.py"""
    init_file = Path("mem0/__init__.py")
    build_info = get_build_info()
    
    # Read existing content
    content = init_file.read_text()
    
    # Check if build metadata already exists
    if '__build_stamp__' in content:
        # Replace existing build stamp
        import re
        content = re.sub(
            r'__build_stamp__ = "[^"]*"',
            f'__build_stamp__ = "{build_info}"',
            content
        )
    else:
        # Add new build metadata
        build_metadata = f'__build_stamp__ = "{build_info}"\n__build_type__ = "{"distribution" if os.getenv("GITHUB_ACTIONS") else "local"}"\n'
        
        # Insert before the last line
        lines = content.split('\n')
        lines.insert(-2, build_metadata.strip())
        content = '\n'.join(lines)
    
    init_file.write_text(content)
    print(f"Added build metadata: {build_info}")

def create_build_info_file():
    """Create .build_info file for runtime detection"""
    build_info_file = Path("mem0/.build_info")
    build_info = get_build_info()
    
    # Include additional CI/CD metadata
    metadata = {
        "build_info": build_info,
        "timestamp": datetime.datetime.now().isoformat(),
        "commit": get_git_commit(),
    }
    
    if os.getenv('GITHUB_ACTIONS'):
        # Get environment variables with fallbacks for empty strings
        def get_env_var(name, default='unknown'):
            value = os.getenv(name, default)
            return value if value and value.strip() else default
            
        metadata.update({
            "build_type": "distribution-build",
            "branch": get_env_var('GITHUB_REF_NAME'),
            "run_id": get_env_var('GITHUB_RUN_ID'),
            "sha": get_env_var('GITHUB_SHA'),
            "actor": get_env_var('GITHUB_ACTOR'),
            "workflow": get_env_var('GITHUB_WORKFLOW')
        })
    else:
        metadata["build_type"] = "local"
    
    # Write as simple key=value format for easy parsing
    content = '\n'.join(f"{key}={value}" for key, value in metadata.items())
    build_info_file.write_text(content)
    print(f"Created build info file: {build_info_file}")

def main():
    """Main build process"""
    build_env = "CI/CD" if os.getenv('GITHUB_ACTIONS') else "local"
    print(f"Building mem0ai package in {build_env} environment...")
    
    # Update version with build metadata (only in CI)
    if os.getenv('GITHUB_ACTIONS'):
        update_version_with_metadata()
    
    # Add build metadata to __init__.py
    update_init_file()
    
    # Create build info file
    create_build_info_file()
    
    # Run hatch build
    subprocess.run(['hatch', 'build'], check=True)
    
    print("Build complete!")

if __name__ == "__main__":
    main()
