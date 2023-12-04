"""Anthropic LLMs."""
import os
import re
import warnings
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    cast,
)

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import LLM, BaseLanguageModel
from langchain_core.outputs import GenerationChunk
from langchain_core.prompt_values import PromptValue
from langchain_core.pydantic_v1 import Field, SecretStr, root_validator
from langchain_core.utils import (
    build_extra_kwargs,
    check_package_version,
    convert_to_secret_str,
    get_pydantic_field_names,
)


class _AnthropicCommon(BaseLanguageModel):
    client: Any = None  #: :meta private:
    async_client: Any = None  #: :meta private:
    model: str = Field(default="claude-2", alias="model_name")
    """Model name to use."""

    max_tokens_to_sample: int = Field(default=256, alias="max_tokens")
    """Denotes the number of tokens to predict per generation."""

    temperature: Optional[float] = None
    """A non-negative float that tunes the degree of randomness in generation."""

    top_k: Optional[int] = None
    """Number of most likely tokens to consider at each step."""

    top_p: Optional[float] = None
    """Total probability mass of tokens to consider at each step."""

    default_request_timeout: Optional[float] = Field(default=None, alias="timeout")
    """Timeout for requests to Anthropic Completion API. Default is 600 seconds."""

    anthropic_api_url: Optional[str] = Field(default=None, alias="base_url")
    """Base API url."""

    anthropic_api_key: Optional[SecretStr] = Field(default=None, alias="api_key")
    """Automatically inferred from env var `ANTHROPIC_API_KEY` if not provided."""

    model_kwargs: Dict[str, Any] = Field(default_factory=dict)
    """Additional keyword arguments to pass in when invoking model."""

    streaming: bool = False
    HUMAN_PROMPT: Optional[str] = None
    AI_PROMPT: Optional[str] = None
    count_tokens: Optional[Callable[[str], int]] = None

    @root_validator(pre=True)
    def build_extra(cls, values: Dict) -> Dict:
        extra = values.get("model_kwargs", {})
        all_required_field_names = get_pydantic_field_names(cls)
        values["model_kwargs"] = build_extra_kwargs(
            extra, values, all_required_field_names
        )
        return values

    @root_validator()
    def validate_environment(cls, values: Dict) -> Dict:
        """Validate that api key and python package exists in environment."""
        if values["anthropic_api_key"] is None:
            if os.getenv("ANTHROPIC_API_KEY") is None:
                raise ValueError(
                    "API key must be provided in as argument anthropic_api_key or set"
                    " as environment variable ANTHROPIC_API_KEY."
                )
            values["anthropic_api_key"] = os.getenv("ANTHROPIC_API_KEY")

        values["anthropic_api_key"] = convert_to_secret_str(values["anthropic_api_key"])

        # Get custom api url from environment.
        if values["anthropic_api_url"] is None:
            values["anthropic_api_url"] = os.getenv(
                "ANTHROPIC_API_URL", default="https://api.anthropic.com"
            )

        try:
            import anthropic

            check_package_version("anthropic", gte_version="0.3")

            base_url = values["anthropic_api_url"]
            api_key = cast(SecretStr, values["anthropic_api_key"]).get_secret_value()
            timeout = values["default_request_timeout"]
            values["client"] = anthropic.Anthropic(
                base_url=base_url,
                api_key=api_key,
                timeout=timeout,
            )
            values["async_client"] = anthropic.AsyncAnthropic(
                base_url=base_url,
                api_key=api_key,
                timeout=timeout,
            )
            values["HUMAN_PROMPT"] = (
                values["HUMAN_PROMPT"]
                if values["HUMAN_PROMPT"] is not None
                else anthropic.HUMAN_PROMPT
            )
            values["AI_PROMPT"] = (
                values["AI_PROMPT"]
                if values["AI_PROMPT"] is not None
                else anthropic.AI_PROMPT
            )

        except ImportError:
            raise ImportError(
                "Could not import anthropic python package. "
                "Please it install it with `pip install -U anthropic`."
            )
        return values

    @property
    def _default_params(self) -> Mapping[str, Any]:
        """Get the default parameters for calling Anthropic API."""
        d = {
            "max_tokens_to_sample": self.max_tokens_to_sample,
            "model": self.model,
        }
        if self.temperature is not None:
            d["temperature"] = self.temperature
        if self.top_k is not None:
            d["top_k"] = self.top_k
        if self.top_p is not None:
            d["top_p"] = self.top_p
        return {**d, **self.model_kwargs}

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """Get the identifying parameters."""
        return self._default_params

    def _get_anthropic_stop(self, stop: Optional[List[str]] = None) -> List[str]:
        if not self.HUMAN_PROMPT or not self.AI_PROMPT:
            raise NameError("Please ensure the anthropic package is loaded")

        if stop is None:
            stop = []

        # Never want model to invent new turns of Human / Assistant dialog.
        stop.extend([self.HUMAN_PROMPT])

        return stop


