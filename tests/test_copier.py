import pytest
from pathlib import Path
from models.copier import RoboCopier

@pytest.fixture
def temp_environment(tmp_path: Path) -> tuple[Path, Path]:
    """Sets up a temporary source and destination directory for testing."""
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    return src_dir, dst_dir

def test_successful_copy(temp_environment: tuple[Path, Path]):
    """Test standard copying of files and folders."""
    src_dir, dst_dir = temp_environment
    
    (src_dir / "test1.txt").write_text("Hello World")
    sub_dir = src_dir / "subfolder"
    sub_dir.mkdir()
    (sub_dir / "test2.txt").write_text("Data")

    copier = RoboCopier(workers=2)
    results = copier.execute_copy(str(src_dir), str(dst_dir))
    
    assert len(results) == 2
    assert all(r.success for r in results)

def test_source_does_not_exist(temp_environment: tuple[Path, Path]):
    """Test behavior when the source directory is missing."""
    _, dst_dir = temp_environment
    copier = RoboCopier()
    
    results = copier.execute_copy("invalid_path_123", str(dst_dir))
    
    assert len(results) == 1
    assert results[0].success is False
    assert "does not exist" in results[0].error_message

def test_cancellation(temp_environment: tuple[Path, Path]):
    """Test that setting the cancel flag stops execution."""
    src_dir, dst_dir = temp_environment
    
    # Create 100 small files
    for i in range(100):
        (src_dir / f"file_{i}.txt").write_text("cancel test")

    copier = RoboCopier(workers=1)
    
    # Pre-trigger cancellation
    copier.cancel() 
    results = copier.execute_copy(str(src_dir), str(dst_dir))
    
    # Since it was cancelled immediately, no valid file operations should return successful
    success_copies = [r for r in results if r.success]
    assert len(success_copies) == 0