from mcp.server.fastmcp import FastMCP
from standbox.swe_bench import run_in_docker

mcp = FastMCP("mbpp")

def run_test(code, list_test):
    code = code + "\n" + "\n".join(list_test)
    script = f"cat <<'EOF' > /testbed/test_scrip.py\n{code}\nEOF\n"
    result = run_in_docker(script)
