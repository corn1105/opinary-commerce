from typing import Literal, Optional

from pydantic import BaseModel, Field

Locale = Literal["de", "en"]
BadgeLiteral = Literal["TOP RATED", "MOST POPULAR", "BEST VALUE", "EDITOR'S PICK", "NEW RELEASE"]


class AdminAuthRequest(BaseModel):
    password: str


class PollOptionInput(BaseModel):
    label: str
    id: Optional[str] = None  # present on edit, absent on create


class PollCreateRequest(BaseModel):
    question: str
    options: list[PollOptionInput] = Field(min_length=2, max_length=4)
    context_notes: Optional[str] = None
    publisher_name: Optional[str] = None
    publisher_logo: Optional[str] = None


class PollUpdateRequest(BaseModel):
    question: Optional[str] = None
    options: Optional[list[PollOptionInput]] = None
    context_notes: Optional[str] = None
    publisher_name: Optional[str] = None
    publisher_logo: Optional[str] = None
    status: Optional[Literal["active", "archived"]] = None


class VoteRequest(BaseModel):
    option_id: str


class RegenerateRecsRequest(BaseModel):
    locale: Locale


class EditBridgeRequest(BaseModel):
    locale: Locale
    bridge: str


class RecProduct(BaseModel):
    title: str
    description: str
    query: str
    badge: BadgeLiteral
    price: Optional[str] = None  # primary merchant (Amazon) price
    alt_price: Optional[str] = None  # secondary merchant (Best Buy) comparison price
    image_url: Optional[str] = None  # optional product image
    amazon_asin: Optional[str] = None  # direct Amazon product ID; if set, CTA links /dp/<asin>


class RecPayload(BaseModel):
    bridge: str
    products: list[RecProduct] = Field(min_length=2, max_length=4)