class Anthropic(LLM, _AnthropicCommon):
    """Anthropic large language models.

    To use, you should have the ``anthropic`` python package installed, and the
    environment variable ``ANTHROPIC_API_KEY`` set with your API key, or pass
    it as a named parameter to the constructor.

    Example:
        .. code-block:: python

            from langchain_anthropic import Anthropic

            model = Anthropic(
                model="claude-2",
                anthropic_api_key="<my-api-key>",
                max_tokens_to_sample=1024,
            )

            # Simplest invocation, automatically wrapped with HUMAN_PROMPT
            # and AI_PROMPT.
            response = model.invoke("What are the biggest risks facing humanity?")

            # Or if you want to use the chat mode, build a few-shot-prompt, or
            # put words in the Assistant's mouth, use HUMAN_PROMPT and AI_PROMPT:
            raw_prompt = "What are the biggest risks facing humanity?"
            prompt = f"{anthropic.HUMAN_PROMPT} {prompt}{anthropic.AI_PROMPT}"
            response = model.invoke(prompt)
    """

    class Config:
        """Configuration for this pydantic object."""

        allow_population_by_field_name = True
        arbitrary_types_allowed = True

    @root_validator()
    def raise_warning(cls, values: Dict) -> Dict:
        """Raise warning that this class is deprecated."""
        warnings.warn(
            "This Anthropic LLM is deprecated. "
            "Please use `from langchain_anthropic import ChatAnthropic` instead"
        )
        return values

    @property
    def _llm_type(self) -> str:
        """Return type of llm."""
        return "anthropic-llm"

    def _wrap_prompt(self, prompt: str) -> str:
        if not self.HUMAN_PROMPT or not self.AI_PROMPT:
            raise NameError("Please ensure the anthropic package is loaded")

        if prompt.startswith(self.HUMAN_PROMPT):
            return prompt  # Already wrapped.

        # Guard against common errors in specifying wrong number of newlines.
        corrected_prompt, n_subs = re.subn(r"^\n*Human:", self.HUMAN_PROMPT, prompt)
        if n_subs == 1:
            return corrected_prompt

        # As a last resort, wrap the prompt ourselves to emulate instruct-style.
        return f"{self.HUMAN_PROMPT} {prompt}{self.AI_PROMPT} Sure, here you go:\n"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        r"""Call out to Anthropic's completion endpoint.

        Args:
            prompt: The prompt to pass into the model.
            stop: Optional list of stop words to use when generating.

        Returns:
            The string generated by the model.

        Example:
            .. code-block:: python

                prompt = "What are the biggest risks facing humanity?"
                prompt = f"\n\nHuman: {prompt}\n\nAssistant:"
                response = model(prompt)

        """
        if self.streaming:
            completion = ""
            for chunk in self._stream(
                prompt=prompt, stop=stop, run_manager=run_manager, **kwargs
            ):
                completion += chunk.text
            return completion

        stop = self._get_anthropic_stop(stop)
        params = {**self._default_params, **kwargs}
        response = self.client.completions.create(
            prompt=self._wrap_prompt(prompt),
            stop_sequences=stop,
            **params,
        )
        return response.completion

    def convert_prompt(self, prompt: PromptValue) -> str:
        return self._wrap_prompt(prompt.to_string())

    async def _acall(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Call out to Anthropic's completion endpoint asynchronously."""
        if self.streaming:
            completion = ""
            async for chunk in self._astream(
                prompt=prompt, stop=stop, run_manager=run_manager, **kwargs
            ):
                completion += chunk.text
            return completion

        stop = self._get_anthropic_stop(stop)
        params = {**self._default_params, **kwargs}

        response = await self.async_client.completions.create(
            prompt=self._wrap_prompt(prompt),
            stop_sequences=stop,
            **params,
        )
        return response.completion

    def _stream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[GenerationChunk]:
        r"""Call Anthropic completion_stream and return the resulting generator.

        Args:
            prompt: The prompt to pass into the model.
            stop: Optional list of stop words to use when generating.
        Returns:
            A generator representing the stream of tokens from Anthropic.
        Example:
            .. code-block:: python

                prompt = "Write a poem about a stream."
                prompt = f"\n\nHuman: {prompt}\n\nAssistant:"
                generator = anthropic.stream(prompt)
                for token in generator:
                    yield token
        """
        stop = self._get_anthropic_stop(stop)
        params = {**self._default_params, **kwargs}

        for token in self.client.completions.create(
            prompt=self._wrap_prompt(prompt), stop_sequences=stop, stream=True, **params
        ):
            chunk = GenerationChunk(text=token.completion)
            yield chunk
            if run_manager:
                run_manager.on_llm_new_token(chunk.text, chunk=chunk)

    async def _astream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[GenerationChunk]:
        r"""Call Anthropic completion_stream and return the resulting generator.

        Args:
            prompt: The prompt to pass into the model.
            stop: Optional list of stop words to use when generating.
        Returns:
            A generator representing the stream of tokens from Anthropic.
        Example:
            .. code-block:: python
                prompt = "Write a poem about a stream."
                prompt = f"\n\nHuman: {prompt}\n\nAssistant:"
                generator = anthropic.stream(prompt)
                for token in generator:
                    yield token
        """
        stop = self._get_anthropic_stop(stop)
        params = {**self._default_params, **kwargs}

        async for token in await self.async_client.completions.create(
            prompt=self._wrap_prompt(prompt),
            stop_sequences=stop,
            stream=True,
            **params,
        ):
            chunk = GenerationChunk(text=token.completion)
            yield chunk
            if run_manager:
                await run_manager.on_llm_new_token(chunk.text, chunk=chunk)

    def get_num_tokens(self, text: str) -> int:
        """Calculate number of tokens."""
        if self.count_tokens is not None:
            return self.count_tokens(text)
        else:
            return self.client.count_tokens(text)
