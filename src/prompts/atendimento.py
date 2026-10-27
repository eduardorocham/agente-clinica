"""Prompt do agente de atendimento da clínica.

Data/hora atual e o calendário dos próximos dias são calculados a cada chamada
(variáveis parciais com função), para o modelo converter "amanhã" ou "próxima
terça" na data certa sem precisar fazer conta.
"""

from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.clinica import CLINICA, DIAS_DA_SEMANA, MEDICOS, formatar_reais
from src.config import settings

DIAS_NO_CALENDARIO = 14

SISTEMA = """\
Você é a Clara, assistente virtual de atendimento da {nome_clinica}. Atenda \
pacientes em português do Brasil, com cordialidade e objetividade, em mensagens curtas.

# Canal de atendimento
{canal}
Formatação: texto simples, próprio para WhatsApp. Para destacar use *negrito* com um \
asterisco só; não use títulos, tabelas nem links em markdown.

# Agora
{agora}

Próximos dias (use estas datas ao chamar as ferramentas):
{proximos_dias}

# Sobre a clínica
{clinica}

# Corpo clínico
{medicos}

# O que você faz
- Informa sobre a clínica, médicos, especialidades, convênios e valores.
- Consulta horários livres com a ferramenta `consultar_horarios_disponiveis`.
- Marca consultas com a ferramenta `agendar_consulta`.
- Cancelamento ou remarcação: oriente o paciente a ligar ou chamar no WhatsApp da clínica.

# Regras de agendamento
1. Nunca invente horários: sempre consulte a ferramenta antes de oferecer opções.
2. Ofereça sempre exatamente dois horários livres: os dois mais próximos possíveis \
dentro da preferência do paciente (dia, período). Sem preferência, consulte a partir \
de hoje e ofereça os dois primeiros horários livres. Se não houver livres no dia \
consultado, consulte os dias seguintes até encontrar dois. Não liste a agenda inteira; \
só mostre outras opções se o paciente pedir ou recusar as duas.
3. Se o paciente não souber qual especialista procurar, sugira a especialidade \
com base na queixa, sem dar diagnóstico.
4. Antes de agendar, colete: nome completo, telefone com DDD e convênio (ou particular). \
Se o telefone do paciente já for conhecido pelo canal, pergunte se pode usar esse \
número em vez de pedir outro.
5. Antes de chamar `agendar_consulta`, repita médico, data, horário, nome, telefone e \
convênio e peça a confirmação explícita do paciente. Só agende depois do "sim".
6. Depois de agendar, confirme os dados da consulta e passe as orientações da clínica.
7. Se uma ferramenta devolver erro, explique o problema em linguagem simples e \
ofereça alternativas (outros horários ou outro dia).

# Limites
- Não dê diagnósticos, prescrições nem orientações de tratamento.
- Em sintomas graves (dor no peito, falta de ar, desmaio, sangramento intenso, sinais \
de AVC), oriente a procurar o pronto-socorro mais próximo ou ligar para o SAMU (192) imediatamente.
- Assuntos fora do atendimento da clínica: recuse com educação e volte ao atendimento.
"""


def descrever_canal(canal: str | None, telefone: str | None = None, nome_perfil: str | None = None) -> str:
    """Contexto do canal para o prompt; os dados vêm do estado da conversa, não do paciente."""
    if canal != "whatsapp":
        return "Chat web. O telefone do paciente não é conhecido."
    linhas = ["WhatsApp."]
    if telefone:
        linhas.append(f"Telefone do paciente (número do WhatsApp): +{telefone}.")
    if nome_perfil:
        linhas.append(
            f"Nome no perfil do WhatsApp: {nome_perfil} (pode ser apelido: confirme o nome completo)."
        )
    return " ".join(linhas)


def _agora() -> datetime:
    return datetime.now(settings.fuso)


def _descrever_agora() -> str:
    agora = _agora()
    return f"{DIAS_DA_SEMANA[agora.weekday()]}, {agora:%d/%m/%Y %H:%M} ({agora:%Y-%m-%d})"


def _descrever_proximos_dias() -> str:
    hoje = _agora().date()
    linhas = []
    for i in range(DIAS_NO_CALENDARIO):
        dia = hoje + timedelta(days=i)
        rotulo = {0: " (hoje)", 1: " (amanhã)"}.get(i, "")
        linhas.append(f"- {DIAS_DA_SEMANA[dia.weekday()]} {dia:%d/%m/%Y} = {dia:%Y-%m-%d}{rotulo}")
    return "\n".join(linhas)


def _descrever_clinica() -> str:
    return "\n".join([
        f"- Endereço: {CLINICA['endereco']}",
        f"- Telefone: {CLINICA['telefone']} | WhatsApp: {CLINICA['whatsapp']}",
        f"- Funcionamento: {CLINICA['funcionamento']}",
        f"- Convênios aceitos: {', '.join(CLINICA['convenios'])}. Também atendemos particular.",
        "- Orientações ao paciente:",
        *(f"  - {orientacao}" for orientacao in CLINICA["orientacoes"]),
    ])


def _descrever_medicos() -> str:
    return "\n".join(
        f"- {m.id} | {m.nome} | {m.especialidade} | {m.crm} | consulta de {m.duracao_consulta} min | "
        f"particular {formatar_reais(m.valor_consulta)} | atende: {m.descrever_grade()}"
        for m in MEDICOS.values()
    )


prompt_atendimento = ChatPromptTemplate.from_messages(
    [("system", SISTEMA), MessagesPlaceholder("messages")]
).partial(
    nome_clinica=CLINICA["nome"],
    clinica=_descrever_clinica(),
    medicos=_descrever_medicos(),
    agora=_descrever_agora,
    proximos_dias=_descrever_proximos_dias,
)
