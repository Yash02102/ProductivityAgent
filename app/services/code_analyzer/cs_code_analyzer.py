import subprocess
import json
import os
from config import settings
def analyze_cs_file_with_roslyn(content: str):
    analyze_exe = settings.cs_code_analyzer
    if not analyze_exe:
        return []
    try:
        result = subprocess.check_output(
            ["dotnet", analyze_exe, "-"],
            input=content, text=True, encoding="utf-8",
            stderr=subprocess.STDOUT, timeout=20
        )
        return json.loads(result)
    except subprocess.CalledProcessError as e:
        print(e)
        return []
    except Exception:
        return []