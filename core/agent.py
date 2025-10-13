import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI

from config import config
from core.enumerations import EffortType, MessageType, ModelType, VerbosityType
from core.prompt import SYSTEM_PROMPT

load_dotenv(".env")


class SetMessagesError(Exception):
    pass


class ChatMemory:
    def __init__(self, prompt=SYSTEM_PROMPT):
        self.__ai_output: dict[str, Any] = {}
        self.__messages: dict[str, list[dict]] = {}
        self.__tool_msgs: dict[str, list[dict]] = {}
        self.init_msg = {
            "role": MessageType.DEVELOPER.value,
            "content": prompt,
        }
        self.__last_time: float

    def get_ai_output(self, user_id: int):
        if user_id not in self.__ai_output:
            return []

        return self.__ai_output[user_id].output

    def get_tool_msgs(self, user_id: int):
        if user_id not in self.__tool_msgs:
            return []
        return self.__tool_msgs[user_id]

    def get_messages(self, user_id: int, with_prompt: bool = True):
        if user_id not in self.__messages:
            print(f"{user_id} not found in memory")
            self.init_chat(user_id)

        if with_prompt:
            return self.__messages[user_id]
        else:
            return self.__messages[user_id][1:]

    def get_last_time(self):
        return self.__last_time

    def _set_ai_output(self, ai_output, user_id: int):
        self.__ai_output[user_id] = ai_output

        if user_id not in self.__messages:
            print(f"{user_id} not found in memory")
            return False

        if user_id not in self.__tool_msgs:
            self.__tool_msgs[user_id] = ai_output.output.copy()
        else:
            self.__tool_msgs[user_id] += ai_output.output.copy()

        self.__messages[user_id] += ai_output.output.copy()

    def _clean_tool_msgs(self, user_id: int):
        if user_id not in self.__tool_msgs:
            print(f"{user_id} not have tool messages")

        self.__tool_msgs[user_id] = []

    def has_chat(self, user_id: int) -> bool:
        return user_id in self.__messages and len(self.__messages[user_id]) > 0

    def delete_chat(self, user_id: int) -> None:
        if user_id in self.__messages:
            del self.__messages[user_id]
        if user_id in self.__tool_msgs:
            del self.__tool_msgs[user_id]
        if user_id in self.__ai_output:
            del self.__ai_output[user_id]

    def init_chat(self, user_id: int):
        self.set_messages([self.init_msg], user_id)
        print(f"New chat for {user_id}")

    def add_msg(self, message: str, role: str, user_id: int):
        if user_id not in self.__messages:
            self.init_chat(user_id)

        if MessageType.has_value(role):
            self.__messages[user_id].append(
                {
                    "role": role,
                    "content": message,
                }
            )
            print(f"New message from {role} added to chat of {user_id}")
            return True

        print(f"Invalid role {role}, must be one of: {MessageType.list_values()}")
        return False

    def set_messages(self, messages: list[dict[str, str]], user_id: int):
        if not isinstance(messages, list):
            raise SetMessagesError(f"messages must be a list, not {type(messages)}")

        for id, msg in enumerate(messages):
            if not MessageType.has_value(msg["role"]):
                raise SetMessagesError(
                    f"Invalid role {msg['role']} in the {id + 1} message, must be one of: {MessageType.list_values()}"
                )

        self.__messages[user_id] = messages

    def _get_ai_msg(self, user_id: int):
        ai_output = self.get_ai_output(user_id)

        for item in ai_output:  # type: ignore
            try:
                if item.type == "message":
                    ans = item.content[0].text  # type: ignore
                    return ans

            except Exception as exc:
                print(f"Error retrieving AI message: {exc}")
                print(item)

        return "No Answer"

    def _purge_tool_msgs(self, user_id: int):
        tool_msgs = self.get_tool_msgs(user_id)
        messages = self.get_messages(user_id)
        if tool_msgs:
            clean_messages = [m for m in messages if m not in tool_msgs]
            try:
                self.set_messages(clean_messages, user_id)
            except SetMessagesError as exc:
                print(f"Error purging tool messages: {exc}")
            finally:
                self._clean_tool_msgs(user_id)

    def _set_tool_output(self, call_id, function_out, user_id: int):
        # Store as ephemeral tool output; do not persist in history
        if user_id not in self.__messages:
            print(f"{user_id} not found in memory")
            return False

        msg = {
            "type": "function_call_output",
            "call_id": call_id,
            "output": str(function_out),
        }

        if user_id not in self.__tool_msgs:
            self.__tool_msgs[user_id] = [msg]
        else:
            self.__tool_msgs[user_id].append(msg)

        self.__messages[user_id].append(msg)


