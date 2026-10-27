"""Canal WhatsApp: webhook de ponta a ponta (FastAPI + grafo real + LLM roteirizado),
com o envio pela Graph API trocado por um cliente falso."""

import hashlib
import hmac
import json
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from api.routes import app
from src.services.whatsapp_service import MENSAGEM_ERRO, MENSAGEM_SO_TEXTO, AtendimentoWhatsApp
from src.whatsapp import assinatura_valida, extrair_mensagens
from src.whatsapp.cliente import WhatsAppCliente, dividir, para_whatsapp

TELEFONE = "5511988887777"
SEGREDO = "segredo-teste"  # WHATSAPP_APP_SECRET do conftest


class ClienteFalso:
    def __init__(self) -> None:
        self.enviadas: list[tuple[str, str]] = []
        self.lidas: list[str] = []

    async def enviar_texto(self, telefone: str, texto: str) -> None:
        self.enviadas.append((telefone, texto))

    async def marcar_como_lida(self, mensagem_id: str) -> None:
        self.lidas.append(mensagem_id)

    async def fechar(self) -> None:
        pass


def payload(*mensagens: dict, nome="João") -> dict:
    return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{
        "field": "messages",
        "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "551140028922", "phone_number_id": "1234567890"},
            "contacts": [{"profile": {"name": nome}, "wa_id": TELEFONE}],
            "messages": list(mensagens),
        },
    }]}]}


def texto(corpo: str, id_="wamid.1") -> dict:
    return {"from": TELEFONE, "id": id_, "timestamp": "1790000000", "type": "text", "text": {"body": corpo}}


def assinar(corpo: bytes, segredo: str = SEGREDO) -> str:
    return "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


@pytest.fixture
def cliente_falso():
    return ClienteFalso()


@pytest.fixture
def api(cliente_falso, calendario):
    with TestClient(app) as client:
        client.app.state.whatsapp._cliente = cliente_falso
        yield client


def postar(api: TestClient, dados: dict, assinatura: str | None = None) -> httpx.Response:
    corpo = json.dumps(dados).encode()
    return api.post(
        "/webhook/whatsapp",
        content=corpo,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": assinatura or assinar(corpo)},
    )


# --- webhook ---------------------------------------------------------------

def test_verificacao_do_webhook(api):
    params = {"hub.mode": "subscribe", "hub.verify_token": "verifica-teste", "hub.challenge": "12345"}
    resposta = api.get("/webhook/whatsapp", params=params)
    assert resposta.status_code == 200 and resposta.text == "12345"

    params["hub.verify_token"] = "errado"
    assert api.get("/webhook/whatsapp", params=params).status_code == 403


def test_assinatura_invalida_e_rejeitada(api, cliente_falso, roteirizar):
    llm = roteirizar()
    resposta = postar(api, payload(texto("oi")), assinatura=assinar(b"outro corpo"))
    assert resposta.status_code == 403
    assert cliente_falso.enviadas == [] and llm.entradas == []


def test_mensagem_de_texto_recebe_resposta(api, cliente_falso, roteirizar):
    llm = roteirizar(AIMessage(content="Olá, João! Como posso ajudar?"))

    resposta = postar(api, payload(texto("Oi, quero marcar consulta")))

    assert resposta.status_code == 200
    assert cliente_falso.lidas == ["wamid.1"]
    assert cliente_falso.enviadas == [(TELEFONE, "Olá, João! Como posso ajudar?")]
    # o agente recebe o telefone e o nome do perfil pelo prompt
    assert f"+{TELEFONE}" in llm.entradas[0]["canal"]
    assert "João" in llm.entradas[0]["canal"]


def test_reentrega_da_meta_e_ignorada(api, cliente_falso, roteirizar):
    roteirizar(AIMessage(content="Resposta única"))
    postar(api, payload(texto("oi")))
    postar(api, payload(texto("oi")))  # mesmo id
    assert len(cliente_falso.enviadas) == 1


