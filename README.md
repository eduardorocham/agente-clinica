# Agente Clínica

Demo de agente de atendimento para uma clínica médica fictícia (**Clínica Vida Plena**),
construído com LangChain + LangGraph, modelo do Google (Gemini API), integração com o
**Google Calendar** para consultar horários livres e marcar consultas e o **WhatsApp**
(Cloud API da Meta) como canal de atendimento.

O histórico das conversas fica só em memória (`InMemorySaver`): nada é gravado em banco
e tudo some quando o processo reinicia.

## Como funciona

```
WhatsApp ──► /webhook/whatsapp ──► whatsapp_service ──┐
                                                      ▼
paciente ──► /conversar ─────────────────────► chat_service ──► grafo LangGraph
                                               │
                                   ┌──► agente (Gemini + prompt da clínica)
                                   │       │ tool_calls?
                                   │       ▼
                                   └── ferramentas ──► agenda_service ──► Google Calendar
```

| Tool | O que faz |
|------|-----------|
| `consultar_horarios_disponiveis(medico_id, data_inicial, dias)` | Grade do médico menos os eventos da agenda, sem horários passados |
| `agendar_consulta(medico_id, data_hora, nome_paciente, telefone, convenio)` | Valida tudo de novo no servidor e cria o evento na agenda |

Regras garantidas pelo servidor (não dependem do LLM): o horário precisa estar na grade do
médico, ser futuro, estar dentro dos próximos 60 dias e livre na agenda no momento da marcação;
convênio precisa ser aceito e telefone ter DDD.

### Dados fictícios

Médicos, grades, valores e convênios ficam em [src/clinica/dados.py](src/clinica/dados.py):

| Código | Médico | Especialidade | Atende | Consulta |
|--------|--------|---------------|--------|----------|
| MED-01 | Dra. Helena Martins | Clínica Geral | seg e qua 08–12; sex 08–12 e 14–17 | 30 min |
| MED-02 | Dr. Rafael Albuquerque | Cardiologia | ter e qui 13–18 | 40 min |
| MED-03 | Dra. Camila Nogueira | Dermatologia | seg 14–18; ter 09–12; qui 09–12 e 14–17 | 30 min |
| MED-04 | Dr. Paulo Mendes | Pediatria | seg a sex 14–18 | 30 min |
| MED-05 | Dra. Beatriz Lima | Ortopedia | qua 13–18:15; sáb 08–12:30 | 45 min |

Convênios: Unimed, Bradesco Saúde, SulAmérica, Amil (e particular).

### Como a agenda é usada

Todas as consultas ficam em **uma** agenda do Google (`GOOGLE_CALENDAR_ID`). O evento de cada
consulta guarda o código do médico em `extendedProperties.private.medico_id`.

- Evento com `medico_id` ocupa o horário só daquele médico.
- Evento **sem** `medico_id` (ex.: "Feriado" ou "Reunião geral" criado à mão na agenda)
  bloqueia o horário de **todos** os médicos.
- Eventos marcados como "Disponível" (transparentes) não bloqueiam nada.

Por isso use uma agenda dedicada à clínica, não a sua agenda pessoal.

## Instalação

```bash
uv sync
cp .env.example .env
```

Preencha `GEMINI_API_KEY` (Google AI Studio). O modelo padrão é o `gemma-4-26b-a4b-it`,
o mesmo do projeto `agente-de-grafos`.

Para testar sem o Google Calendar, use `CALENDARIO_BACKEND=memoria`.

## Configurando o Google Calendar

