## The types defined here are used generally throughout the project and are not related to any specific module.

from typing import Annotated
from pydantic import Field, StrictStr

AlphaNumStr = Annotated[StrictStr, Field(pattern=r"^[a-zA-Z0-9_-]+$")]

# create a type that is alphanum but accepts - and _
AlphaNumDashStr = Annotated[StrictStr, Field(
    pattern=r"^[a-zA-Z0-9_-]+$",
    description="Account alias should only contain letters, numbers, hyphens (-), or underscores (_)"
)]
