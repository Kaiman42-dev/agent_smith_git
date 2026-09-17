import json
import ast
from bs4 import BeautifulSoup


# PARSING

def p_mardown(s):
	try:
		_, rep,  = s.split("```python" or "```.")
		res = rep.replace("```", "").strip()
	except:
		return ""
	return res

def p_json(s):
	try:
		_, js = s.split("<tool_call>" or "</tool_call>.")
		clear_js = js.replace("</tool_call>", "")
		data = json.loads(clear_js.strip())
		
		name = data['name']
		arguments = data['arguments']
		
		filepath = arguments['filepath']
		start = arguments["start_line"]
		end = arguments ['end_line']

		return f"""result = {name}(filepath="{filepath}", start_line={start}, end_line={end})\n"""
	except:
		return "Error"

def p_XML(s):
	try:
		soup = BeautifulSoup(s, "xml")
		name = soup.invoke["name"]
		filepath = soup.find("parameter", attrs={"name": "filepath"}).text
		start_line = soup.find("parameter", attrs={"name": "start_line"}).text
		end_line = soup.find("parameter", attrs={"name": "end_line"}).text
		return f"""result = {name}(filepath="{filepath}", start_line={start_line}, end_line={end_line})\n"""
	except:
		return "Error"

def p_ReAct(s):
	n = s.split("Action:")[1].strip()
	name = n.split()[0]
	di = n.split("Action Input:")[1].strip()
	dic = json.loads(di)
	return f"""result = {name}(filepath="{dic['filepath']}", start_line={dic['start_line']}, end_line={dic['end_line']})\n"""
"""
if __name__ == "__main__":
	aa = """Thought: I need to check the configuration file to understand the environment.
	Action: read_file
	Action Input: {"filepath": "/testbed/config.json", "start_line": 1, "end_line": 100}"""
	resultat = p_ReAct(aa)
	print(resultat)
"""


















"""
def parsing(s):
    _, rep, _ = s.split("```" or "```.")
    clear = rep[6:].strip()
    _, a = clear.split('(')
    clear = a[1:-1]
    c, a , b = clear.split(",")
    lst = [c[:-1], int(a.strip()), int(b.strip())]
    print(lst)
"""