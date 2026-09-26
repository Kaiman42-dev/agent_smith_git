import json

def p_mbpp(filepath):
	try:
		with open(filepath, 'r') as f:
			dic = json.load(f)
		return dic
	except:
		return "Erreur"

if __name__ == "__main__":
	print(p_mbpp("Json/question.json"))