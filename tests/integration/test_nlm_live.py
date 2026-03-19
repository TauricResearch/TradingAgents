import os
import json
import subprocess
import pytest
from pathlib import Path

# This test requires a real NOTEBOOKLM_ID in .env and nlm CLI logged in.
# It is excluded from regular unit tests by its location/filename.

NOTEBOOK_ID = os.environ.get("NOTEBOOKLM_ID")
NLM_PATH = os.path.expanduser("~/.local/bin/nlm")

@pytest.mark.skipif(not NOTEBOOK_ID, reason="NOTEBOOKLM_ID not set")
@pytest.mark.skipif(not os.path.exists(NLM_PATH), reason="nlm CLI not found")
def test_nlm_source_crud_live():
    """Live integration test for nlm source commands."""
    date = "2026-03-19"
    test_title = f"Integration Test Source ({date})"
    test_file = Path("test_integration_source.md")
    test_file.write_text("# Integration Test Content")

    try:
        # 1. Check if it already exists (from a failed run, maybe) and delete it
        print(f"\nChecking for existing '{test_title}' source...")
        result = subprocess.run(
            [NLM_PATH, "source", "list", NOTEBOOK_ID, "--json"],
            capture_output=True, text=True, check=True
        )
        sources = json.loads(result.stdout)
        for s in sources:
            if s.get("title") == test_title:
                print(f"Deleting existing source {s['id']}")
                subprocess.run([NLM_PATH, "source", "delete", NOTEBOOK_ID, s["id"], "-y"], check=False)

        # 2. Add source via text to ensure title is respected
        print(f"Adding source: {test_title}")
        result = subprocess.run(
            [NLM_PATH, "source", "add", NOTEBOOK_ID, "--text", "Integration Test Content", "--title", test_title, "--wait"],
            capture_output=True, text=True, check=True
        )
        assert "Added source" in result.stdout
        
        # Parse ID from stdout if possible (it's not JSON)
        import re
        match = re.search(r"Source ID: ([a-f0-9\-]+)", result.stdout)
        source_id = match.group(1) if match else None
        assert source_id is not None
        print(f"Source created with ID: {source_id}")

        # 3. List and verify finding by name
        print(f"Verifying we can find source by its name title: '{test_title}'")
        result = subprocess.run(
            [NLM_PATH, "source", "list", NOTEBOOK_ID, "--json"],
            capture_output=True, text=True, check=True
        )
        sources = json.loads(result.stdout)
        
        found_id_by_name = None
        for s in sources:
            if s.get("title") == test_title:
                found_id_by_name = s.get("id")
                break
                
        assert found_id_by_name == source_id, f"Failed to find source ID {source_id} by title '{test_title}'\nFound sources: {[s.get('title') for s in sources]}"
        print(f"Successfully found source {found_id_by_name} by title.")

    finally:
        # 4. Clean up
        if 'source_id' in locals() and source_id:
            print(f"Cleaning up source {source_id}")
            subprocess.run([NLM_PATH, "source", "delete", NOTEBOOK_ID, source_id, "-y"], check=False)
        print("Integration test complete")