class AIClient:
    def __init__(
        self,
        api_key: str,
    ):
        self.__client = OpenAI(api_key=api_key)
        self.__async_client = AsyncOpenAI(api_key=api_key)

    async def _async_gen_ai_output(self, params: dict):
        ai_output = await self.__async_client.responses.create(**params)
        return ai_output

    def _gen_ai_output(self, params: dict):
        return self.__client.responses.create(**params)


class ToolRunner:
    def __init__(
        self,
        error_msg="Ha ocurrido un error inesperado",
    ):
        self.ERROR_MSG = error_msg

    def _run_functions(
        self,
        functions_called,
        user_id: int,
        chat_memory: ChatMemory,
        rag_functions,
    ) -> None:
        print(f"{len(functions_called)} functions need to be called!")

        with ThreadPoolExecutor() as executor:
            futures = []
            for tool in functions_called:
                function_name = tool.name
                function_args = tool.arguments
                function_to_call = rag_functions[function_name]

                print(f"function_name: {function_name}")
                print(
                    f"function_args: {function_args[:100]}{'...' if len(function_args) > 100 else ''}"
                )
                function_args = json.loads(function_args)
                function_args["phone"] = user_id

                futures.append(executor.submit(function_to_call, **function_args))

            self.run_futures(futures, functions_called, user_id, chat_memory)

    def _run_custom_tools(
        self, custom_tools_called, user_id: int, chat_memory: ChatMemory, rag_functions
    ) -> None:
        print(f"{len(custom_tools_called)} custom tools need to be called!")

        with ThreadPoolExecutor() as executor:
            futures = []
            for tool in custom_tools_called:
                print(f"Custom tool name: {tool.name}")
                print(f"Custom tool input: {tool.input}")

                function_args = {"tool_input": tool.input}
                function_to_call = rag_functions[tool.name]

                futures.append(executor.submit(function_to_call, **function_args))

            self.run_futures(futures, custom_tools_called, user_id, chat_memory)

    def run_futures(self, futures, tools_called, user_id: int, chat_memory: ChatMemory):
        for future, tool in zip(futures, tools_called):
            try:
                function_out = future.result()
                print(f"{tool.name}: {function_out[:100]}")  # type: ignore
            except Exception as exc:
                print(f"{tool.name}: {exc}")
                function_out = self.ERROR_MSG

            chat_memory._set_tool_output(tool.call_id, function_out, user_id)

    async def _async_run_functions(
        self, functions_called, user_id: int, chat_memory: ChatMemory, rag_functions
    ) -> None:
        print(f"{len(functions_called)} function need to be called!")
        tasks = []
        for tool in functions_called:
            function_name = tool.name
            function_args = tool.arguments
            function_to_call = rag_functions[function_name]  # type: ignore

            print(f"function_name: {function_name}")
            print(
                f"function_args: {function_args[:100]}{'...' if len(function_args) > 100 else ''}"
            )
            function_args = json.loads(function_args)
            function_args["phone"] = user_id

            tasks.append(function_to_call(**function_args))

        await self.run_coroutines(functions_called, tasks, user_id, chat_memory)

    async def _async_run_custom_tools(  # type: ignore
        self, custom_tools_called, user_id: int, chat_memory: ChatMemory, rag_functions
    ) -> None:
        print(f"{len(custom_tools_called)} custom tools need to be called!")

        tasks = []
        for tool in custom_tools_called:
            print(f"function_name: {tool.name}")
            print(f"Input tool: {tool.input}")

            function_to_call = rag_functions[tool.name]  # type: ignore
            function_args = {"tool_input": tool.input}

            tasks.append(function_to_call(**function_args))

        await self.run_coroutines(custom_tools_called, tasks, user_id, chat_memory)

    async def run_coroutines(
        self, tools_called, tasks, user_id: int, chat_memory: ChatMemory
    ):
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for tool, function_out in zip(tools_called, results):
            if isinstance(function_out, Exception):
                print(f"{tool.name}: {function_out}")
                function_out = self.ERROR_MSG  # type: ignore
            else:
                print(f"{tool.name}: {function_out[:100]}")  # type: ignore

            chat_memory._set_tool_output(tool.call_id, function_out, user_id)