def test_mensagens_seguidas_mantem_o_historico(api, cliente_falso, roteirizar):
    llm = roteirizar(AIMessage(content="Qual especialidade?"), AIMessage(content="Certo!"))
    postar(api, payload(texto("Quero marcar", "wamid.1")))
    postar(api, payload(texto("Cardiologia", "wamid.2")))
    assert [m.content for m in llm.historicos[-1]] == ["Quero marcar", "Qual especialidade?", "Cardiologia"]


def test_audio_recebe_aviso_sem_chamar_o_agente(api, cliente_falso, roteirizar):
    llm = roteirizar()
    audio = {"from": TELEFONE, "id": "wamid.a", "type": "audio", "audio": {"id": "m1"}}
    postar(api, payload(audio))
    assert cliente_falso.enviadas == [(TELEFONE, MENSAGEM_SO_TEXTO)]
    assert llm.entradas == []


def test_status_de_entrega_nao_gera_resposta(api, cliente_falso):
    dados = payload()
    dados["entry"][0]["changes"][0]["value"] = {
        "messaging_product": "whatsapp",
        "statuses": [{"id": "wamid.x", "status": "delivered", "recipient_id": TELEFONE}],
    }
    assert postar(api, dados).status_code == 200
    assert cliente_falso.enviadas == []


def test_falha_do_agente_vira_mensagem_amigavel(api, cliente_falso, monkeypatch):
    async def quebra(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr("src.services.chat_service.conversar", quebra)
    postar(api, payload(texto("oi")))
    assert cliente_falso.enviadas == [(TELEFONE, MENSAGEM_ERRO)]


# --- sessão ----------------------------------------------------------------

def test_conversa_recomeca_depois_da_sessao(app_grafo):
    agora = [0.0]
    atendimento = AtendimentoWhatsApp(app_grafo, ClienteFalso(), timedelta(minutes=120), relogio=lambda: agora[0])

    primeira = atendimento._conversa_do_paciente(TELEFONE)
    agora[0] = 119 * 60
    assert atendimento._conversa_do_paciente(TELEFONE) == primeira  # conta a partir da última mensagem
    agora[0] += 121 * 60
    assert atendimento._conversa_do_paciente(TELEFONE) != primeira


# --- funções auxiliares ----------------------------------------------------

def test_assinatura():
    assert assinatura_valida(b"{}", assinar(b"{}"), SEGREDO)
    assert not assinatura_valida(b"{}", assinar(b"{}", "outro"), SEGREDO)
    assert not assinatura_valida(b"{}", None, SEGREDO)


def test_extrair_resposta_de_botao():
    botao = {"from": TELEFONE, "id": "wamid.b", "type": "interactive",
             "interactive": {"type": "button_reply", "button_reply": {"id": "s", "title": "Sim"}}}
    [mensagem] = extrair_mensagens(payload(botao, nome="Ana"))
    assert (mensagem.texto, mensagem.nome_perfil, mensagem.telefone) == ("Sim", "Ana", TELEFONE)


def test_formatacao_para_whatsapp():
    assert para_whatsapp("## Horários\n**14:20** ou *15:00*") == "*Horários*\n*14:20* ou *15:00*"


def test_dividir_mensagem_longa():
    partes = dividir("linha\n" * 1000, limite=100)
    assert all(len(p) <= 100 for p in partes)
    assert "\n".join(partes).split() == ["linha"] * 1000


@pytest.mark.anyio
async def test_cliente_envia_para_graph_api():
    requisicoes = []

    def responder(request: httpx.Request) -> httpx.Response:
        requisicoes.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.r"}]})

    cliente = WhatsAppCliente("tok", "999", "v23.0")
    cliente._http = httpx.AsyncClient(
        base_url="https://graph.facebook.com/v23.0/999",
        headers={"Authorization": "Bearer tok"},
        transport=httpx.MockTransport(responder),
    )
    await cliente.enviar_texto(TELEFONE, "**Olá**")
    await cliente.fechar()

    [req] = requisicoes
    assert str(req.url) == "https://graph.facebook.com/v23.0/999/messages"
    assert req.headers["Authorization"] == "Bearer tok"
    assert json.loads(req.content)["text"]["body"] == "*Olá*"
    assert json.loads(req.content)["to"] == TELEFONE
