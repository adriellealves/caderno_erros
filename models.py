from typing import List, Optional
from pydantic.v1 import BaseModel, validator

class Questao(BaseModel):
    numero: Optional[str]
    tipo: Optional[str]
    disciplina: str
    aula: Optional[str]
    origem_pdf: Optional[str]
    enunciado: str
    alternativas: List[str]
    resposta_correta: Optional[str]
    comentario: Optional[str]

    @validator('alternativas', pre=True, allow_reuse=True)
    def parse_alternativas(cls, v):
        if isinstance(v, str):
            import json, ast
            try:
                return json.loads(v)
            except Exception:
                try:
                    return ast.literal_eval(v)
                except Exception:
                    return [v]
        if isinstance(v, list):
            return v
        return [str(v)]

    @validator('disciplina', 'enunciado', allow_reuse=True)
    def not_empty(cls, v):
        if not v or not str(v).strip():
            raise ValueError('Campo obrigatório vazio')
        return v.strip()

    @validator('resposta_correta', 'comentario', 'aula', 'tipo', 'numero', 'origem_pdf', pre=True, always=True, allow_reuse=True)
    def default_none(cls, v):
        return v if v is not None else None
