"""Typed API request schemas and validation, independent of the FastAPI router.

Public compatibility imports remain available from gridraft.app.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .economics import number
from .model_policy import MODEL_LIMIT_CEILING, MAX_MESSAGES, MAX_CHOICES
from .request_policy import validate_extensions


class StrictBody(BaseModel):
    model_config=ConfigDict(extra='forbid', allow_inf_nan=False)
class ChallengeInput(StrictBody):
    wallet: str=Field(min_length=32,max_length=44)
class VerifyInput(StrictBody):
    id: str=Field(min_length=1,max_length=100)
    signature: str=Field(min_length=1,max_length=100)
class KeyInput(StrictBody):
    name: str=Field(min_length=1,max_length=60)
    limit_usd: str=Field(default='5',max_length=20)

    @field_validator('name')
    @classmethod
    def valid_name(cls, value):
        value=value.strip().strip('\u200b\u200c\u200d\ufeff')
        if not value or not value.isprintable():
            raise ValueError('Use a non-empty printable name')
        return value
class Message(StrictBody):
    role: Literal['developer','system','user','assistant','tool','function']
    content: str | list[dict] | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = Field(default=None,max_length=200)
    name: str | None = Field(default=None,max_length=128)
    function_call: dict | None = None
    reasoning_content: str | None = None

    @model_validator(mode='after')
    def validate_message(self):
        if self.role in ('developer','system','user') and self.content is None:
            raise ValueError('Message content is required')
        if self.role=='tool' and not self.tool_call_id:
            raise ValueError('tool_call_id is required for tool messages')
        if self.role=='function' and not self.name:
            raise ValueError('name is required for function messages')
        if self.role=='assistant' and self.content is None and not self.tool_calls and not self.function_call:
            raise ValueError('Assistant message needs content or a tool/function call')
        return self

class ChatInput(StrictBody):
    model: str=Field(min_length=1,max_length=150)
    messages: list[Message]=Field(min_length=1,max_length=MAX_MESSAGES)
    max_tokens: int | None=Field(default=None,ge=1,le=MODEL_LIMIT_CEILING,strict=True)
    max_completion_tokens: int | None=Field(default=None,ge=1,le=MODEL_LIMIT_CEILING,strict=True)
    stream: bool=Field(default=False,strict=True)
    stream_options: dict | None=None
    temperature: float=Field(default=0.7,ge=0,le=2)
    top_p: float | None=Field(default=None,gt=0,le=1)
    top_k: int | None=None
    min_p: float | None=Field(default=None,ge=0,le=1)
    frequency_penalty: float | None=Field(default=None,ge=-2,le=2)
    presence_penalty: float | None=Field(default=None,ge=-2,le=2)
    repetition_penalty: float | None=Field(default=None,gt=0,le=2)
    logit_bias: dict[str,float] | None=None
    logprobs: bool | None=None
    top_logprobs: int | None=Field(default=None,ge=0,le=20,strict=True)
    structured_outputs: dict | None=None
    service_tier: str | None=Field(default=None,max_length=100)
    store: bool | None=None
    safety_identifier: str | None=Field(default=None,max_length=512)
    prompt_cache_key: str | None=Field(default=None,max_length=512)
    cache_key: str | None=Field(default=None,max_length=512)
    enable_thinking: bool | None=None
    thinking_config: dict | None=None
    think: bool | None=None
    min_tokens: int | None=Field(default=None,ge=0,le=MODEL_LIMIT_CEILING,strict=True)
    bad_words: list[str] | None=Field(default=None,max_length=64)
    stop_token_ids: list[int] | None=Field(default=None,max_length=64)
    skip_special_tokens: bool | None=None
    detokenize: bool | None=None
    chat_template_kwargs: dict | None=None
    n: int=Field(default=1,ge=1,le=MAX_CHOICES,strict=True)
    stop: str | list[str] | None=None
    seed: int | None=Field(default=None,ge=0)
    tools: list[dict] | None=Field(default=None,max_length=128)
    tool_choice: str | dict | None=None
    parallel_tool_calls: bool | None=None
    response_format: dict | None=None
    user: str | None=Field(default=None,max_length=512)
    metadata: dict | None=None
    reasoning: dict | None=None
    reasoning_effort: str | None=None

    @field_validator('stop')
    @classmethod
    def validate_stop(cls,value):
        if value is None:return value
        values=[value] if isinstance(value,str) else value
        if len(values)>16 or any(not isinstance(x,str) or len(x.encode())>256 for x in values):
            raise ValueError('stop supports at most 16 strings of 256 bytes each')
        return value

    @field_validator('top_k')
    @classmethod
    def validate_top_k(cls,value):
        if value is not None and value!=-1 and value<1:raise ValueError('top_k must be -1 or >= 1')
        return value

    @field_validator('bad_words')
    @classmethod
    def validate_bad_words(cls,value):
        if value is not None and any(not isinstance(x,str) or len(x.encode())>128 for x in value):
            raise ValueError('bad_words supports at most 64 strings of 128 bytes each')
        return value

    @field_validator('stop_token_ids')
    @classmethod
    def validate_stop_token_ids(cls,value):
        if value is not None and any(type(x) is not int or x<0 for x in value):raise ValueError('stop_token_ids must contain non-negative integers')
        return value

    @field_validator('logit_bias')
    @classmethod
    def validate_logit_bias(cls,value):
        if value is not None:
            if len(value)>1024:raise ValueError('logit_bias supports at most 1024 entries')
            for k,v in value.items():
                if not isinstance(k,str) or not isinstance(v,(int,float)) or isinstance(v,bool) or not -100<=v<=100:
                    raise ValueError('Invalid logit_bias entry')
        return value

    @model_validator(mode='after')
    def normalize_output_aliases(self):
        validate_extensions(self)
        if self.max_tokens is not None and self.max_completion_tokens is not None and self.max_tokens!=self.max_completion_tokens:
            raise ValueError('max_tokens and max_completion_tokens must match when both are provided')
        return self


class AdminConfigInput(StrictBody):
    wallet_rpm: int=Field(ge=1,le=10000)
    wallet_concurrency: int=Field(ge=1,le=100)
    global_rpm: int=Field(ge=1,le=100000)
    global_concurrency: int=Field(ge=1,le=10000)
    holder_daily_tokens: int=Field(ge=1,le=10**9)
    global_daily_tokens: int=Field(ge=1,le=10**9)
    default_output_tokens: int=Field(ge=1,le=MODEL_LIMIT_CEILING)
    max_output_tokens: int=Field(ge=1,le=MODEL_LIMIT_CEILING)
    retail_input_nusd_per_token: int=Field(ge=1,le=10**6)
    retail_output_nusd_per_token: int=Field(ge=1,le=10**6)
    ngonka_per_token_budget: int | None=Field(default=None,ge=10,le=1000)
    maintenance_mode: bool=False
    disabled_models: list[str]=Field(default_factory=list,max_length=100)
    gnk_usd: str | None=None

    @model_validator(mode='after')
    def validate_config(self):
        if self.default_output_tokens>self.max_output_tokens:raise ValueError('Default output cannot exceed max output')
        if self.global_daily_tokens<self.holder_daily_tokens:raise ValueError('Global allowance cannot be smaller than per-wallet allowance')
        if self.global_concurrency<self.wallet_concurrency:raise ValueError('Global concurrency cannot be smaller than wallet concurrency')
        if self.gnk_usd is not None:number(self.gnk_usd,positive=True,maximum='1000000')
        if len(set(self.disabled_models))!=len(self.disabled_models):raise ValueError('Duplicate disabled model')
        return self

class AdminUserInput(StrictBody):
    disabled: bool=False
    daily_tokens_override: int | None=Field(default=None,ge=1,le=10**9)
    note: str=Field(default='',max_length=500)

class AdminFundInput(StrictBody):
    gnk: str=Field(min_length=1,max_length=40)
    reference: str=Field(min_length=1,max_length=200)
    confirm_funded: bool=False

class AdminBusinessInput(StrictBody):
    category: Literal['creator_fee','api_revenue','subscription_revenue','hosting','rpc','support','refund','tax','developer_payout','gnk_purchase','other']
    amount_usd: str=Field(min_length=1,max_length=40)
    reference: str=Field(min_length=1,max_length=200)
    note: str=Field(default='',max_length=500)



class SwapQuoteInput(StrictBody):
    asset: Literal['SOL','PROJECT']='SOL'
    amount: str=Field(min_length=1,max_length=40)
    slippage_bps: int=Field(default=50,ge=1,le=100,strict=True)