class Agent:
    def __init__(
        self,
        name="Console Agent",
        model=ModelType.GPT_5.value,
        prompt=SYSTEM_PROMPT,
        api_key=config.OPENAI_API_KEY,
    ):
        self.name = name
        self.model = model
        self.chat_memory = ChatMemory(prompt=prompt)
        self._ai_client = AIClient(api_key)
        self._tool_runner = ToolRunner()

    def run_callback(self, tool_execution_callback, user_id):
        reasoning_items = [
            item
            for item in self.chat_memory.get_ai_output(user_id)
            if item.type == "reasoning"
        ]

        if reasoning_items:
            print(f"{len(reasoning_items)} reasoning items have founded")
            reasoning_content = None
            for reasoning_item in reasoning_items:
                if hasattr(reasoning_item, "content") and reasoning_item.content:
                    reasoning_content = reasoning_item.content
                    break
                elif hasattr(reasoning_item, "summary") and reasoning_item.summary:
                    reasoning_content = reasoning_item.summary
                    break

            if reasoning_content:
                tool_execution_callback(reasoning_content)

        print("No reasoning content to show")

    def process_msg(
        self,
        message: str,
        user_id: int,
        rag_functions: dict = {},
        rag_prompt: list[dict] = [],
        tool_execution_callback=None,
    ) -> str | None:
        print(f"Running {self.model} with {len(rag_prompt)} tools")

        self.chat_memory.add_msg(message, MessageType.USER.value, user_id)

        while True:
            params = {
                "model": self.model,  # type: ignore
                "input": self.chat_memory.get_messages(user_id),  # type: ignore
            }
            if rag_prompt:
                params["tools"] = rag_prompt
            if self.model == ModelType.GPT_5.value:  # type: ignore
                params["text"] = {"verbosity": VerbosityType.LOW.value}
                params["reasoning"] = {"effort": EffortType.LOW.value}

            ai_output = self._ai_client._gen_ai_output(params)
            self.chat_memory._set_ai_output(ai_output, user_id)

            functions_called = [
                item
                for item in ai_output.output  # type: ignore
                if item.type == MessageType.FUNCTION_CALL.value
            ]

            custom_tools_called = [
                item
                for item in ai_output.output  # type: ignore
                if item.type == MessageType.CUSTOM_TOOL_CALL.value
            ]

            if not functions_called and not custom_tools_called:
                break

            if tool_execution_callback:
                self.run_callback(tool_execution_callback, user_id)

            if functions_called:
                self._tool_runner._run_functions(
                    functions_called,
                    user_id,
                    self.chat_memory,
                    rag_functions,
                )

            if custom_tools_called:
                self._tool_runner._run_custom_tools(
                    custom_tools_called,
                    user_id,
                    self.chat_memory,
                    rag_functions,
                )

        self.chat_memory._purge_tool_msgs(user_id)
        ai_msg = self.chat_memory._get_ai_msg(user_id)
        print(f"{self.name}: {ai_msg}")
        self.chat_memory.add_msg(ai_msg, MessageType.ASSISTANT.value, user_id)
        # print(self.chat_memory.get_messages(user_id, with_prompt=False))
        return ai_msg

    async def async_process_msg(
        self,
        message: str,
        user_id: int,
        rag_functions: dict = {},
        rag_prompt: list[dict] = [],
        tool_execution_callback=None,
    ) -> str | None:
        print(f"Running {self.model} with {len(rag_prompt)} tools")

        self.chat_memory.add_msg(message, MessageType.USER.value, user_id)

        while True:
            params = {
                "model": self.model,  # type: ignore
                "input": self.chat_memory.get_messages(user_id),  # type: ignore
            }
            if rag_prompt:
                params["tools"] = rag_prompt
            if self.model == ModelType.GPT_5.value:  # type: ignore
                params["text"] = {"verbosity": VerbosityType.LOW.value}
                params["reasoning"] = {"effort": EffortType.LOW.value}

            ai_output = await self._ai_client._async_gen_ai_output(params)
            self.chat_memory._set_ai_output(ai_output, user_id)

            functions_called = [
                item
                for item in ai_output.output  # type: ignore
                if item.type == MessageType.FUNCTION_CALL.value
            ]

            custom_tools_called = [
                item
                for item in ai_output.output  # type: ignore
                if item.type == MessageType.CUSTOM_TOOL_CALL.value
            ]

            if not functions_called and not custom_tools_called:
                break

            if tool_execution_callback:
                self.run_callback(tool_execution_callback, user_id)

            if functions_called:
                await self._tool_runner._async_run_functions(
                    functions_called,
                    user_id,
                    self.chat_memory,
                    rag_functions,
                )

            if custom_tools_called:
                await self._tool_runner._async_run_custom_tools(
                    custom_tools_called,
                    user_id,
                    self.chat_memory,
                    rag_functions,
                )

        self.chat_memory._purge_tool_msgs(user_id)
        ai_msg = self.chat_memory._get_ai_msg(user_id)
        print(f"{self.name}: {ai_msg}")
        self.chat_memory.add_msg(ai_msg, MessageType.ASSISTANT.value, user_id)
        return ai_msg


