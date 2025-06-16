## The types defined here are used generally throughout the project and are not related to any specific module.

from typing import Annotated
from pydantic import Field, StrictStr

AlphaNumStr = Annotated[StrictStr, Field(pattern=r"^[a-zA-Z0-9]+$")]