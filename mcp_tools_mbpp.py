from mcp.server.fastmcp import FastMCP
from standbox.swe_bench import run_in_docker

mcp = FastMCP("mbpp")

def run_tests(code, list_test):
    code = code + "\n" + "\n".join(list_test)
    script = f"cat <<'EOF' > /testbed/test_script.py\n{code}\nEOF\npython3 /testbed/test_script.py"
    result = run_in_docker(script)
    if "Traceback" in result or "Error" in result:
        return {"success": False, "output": result}
    else:
        return {"success": True, "output": result}
    return result
