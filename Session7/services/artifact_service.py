import sys
import hashlib
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import schemas
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import Artifact


class ArtifactStore:
    def __init__(self, artifacts_dir: str | Path = None):
        """
        Initialize the ArtifactStore.

        Args:
            artifacts_dir: Path to the artifacts directory (default: state/artifacts/)
        """
        # Set up the artifacts directory path
        if artifacts_dir is None:
            # Default to state/artifacts/ relative to the parent directory
            path_dir = Path(__file__).resolve().parent.parent
            self.artifacts_dir = path_dir / "state" / "artifacts"
        else:
            self.artifacts_dir = Path(artifacts_dir)

        # Ensure artifacts directory exists
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Counter file for auto-incrementing IDs
        self.counter_file = self.artifacts_dir / "_counter.json"
        self._init_counter()
    
    def _init_counter(self) -> None:
        """Initialize the counter file if it doesn't exist."""
        if not self.counter_file.exists():
            with open(self.counter_file, 'w', encoding='utf-8') as f:
                json.dump({"next_id": 1}, f)

    def _get_next_id(self) -> int:
        """Get the next available artifact ID and increment the counter."""
        with open(self.counter_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        next_id = data["next_id"]

        # Increment and save
        data["next_id"] = next_id + 1
        with open(self.counter_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        return next_id

    def put(
        self,
        blob: bytes,
        *,
        content_type: str,
        source: str,
        descriptor: str
    ) -> str:
        """
        Store an artifact (raw bytes + metadata).

        Writes two files:
        - art-<num>.bin: raw bytes
        - art-<num>.json: metadata (Artifact schema)

        Args:
            blob: The raw bytes to store
            content_type: MIME type or content type identifier
            source: Source identifier (e.g., "mcp:fetch_url", "user_upload")
            descriptor: Human-readable description

        Returns:
            artifact_id: Unique identifier in format "art:<int>"
        """
        # Get next auto-incrementing ID
        num_id = self._get_next_id()
        artifact_id = f"art:{num_id}"

        # Determine file paths (use numeric part for filenames)
        bin_path = self.artifacts_dir / f"art-{num_id}.bin"
        json_path = self.artifacts_dir / f"art-{num_id}.json"

        # Write binary content
        with open(bin_path, 'wb') as f:
            f.write(blob)

        # Create metadata
        content_hash = hashlib.sha256(blob).hexdigest()
        artifact = Artifact(
            id=artifact_id,
            content_type=content_type,
            size_bytes=len(blob),
            source=source,
            descriptor=descriptor
        )

        # Write metadata as JSON
        metadata = artifact.model_dump()
        metadata['created_at'] = datetime.now().isoformat()
        metadata['sha256'] = content_hash

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return artifact_id
    
    def get_bytes(self, artifact_id: str) -> bytes:
        """
        Retrieve the raw bytes of an artifact.

        Args:
            artifact_id: The artifact identifier (format: "art:<int>")

        Returns:
            The raw bytes

        Raises:
            FileNotFoundError: If the artifact doesn't exist
        """
        # Extract numeric part from "art:123" -> "123"
        num_id = artifact_id.split(":")[-1]
        bin_path = self.artifacts_dir / f"art-{num_id}.bin"

        if not bin_path.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_id}")

        with open(bin_path, 'rb') as f:
            return f.read()

    def get_meta(self, artifact_id: str) -> Artifact:
        """
        Retrieve the metadata of an artifact.

        Args:
            artifact_id: The artifact identifier (format: "art:<int>")

        Returns:
            Artifact object with metadata

        Raises:
            FileNotFoundError: If the artifact doesn't exist
        """
        # Extract numeric part from "art:123" -> "123"
        num_id = artifact_id.split(":")[-1]
        json_path = self.artifacts_dir / f"art-{num_id}.json"

        if not json_path.exists():
            raise FileNotFoundError(f"Artifact metadata not found: {artifact_id}")

        with open(json_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        # Remove extra fields that aren't part of Artifact schema
        artifact_fields = {k: v for k, v in metadata.items()
                          if k in ['id', 'content_type', 'size_bytes', 'source', 'descriptor']}

        return Artifact(**artifact_fields)

    def exists(self, artifact_id: str) -> bool:
        """
        Check if an artifact exists.

        Args:
            artifact_id: The artifact identifier (format: "art:<int>")

        Returns:
            True if both .bin and .json files exist, False otherwise
        """
        # Extract numeric part from "art:123" -> "123"
        num_id = artifact_id.split(":")[-1]
        bin_path = self.artifacts_dir / f"art-{num_id}.bin"
        json_path = self.artifacts_dir / f"art-{num_id}.json"

        return bin_path.exists() and json_path.exists()
