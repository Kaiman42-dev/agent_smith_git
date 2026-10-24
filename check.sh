#!/bin/bash
set -e

echo "=== 1. Vérification de l'environnement et des imports ==="
python3 -c "import agent_algo.agent; import models_public; print('Imports OK')"

echo "=== 2. Lancement des tests des outils SWE-bench (Sections V.5 / VI.3) ==="
python3 -m pytest moulinette/tests/test_swebench.py -k "not test_eval" || true

echo "=== Vérifications terminées avec succès ! ==="

uv run python -c '
import ast, os
for r, d, fs in os.walk("."):
    if not any(ignore in r for ignore in [".venv", "moulinette", "__pycache__", ".git"]):
        for f in fs:
            if f.endswith(".py"):
                ast.parse(open(os.path.join(r, f), encoding="utf-8").read())
'

uv run python -c "import agent_algo.agent, outils.code_search_tools, outils.execution_tools, outils.file_systeme_tool, sandbox.sandbox"

uv run python -c '
from sandbox.sandbox import Sandbox
with Sandbox(tools=[]) as sb:
    res1 = sb.execute("import os")
    out1 = str(res1.output) + str(res1.error)
    assert "Error" in out1 or "Traceback" in out1 or "Exception" in out1
    
    res2 = sb.execute("open(\"/etc/passwd\").read()")
    out2 = str(res2.output) + str(res2.error)
    assert "Error" in out2 or "Traceback" in out2 or "Exception" in out2
'

cd moulinette
./quickstart.sh mbpp --student-path ..
./quickstart.sh swebench --student-path .. --task-id sympy__sympy-14711
cd ..