from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# O pydantic-settings lê o .env só para o objeto Settings. Bibliotecas que leem
# direto de os.environ (ex.: o tracing do LangSmith, via LANGSMITH_TRACING e
# LANGSMITH_API_KEY) precisam que as variáveis sejam exportadas para o processo.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemma-4-26b-a4b-it"

    fuso_horario: str = "America/Sao_Paulo"

    # Agenda: google | memoria
    calendario_backend: str = "google"
    google_calendar_id: str = "primary"
    google_credentials_file: str = "credentials.json"
    google_token_file: str = "token.json"

    # WhatsApp Cloud API (Meta)
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""  # combinado com a Meta na configuração do webhook
    whatsapp_app_secret: str = ""  # valida a assinatura X-Hub-Signature-256
    whatsapp_api_version: str = "v23.0"
    # sem mensagem por esse tempo, a próxima começa uma conversa nova (histórico limpo)
    whatsapp_sessao_minutos: int = 120

    @property
    def whatsapp_configurado(self) -> bool:
        return all((
            self.whatsapp_access_token, self.whatsapp_phone_number_id,
            self.whatsapp_verify_token, self.whatsapp_app_secret,
        ))

    @property
    def fuso(self) -> ZoneInfo:
        return ZoneInfo(self.fuso_horario)


settings = Settings()
