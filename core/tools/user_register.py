import json
from pathlib import Path


async def user_register(
    email: str, name: str = None, phone: str = None, telegram_id: str = None
) -> str:
    try:
        users_file = Path(__file__).parent.parent / "users.json"

        if users_file.exists():
            with open(users_file, "r", encoding="utf-8") as f:
                users = json.load(f)
        else:
            users = []

        for user in users:
            if user.get("email") == email:
                return f"El usuario con email {email} ya está registrado"

        new_user = {
            "email": email,
            "phone": phone,
            "telegram_id": telegram_id,
            "name": name,
        }

        users.append(new_user)

        with open(users_file, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=4, ensure_ascii=False)

        return f"Usuario {email} registrado exitosamente"

    except Exception as e:
        return f"Error al registrar usuario: {str(e)}"
