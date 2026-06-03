import shutil
import time
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

def copy_file(src, dst):
    """Worker function to copy a single file."""
    try:
        shutil.copy2(src, dst) 
        return True, src
    except Exception as e:
        return False, f"{src} -> Error: {e}"

def get_folder_stats(src_path):
    """Scans the folder to return a list of files and total size in bytes."""
    files = []
    total_size_bytes = 0
    
    for f in src_path.rglob('*'):
        if f.is_file():
            files.append(f)
            total_size_bytes += f.stat().st_size 
            
    return files, total_size_bytes

def parallel_copy_with_stats(src_dir, dest_dir, workers=8):
    src_path = Path(src_dir)
    dst_path = Path(dest_dir) / src_path.name 

    if not src_path.exists():
        print(f"Error: The src folder '{src_dir}' does not exist.")
        return

    print("Scanning directory, calculating size, and mapping folder structure...")
    
    files, total_size_bytes = get_folder_stats(src_path)
    total_files = len(files)
    total_size_mb = total_size_bytes / (1024 * 1024)
    
    print(f"Total files found: {total_files}")
    print(f"Total size to copy: {total_size_mb:.2f} MB\n")

    dst_path.mkdir(parents=True, exist_ok=True)
    
    # ---------------------------------------------------------
    # 1. DIRECTORY CREATION PERCENTAGE
    # ---------------------------------------------------------
    directories = [d for d in src_path.rglob('*') if d.is_dir()]
    total_dirs = len(directories)
    
    if total_dirs > 0:
        for i, d in enumerate(directories, 1):
            rel_path = d.relative_to(src_path)
            (dst_path / rel_path).mkdir(parents=True, exist_ok=True)
            
            # Calculate % and print on the same line using \r
            percent = (i / total_dirs) * 100
            print(f"\rCreating Folders: {percent:.1f}% ({i}/{total_dirs})", end="", flush=True)
        print() # Move to the next line when done

    # ---------------------------------------------------------
    # 2. FILE COPY PERCENTAGE
    # ---------------------------------------------------------
    print(f"Starting parallel copy using {workers} threads...")
    success_count = 0
    
    start_time = time.perf_counter()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for f in files:
            dest_file = dst_path / f.relative_to(src_path)
            futures.append(executor.submit(copy_file, f, dest_file))

        for future in as_completed(futures):
            success, result = future.result()
            if success:
                success_count += 1
                
                # Calculate % and print on the same line using \r
                percent = (success_count / total_files) * 100
                print(f"\rCopying Files: {percent:.1f}% ({success_count}/{total_files})", end="", flush=True)
            else:
                # Print a newline first so the error doesn't overwrite the progress bar
                print(f"\nFailed: {result}")

    # Move to the next line after the progress bar finishes
    print() 

    end_time = time.perf_counter()
    
    duration_seconds = max(end_time - start_time, 0.001) 
    speed_mb_per_second = total_size_mb / duration_seconds

    print("\n" + "="*30)
    print("       COPY SUMMARY")
    print("="*30)
    print(f"Files Copied : {success_count} / {total_files}")
    print(f"Total Data   : {total_size_mb:.2f} MB")
    print(f"Time Taken   : {duration_seconds:.2f} seconds")
    print(f"Avg Speed    : {speed_mb_per_second:.2f} MB/s")
    print("="*30)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A fast, parallel folder copying tool in Python.")
    parser.add_argument("--src", required=True, help="Path to the src folder")
    parser.add_argument("--dst", default=r"E:\Backup", help="Path to the dst folder")
    parser.add_argument("--workers", type=int, default=8, help="Number of threads to use (default: 8)")
    
    args = parser.parse_args()
    parallel_copy_with_stats(args.src, args.dst, workers=args.workers)