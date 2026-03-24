"""
Quick Check - Are chunks being split properly?
Run this to see if your chunker needs the SafeTextSplitter fix
"""

import sys
from pathlib import Path

chunker_path = Path("norwegian_chunker.py")

if not chunker_path.is_file():
    raise FileNotFoundError(f"❌ File not found: {chunker_path.resolve()}")

content = chunker_path.read_text(encoding="utf-8")
print("✅ Chunker file loaded successfully")

print("=" * 70)
print("CHUNKER SAFETY CHECK")
print("=" * 70)

# Check for SafeTextSplitter
has_splitter = "SafeTextSplitter" in content
print(f"\n1. SafeTextSplitter class: {'✅ FOUND' if has_splitter else '❌ MISSING'}")

# Check for max size limit
has_max_size = "1800" in content or "MAX_CHUNK_SIZE" in content
print(f"2. Max chunk size limit: {'✅ FOUND' if has_max_size else '❌ MISSING'}")

# Check for split_text method
has_split_method = "split_text" in content
print(f"3. Text splitting method: {'✅ FOUND' if has_split_method else '❌ MISSING'}")

print("\n" + "=" * 70)

if not has_splitter:
    print("❌ CHUNKER NEEDS UPDATE!")
    print("=" * 70)
    print("\nYour chunker is creating chunks that are too large:")
    print("• Max seen: 181,456 chars")
    print("• Safe limit: 1,800 chars")
    print("\nThis is why embeddings fail!")
    print("\nFIX:")
    print("1. Replace chunker.py with chunker_safe.py")
    print("2. Run pipeline again")
else:
    print("✅ CHUNKER HAS SAFETY FIXES")
    print("=" * 70)
    print("\nYour chunker should split large chunks automatically.")
    print("If you still see chunks > 2000 chars, there may be a bug.")