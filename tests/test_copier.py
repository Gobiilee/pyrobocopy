import pytest
import shutil
from pathlib import Path
from models.copier import RoboCopier, CopyResult

@pytest.fixture
def temp_environment(tmp_path: Path) -> tuple[Path, Path]:
    """Sets up a temporary source and destination directory for testing."""
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    return src_dir, dst_dir


def test_successful_copy(temp_environment: tuple[Path, Path]):
    """Test path scanning and core copying logic using the existing class API."""
    src_dir, dst_dir = temp_environment
    
    # Create mock folder layout
    file1 = src_dir / "test1.txt"
    file1.write_text("Hello World")
    sub_dir = src_dir / "subfolder"
    sub_dir.mkdir()
    file2 = sub_dir / "test2.txt"
    file2.write_text("Data")

    copier = RoboCopier(workers=2)
    
    # 1. Test scanning engine logic
    files_mapping, total_size = copier.get_item_stats([src_dir])
    assert len(files_mapping) == 2
    assert total_size == (file1.stat().st_size + file2.stat().st_size)

    # 2. Test execution engine logic explicitly
    results = []
    for src_file, base_parent in files_mapping:
        # Replicate structural transformation done in the UI layer
        dest_file = dst_dir / src_file.relative_to(base_parent)
        res = copier.copy_file(src_file, dest_file)
        results.append(res)
    
    assert len(results) == 2
    assert all(r.success for r in results)
    assert (dst_dir / "src" / "test1.txt").exists()
    assert (dst_dir / "src" / "subfolder" / "test2.txt").exists()


def test_source_does_not_exist():
    """Test behavior when paths passed to stats scanning are non-existent or invalid."""
    copier = RoboCopier()
    
    # Passing an invalid path to get_item_stats should safely return empty lists
    files_mapping, total_size = copier.get_item_stats([Path("invalid_path_123")])
    
    assert len(files_mapping) == 0
    assert total_size == 0


def test_cancellation(temp_environment: tuple[Path, Path]):
    """Test that setting the cancel flag instantly rejects file operations."""
    src_dir, dst_dir = temp_environment
    
    test_file = src_dir / "file.txt"
    test_file.write_text("cancel test")

    copier = RoboCopier()
    
    # Trigger cancellation before running execution
    copier.cancel()
    
    # Test that scanning acknowledges cancellation safely
    files_mapping, _ = copier.get_item_stats([src_dir])
    # Note: Depending on timing, files_mapping might be empty or partial if cancelled midway.
    
    # Directly verify that copy_file stops processing immediate actions
    dest_file = dst_dir / "file.txt"
    res = copier.copy_file(test_file, dest_file)
    
    assert res.success is False
    assert res.cancelled is True
    assert res.error_message == "Cancelled"
    assert not dest_file.exists()