async def console_chat_main():
    """
    Flujo de chat principal con entrada de usuario por consola
    """
    print("🤖 Console Chat Bot")
    print("=" * 50)
    print("Comandos: /exit (salir), /reset (reiniciar), /help (ayuda)")
    print("=" * 50)

    bot = Agent("Test Agent")
    conversation_count = 0

    while True:
        try:
            user_input = input("\n👤 Usuario: ").strip()

            if not user_input:
                continue

            # Comandos especiales
            if user_input.lower() in ["/exit", "quit", ":q"]:
                print("👋 ¡Hasta luego!")
                break

            elif user_input.lower() == "/reset":
                bot.chat_memory.init_chat("console")
                bot.chat_memory.add_msg(
                    "Conversación reiniciada.", MessageType.DEVELOPER.value, "console"
                )
                conversation_count = 0
                print("🔄 Conversación reiniciada")
                continue

            elif user_input.lower() == "/help":
                help_text = """
📋 Comandos disponibles:
  /exit, quit, :q  - Salir del chat
  /reset           - Reiniciar conversación
  /help            - Mostrar esta ayuda
  
💡 Simplemente escribe tu mensaje para chatear con el bot
                """
                print(help_text)
                continue

            print("🤖 Procesando...")

            try:
                await bot.async_process_msg(user_input, user_id="console")
                conversation_count += 1

            except Exception as exc:
                print(f"❌ Error: {exc}")

        except (EOFError, KeyboardInterrupt):
            print("\n👋 Saliendo del chat...")
            break
        except Exception as exc:
            print(f"❌ Error inesperado: {exc}")


if __name__ == "__main__":
    asyncio.run(console_chat_main())
