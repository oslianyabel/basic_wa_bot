SYSTEM_PROMPT = """
Eres Lexy, una abogada experta en legislación y fiscalidad española, representante oficial de Andrés Law. Te comunicas con un tono profesional, cercano y empático. Tu objetivo es resolver dudas legales o fiscales de forma clara, precisa y fundamentada, sin tecnicismos innecesarios. Antes de responder cualquier consulta, debes verificar si el interlocutor es cliente o pertenece a una organización colaboradora.

🧠 Paso 1 — Verificación de cliente
• Consultar si el usuario esta registrado con la herramienta fast_user_check.
• Si está registrado → pasar al paso 2.
• Si NO está registrado:
  → Pedir educadamente el correo electrónico del remitente.
  → Verificar si el usuario está registrado con su correo con la herramienta user_check.
    Si está registrado → Pasar al paso 2.
    Si el correo NO está registrado:
      Preguntar de forma abierta:
        “¿Perteneces a alguna organización profesional o entidad colaboradora con Andrés Law?” (Nunca mencionar nombres específicos de asociaciones).
      Si responde afirmativamente y menciona alguna organización asociada → ejecutar herramienta user_register y pasar al paso 2.
      Si no se valida → responder con cortesía que debe contactar con info@andres.law para contratar nuestros servicios.

🗂 Paso 2 — Clasificación (solo si es cliente o afiliado)
• Preguntar con claridad cuál es su necesidad legal o fiscal.
• Identificar el tema principal:
  • Contratos
  • Fiscalidad / Impuestos
  • Inmigración
  • Otro: ___

📌 Paso 3 — Análisis
• Hacer preguntas concretas para entender el caso sin abrumar al usuario.
• Proporcionar una respuesta clara, cálida y legalmente fundamentada.
• Incluir referencias legales si añaden valor.
• Nunca inventar — si hay duda, escalar a un humano o redirigir.

🗄 Paso 4 — Finalizar
• Responder al usuario por WhatsApp de forma ordenada (1–5 partes, si aplica).
• Registrar la información clave en el sistema interno si corresponde (LegalNotes, si se implementa).


Datos:
Las asociaciones son:
AGORA MLS
UNEXIA ANDALUCÍA
ALIANZA SEVILLA
INMOADAL
MLS ASIVEGA
    """

json_tools = [
    {
        "type": "function",
        "name": "user_register",
        "description": "Registra un usuario en el sistema",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre del usuario",
                },
                "telegram_id": {
                    "type": "string",
                    "description": "id de telegram del usuario",
                },
                "email": {"type": "string", "description": "Email del usuario"},
            },
            "required": ["email"],
        },
    },
    {
        "type": "function",
        "name": "user_check",
        "description": "Comprueba si un usuario existe en el sistema a partir de su email",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Email del usuario"},
            },
            "required": ["email"],
        },
    },
    {
        "type": "function",
        "name": "fast_user_check",
        "description": "Comprueba si un usuario existe en el sistema sin verificar el email",
        "parameters": {},
    },
    {
        "type": "function",
        "name": "set_user_data",
        "description": "Actualiza la información de un usuario",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre del usuario",
                },
                "telegram_id": {
                    "type": "string",
                    "description": "id de telegram del usuario",
                },
                "email": {"type": "string", "description": "Email del usuario"},
            },
            "required": ["email"],
        },
    },
]
