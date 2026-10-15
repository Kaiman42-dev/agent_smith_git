from pydantic import BaseModel, Field
from typing import List
import json

class SWEBenchTaskInput(BaseModel):
    instance_id: str
    problem_statement: str
    docker_image: str
    eval_script: str
    repo: str
    

class MBPPTaskInput(BaseModel):
    task_id: int
    task_definition: str
    function_definition: str
    test_imports: List[str] = Field(default_factory=list)
    test_list: List[str] = Field(default_factory=list)


def p_SWE(filepath):
    try:
        with open(filepath , 'r', encoding='utf-8') as f:
            dic = json.load(f)
        return SWEBenchTaskInput(**dic) # verifie les donner automatiquement
    except Exception as e:
        return f"Error : {e}"

def p_mbpp(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            dic = json.load(f)
        return MBPPTaskInput(**dic)
    except Exception as e:
        return f"Error : {e}"


"""
if __name__ == "__main__":
	print(p_mbpp("Json/question.json"))
"""