import json
import keyword
import re


# PARSING
# Chaque fonction renvoie du code Python a executer, ou None si son format est absent.
# Les formats non Python sont convertis en appels Python : la sandbox ne voit que du Python.

def p_mardown(s):
	"""recupe code python qui vient de la reponse du llm (```python ou ```py, <end_code> facultatif)"""
	rep = re.findall(r"```(?:python|py)[ \t]*\n(.*?)```", s, re.DOTALL) # (.*?) balise de capture, re.DOTALL capture vraiment tout
	if not rep: # pas de bloc python = pas de code a executer
		return None
	return rep[0].replace("<end_code>", "")

def appel_python(name, arguments):
	"""construit `result = name(...)` + print(result), ou None si l'appel est invalide.

	name et arguments viennent du LLM : on n'accepte que des identifiants Python,
	et les valeurs passent par repr(), donc rien d'autre que l'appel n'est execute.
	"""
	if not isinstance(name, str) or not name.isidentifier() or keyword.iskeyword(name):
		return None
	if isinstance(arguments, dict):
		if not all(isinstance(k, str) and k.isidentifier() and not keyword.iskeyword(k) for k in arguments):
			return None
		args = ", ".join(f"{k}={v!r}" for k, v in arguments.items())
	else: # une seule valeur sans nom (ex. Action Input: une chaine)
		args = repr(arguments)
	# print : sinon l'observation serait vide, le LLM ne verrait pas le resultat de son outil
	return f"result = {name}({args})\nprint(result)\n"

def joindre(appels):
	"""un seul bloc de code pour plusieurs appels ; None si l'un d'eux est invalide"""
	if not appels or None in appels:
		return None
	return "".join(appels)

def valeur_xml(texte):
	"""les parametres XML sont du texte : "12" -> 12, "true" -> True, '{"a": 1}' -> dict, sinon la chaine"""
	try:
		return json.loads(texte)
	except ValueError:
		return texte

def p_XML(s):
	"""<invoke name="outil"><parameter name="cle">valeur</parameter></invoke> (style Anthropic)"""
	appels = []
	for name, corps in re.findall(r'<invoke name="([^"]*)">(.*?)</invoke>', s, re.DOTALL):
		params = re.findall(r'<parameter name="([^"]*)">(.*?)</parameter>', corps, re.DOTALL)
		appels.append(appel_python(name, {k: valeur_xml(v.strip()) for k, v in params}))
	return joindre(appels)

def appel_json(data):
	"""{"name": "outil", "arguments": {...}} -> appel Python, None si ce n'est pas un appel d'outil"""
	if not isinstance(data, dict) or "name" not in data:
		return None
	arguments = data.get("arguments", data.get("parameters", {}))
	if isinstance(arguments, str): # certaines API envoient les arguments en chaine JSON
		try:
			arguments = json.loads(arguments)
		except ValueError:
			return None
	return appel_python(data["name"], arguments)

def p_json(s):
	"""<tool_call>{"name": "outil", "arguments": {...}}</tool_call> (style Hermes)"""
	appels = []
	for bloc in re.findall(r"<tool_call>(.*?)</tool_call>", s, re.DOTALL):
		try:
			appels.append(appel_json(json.loads(bloc.strip())))
		except ValueError:
			return None
	return joindre(appels)

def p_json_brut(s):
	"""la reponse entiere est un appel JSON sans balises : {"name": ..., "arguments": ...} ou une liste.
	C'est ce que renvoie Groq dans failed_generation quand il refuse un appel d'outil natif."""
	try:
		data = json.loads(s.strip())
	except ValueError:
		return None
	return joindre([appel_json(d) for d in (data if isinstance(data, list) else [data])])

def p_ReAct(s):
	"""Action: outil / Action Input: {...}"""
	m = re.search(r"^\s*Action:\s*(\S+)\s*\n\s*Action Input:\s*(.*)", s, re.MULTILINE | re.DOTALL)
	if m is None:
		return None
	name, entree = m.group(1), m.group(2).strip()
	try:
		# raw_decode lit le JSON du debut et ignore ce qui suit (le LLM continue parfois a ecrire)
		arguments, _ = json.JSONDecoder().raw_decode(entree)
	except ValueError:
		arguments = entree.splitlines()[0].strip() if entree else ""
	return appel_python(name, arguments)

def extraire_code(s):
	"""essaie les formats dans l'ordre du sujet (V.1) : Python, XML, JSON/Hermes, ReAct.
	Le JSON sans balises (appel d'outil natif) passe juste apres le JSON/Hermes.

	Renvoie le code Python a executer, ou None si la reponse n'en contient pas.
	"""
	for parseur in (p_mardown, p_XML, p_json, p_json_brut, p_ReAct):
		code = parseur(s)
		if code is not None:
			return code
	return None
