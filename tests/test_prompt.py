"""O prompt real renderiza com as variáveis que o grafo passa (os testes de fluxo trocam
a cadeia prompt + LLM inteira, então não passam por aqui)."""

from langchain_core.messages import HumanMessage

from src.prompts import descrever_canal, prompt_atendimento


def renderizar(canal: str) -> str:
    return prompt_atendimento.invoke({"messages": [HumanMessage("oi")], "canal": canal}).messages[0].content


def test_whatsapp_informa_telefone_e_nome():
    sistema = renderizar(descrever_canal("whatsapp", "5511988887777", "Jo"))
    assert "+5511988887777" in sistema and "Jo (pode ser apelido" in sistema
    assert "MED-01" in sistema  # corpo clínico
    assert "(hoje)" in sistema  # calendário dos próximos dias


def test_chat_web_sem_telefone():
    assert "telefone do paciente não é conhecido" in renderizar(descrever_canal(None))