1. No [Google Cloud Console](https://console.cloud.google.com/), crie (ou escolha) um projeto
   e ative a **Google Calendar API**.
2. No Google Calendar, crie uma agenda nova (ex.: "Clínica Vida Plena") e copie o
   **ID da agenda** em *Configurações da agenda > Integrar agenda*. Coloque em `GOOGLE_CALENDAR_ID`.
3. Escolha **uma** forma de autenticação e salve o JSON como `credentials.json`
   (ou aponte `GOOGLE_CREDENTIALS_FILE` para ele):
   - **Service account** (recomendado para servidor): *IAM > Contas de serviço > Criar chave JSON*.
     Depois compartilhe a agenda da clínica com o e-mail da service account, com a permissão
     **"Fazer alterações nos eventos"**.
   - **OAuth "App para computador"**: *APIs e serviços > Credenciais > Criar ID do cliente OAuth*.
     Na primeira execução o navegador abre para você autorizar; o token fica em `token.json`.
4. No `.env`: `CALENDARIO_BACKEND=google`.

O escopo pedido é só `calendar.events` (ler e criar eventos).

## Configurando o WhatsApp (Cloud API da Meta)

1. Em [developers.facebook.com](https://developers.facebook.com/apps), crie um app do tipo
   **Empresa** e adicione o produto **WhatsApp**.
2. Em *WhatsApp > Configuração da API*, copie o **ID do número de telefone**
   (`WHATSAPP_PHONE_NUMBER_ID`) e gere um token de acesso (`WHATSAPP_ACCESS_TOKEN`).
   O token temporário expira em 24 h; para algo duradouro, crie um usuário do sistema no
   Business Manager com a permissão `whatsapp_business_messaging` e gere um token permanente.
3. Em *Configurações do app > Básico*, copie a **Chave secreta do app** (`WHATSAPP_APP_SECRET`).
   Ela valida a assinatura `X-Hub-Signature-256` de cada chamada do webhook.
4. Escolha um texto qualquer para `WHATSAPP_VERIFY_TOKEN`.
5. Suba a API e exponha-a com HTTPS (a Meta não aceita `localhost`), por exemplo:

   ```bash
   uv run python main.py
   ngrok http 8000
   ```

6. Em *WhatsApp > Configuração > Webhook*, informe a URL `https://<seu-ngrok>/webhook/whatsapp`
   e o mesmo `WHATSAPP_VERIFY_TOKEN`. Depois, em *Campos do webhook*, assine **messages**.
7. Com o número de teste da Meta, só números cadastrados em *Para* (até 5) recebem respostas.

Como o atendimento funciona no WhatsApp:

- O webhook responde 200 na hora e o agente roda em background. A Meta reenvia o evento se a
  resposta demorar, e mensagens repetidas (mesmo id) são descartadas.
- As mensagens de um mesmo número são atendidas em ordem, uma de cada vez.
- Cada número tem sua conversa. Depois de `WHATSAPP_SESSAO_MINUTOS` sem mensagens (padrão
  120), a conversa recomeça do zero. Isso também limita o tamanho do histórico enviado ao LLM.
- O agente recebe o número do WhatsApp e o nome do perfil e pergunta se pode usar esse número
  no agendamento, em vez de pedir o telefone.
- Áudio, imagem e outros tipos recebem um aviso de que, por enquanto, só texto é entendido.
- A mensagem é marcada como lida e o paciente vê "digitando..." enquanto o agente responde.
- Respostas longas são divididas no limite de 4096 caracteres; `**negrito**` vira `*negrito*`.
- A Meta só permite mensagem livre até 24 h depois da última mensagem do paciente. Como o
  agente só responde, isso não é problema; mandar lembretes por conta própria exigiria templates
  aprovados.

Sem as variáveis `WHATSAPP_*`, a API sobe normalmente, com o canal desativado (o webhook
responde 503).

## Como rodar

Chat no terminal:

```bash
uv run python chat_cli.py
```

API (http://localhost:8000, docs em `/docs`):

```bash
uv run python main.py
```

```bash
curl -X POST http://localhost:8000/conversar \
  -H "Content-Type: application/json" \
  -d '{"mensagem": "Quero marcar um cardiologista para quinta à tarde"}'
```

A resposta traz `conversa_id`; envie-o nas próximas mensagens para continuar a mesma conversa.

Erros seguem o formato `{"erro": "...", "tipo": "..."}` (400 validação, 404 não encontrado,
409 conflito, 502 falha do LLM/agenda, 503 quota do LLM esgotada, com `Retry-After`).

## Testes

```bash
uv run pytest
```

Os testes usam a agenda em memória, a API do Google Calendar e a Graph API da Meta mockadas
e um LLM roteirizado — não fazem chamadas de rede.

## Estrutura

```
api/                    FastAPI: /conversar, webhook do WhatsApp e tradução de erros em HTTP
src/agents/             grafo LangGraph, estado e tools
src/calendario/         agenda: Google Calendar e versão em memória
src/clinica/            dados fictícios da clínica e dos médicos
src/llm/                chat model do Google e política de retry
src/prompts/            prompt do agente (com data atual e calendário dos próximos dias)
src/services/           regras de agenda, orquestração da conversa e atendimento pelo WhatsApp
src/whatsapp/           cliente da Graph API e leitura/assinatura do webhook
chat_cli.py             chat no terminal
main.py                 sobe a API
```
