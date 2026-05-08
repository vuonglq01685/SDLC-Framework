"""Extract <result>...</result> from a task-notification queue-operation JSON line."""
import json
import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])

raw = src.read_text(encoding="utf-8", errors="replace")

# Each tool-result file holds one JSON object per line, prefixed with "<lineno>:".
line = raw.splitlines()[0]
# Strip leading "<digits>:" prefix from grep -n output.
line = re.sub(r"^\d+:", "", line)
obj = json.loads(line)
content = obj.get("content", "")

# content is the rendered notification block. Extract <result>...</result>.
m = re.search(r"<result>(.*?)</result>", content, re.DOTALL)
if not m:
    dst.write_text(content, encoding="utf-8")
else:
    dst.write_text(m.group(1).strip(), encoding="utf-8")
print(f"wrote {dst}: {dst.stat().st_size} bytes")
