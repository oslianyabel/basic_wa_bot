from enum import Enum


class ModelType(Enum):
    GPT_4_1 = "gpt-4.1"
    GPT_4_1_mini = "gpt-4.1-mini"
    GPT_4_1_nano = "gpt-4.1-nano"
    GPT_5 = "gpt-5"
    GPT_5_mini = "gpt-5-mini"
    GPT_5_nano = "gpt-5-nano"

    @classmethod
    def has_value(cls, value: str) -> bool:
        return value in cls._value2member_map_

    @classmethod
    def list_values(cls) -> list[str]:
        return [member.value for member in cls]


class MessageType(Enum):
    SYSTEM = "system"
    DEVELOPER = "developer"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION_CALL = "function_call"
    CUSTOM_TOOL_CALL = "custom_tool_call"
    FUNCTION_CALL_OUTPUT = "function_call_output"

    @classmethod
    def has_value(cls, value: str) -> bool:
        return value in cls._value2member_map_

    @classmethod
    def list_values(cls) -> list[str]:
        return [member.value for member in cls]


class EffortType(Enum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def has_value(cls, value: str) -> bool:
        return value in cls._value2member_map_

    @classmethod
    def list_values(cls) -> list[str]:
        return [member.value for member in cls]


class VerbosityType(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def has_value(cls, value: str) -> bool:
        return value in cls._value2member_map_

    @classmethod
    def list_values(cls) -> list[str]:
        return [member.value for member in cls]


if __name__ == "__main__":
    print(ModelType.list_values())