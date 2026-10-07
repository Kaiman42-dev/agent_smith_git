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
import os
import socket


try:
    ram_bytes = {self.max_memory_mb} * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (ram_bytes, ram_bytes))
except:
    pass


def block_socket(*args, **kwargs):
    raise PermissionError("Réseau bloqué par la Sandbox")
socket.socket = block_socket


_orig_open = builtins.open
ALLOWED_DIRS = {self.allowed_directories}

def safe_open(file, *args, **kwargs):
    abs_path = os.path.abspath(file)

    if not any(abs_path.startswith(os.path.abspath(d)) for d in ALLOWED_DIRS):
        raise PermissionError(f"Accès interdit au fichier : {{file}}")
    return _orig_open(file, *args, **kwargs)

builtins.open = safe_open


_orig_import = builtins.__import__
ALLOWED_IMPORTS = {self.authorized_imports}

def safe_import(name, *args, **kwargs):
    base_name = name.split('.')[0]
    if name not in ALLOWED_IMPORTS and base_name not in ALLOWED_IMPORTS and f"{{base_name}}.*" not in ALLOWED_IMPORTS:
        raise ImportError(f"Import interdit par la Sandbox : {{name}}")
    return _orig_import(name, *args, **kwargs)

builtins.__import__ = safe_import

del builtins.eval
del builtins.exec
del builtins.compile

def final_answer(result):
    print(f"FINAL_ANSWER: {{result}}")
"""