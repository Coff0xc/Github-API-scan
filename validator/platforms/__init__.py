"""Platform checks bound onto AsyncValidator as validate_* methods."""

from validator.platforms.anthropic import validate_anthropic
from validator.platforms.aws import validate_aws_access_key, validate_aws_bedrock
from validator.platforms.azure import validate_azure
from validator.platforms.gemini import validate_gemini
from validator.platforms.http_get import GET_VALIDATORS
from validator.platforms.openai import validate_openai

PLATFORM_METHODS = {
    "validate_openai": validate_openai,
    "validate_gemini": validate_gemini,
    "validate_anthropic": validate_anthropic,
    "validate_azure": validate_azure,
    "validate_aws_bedrock": validate_aws_bedrock,
    "validate_aws_access_key": validate_aws_access_key,
}
PLATFORM_METHODS.update(GET_VALIDATORS)


def bind_platform_methods(cls) -> None:
    for name, fn in PLATFORM_METHODS.items():
        setattr(cls, name, fn)
