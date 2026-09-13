from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=120)
    phone: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyLoginRequest(BaseModel):
    challenge_id: str
    code: str = Field(min_length=6, max_length=6)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str = ""


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    phone: str
    role: str
    initials: str

    model_config = {"from_attributes": True}


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class LoginChallengeOut(BaseModel):
    requires_2fa: bool = True
    challenge_id: str
    email_hint: str
    message: str = "Enter the 6-digit code we emailed you."
    debug_code: str | None = None


class MessageOut(BaseModel):
    message: str
    debug_token: str | None = None
