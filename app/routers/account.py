"""Self-service account API: password change and two-factor authentication."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.crud import user as crud
from app.database import get_db
from app.schemas.user import PasswordChange, TotpDisable, TotpEnable
from app.security import decrypt_phi, require_login, totp, verify_password

router = APIRouter(prefix="/api/account", tags=["account"])


@router.post("/password")
def change_password(data: PasswordChange, request: Request,
                    db: Session = Depends(get_db),
                    user=Depends(require_login)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "현재 비밀번호가 올바르지 않습니다.")
    crud.set_password(db, user, data.new_password)
    crud.audit(db, user=user, action="password.change", request=request)
    return {"status": "ok"}


@router.post("/2fa/init")
def init_2fa(request: Request, db: Session = Depends(get_db),
             user=Depends(require_login)):
    """Generate (but do not yet enable) a TOTP secret; return its QR / URI."""
    secret = totp.generate_secret()
    crud.set_totp(db, user, secret, enabled=False)
    uri = totp.provisioning_uri(secret, account=user.username)
    return {"secret": secret, "uri": uri, "qr_svg": totp.qr_svg(uri)}


@router.post("/2fa/enable")
def enable_2fa(data: TotpEnable, request: Request, db: Session = Depends(get_db),
               user=Depends(require_login)):
    secret = decrypt_phi(user.totp_secret)
    if not secret:
        raise HTTPException(400, "먼저 2단계 인증 설정을 시작하세요.")
    if not totp.verify(secret, data.code):
        raise HTTPException(400, "인증 코드가 올바르지 않습니다.")
    crud.set_totp(db, user, secret, enabled=True)
    crud.audit(db, user=user, action="2fa.enable", request=request)
    return {"status": "enabled"}


@router.post("/2fa/disable")
def disable_2fa(data: TotpDisable, request: Request,
                db: Session = Depends(get_db), user=Depends(require_login)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "현재 비밀번호가 올바르지 않습니다.")
    crud.set_totp(db, user, None, enabled=False)
    crud.audit(db, user=user, action="2fa.disable", request=request)
    return {"status": "disabled"}
