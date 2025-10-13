import json
from pathlib import Path


async def fast_user_check(phone: str) -> str:
    return await user_check(phone, "")


async def user_check(phone: str, email: str) -> str:
    try:
        users_file = Path(__file__).parent.parent / "users.json"

        if users_file.exists():
            with open(users_file, "r", encoding="utf-8") as f:
                users = json.load(f)
        else:
            users = []

        for user in users:
            if user.get("phone") == phone:
                return f"El usuario con el telefono {phone} ya está registrado"

            if email and user.get("email") == email:
                user["phone"] = phone

                with open(users_file, "w", encoding="utf-8") as f:
                    json.dump(users, f, indent=4, ensure_ascii=False)

                return f"El usuario con email {email} ya estaba registrado. Se le ha asignado su numero de telefono"

        return (
            f"El usuario con el telefono {phone} y el email {email} no está registrado"
        )

    except Exception as e:
        return f"Error buscando el usuario: {str(e)}"
