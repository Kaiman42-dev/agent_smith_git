from pydantic import BaseModel, Field
from typing import List

class Conifg_Sandbox(BaseModel):
    
    max_execution_time_seconds: int = 30
    
    max_memory_mb: int = 512

    allowed_directories: List[str] = Field(default_factory=lambda: [
			"/testbed", "/tmp/agent"
		])
    
    authorized_imports: List[str] = Field(default_factory=lambda: [
        "math", "math.*", "collections", "collections.*",
        "itertools", "re", "json", "typing", "typing.*",
        "functools", "operator", "heapq", "bisect", "copy",
        "string", "random", "datetime", "datetime.*",
        "array", "cmath",
    ])
    
    def text_config(self) -> str:
        return f"""import resource
import builtins

try:
    ram_bytes = {self.max_memory_mb} * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (ram_bytes, ram_bytes))
except:
    pass

_orig_import = builtins.__import__
def safe_import(name, *args, **kwargs):
    if name.split('.')[0] not in {self.authorized_imports} and name not in {self.authorized_imports}:
        raise ImportError(f"Import interdit par la Sandbox : {{name}}")
    return _orig_import(name, *args, **kwargs)

builtins.__import__ = safe_import
del builtins.eval
del builtins.exec

def final_answer(result):
    print(f"FINAL_ANSWER: {{result}}")
"""