"""Patient ORM model.

Modelled on the registration record kept by ophthalmology EMRs: demographics,
contact, insurance and referral, systemic and ocular history, and a baseline
ocular examination (VA / refraction / IOP / lens / pupil) per eye — the state
documentation that ISCEV electrophysiology reports also depend on.
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)

    # -- demographics -----------------------------------------------------
    mrn = Column(String(32), unique=True, index=True, nullable=False)  # chart no
    name = Column(String(128), nullable=False)
    name_en = Column(String(128), nullable=True)
    national_id = Column(String(32), nullable=True)  # 주민등록번호 (mask/encrypt in prod)
    birth_date = Column(Date, nullable=True)
    sex = Column(String(1), nullable=True)  # M / F / O

    # -- contact ----------------------------------------------------------
    phone = Column(String(32), nullable=True)
    email = Column(String(128), nullable=True)
    address = Column(String(256), nullable=True)
    guardian_name = Column(String(64), nullable=True)
    guardian_relation = Column(String(32), nullable=True)
    guardian_phone = Column(String(32), nullable=True)

    # -- registration / insurance / referral -----------------------------
    insurance_type = Column(String(32), nullable=True)  # 건강보험/의료급여/자보/산재/일반
    insurance_no = Column(String(64), nullable=True)
    referring_doctor = Column(String(64), nullable=True)
    referral_clinic = Column(String(128), nullable=True)
    chief_complaint = Column(String(256), nullable=True)

    # -- systemic / general history ---------------------------------------
    diabetes = Column(Boolean, nullable=True)
    diabetes_years = Column(Float, nullable=True)
    hypertension = Column(Boolean, nullable=True)
    smoking = Column(String(16), nullable=True)  # 비흡연/과거흡연/현재흡연
    systemic_history = Column(String(256), nullable=True)
    medications = Column(String(256), nullable=True)
    allergies = Column(String(256), nullable=True)
    family_ocular_history = Column(String(256), nullable=True)

    # -- ocular history (per eye) -----------------------------------------
    ocular_history_od = Column(String(256), nullable=True)
    ocular_history_os = Column(String(256), nullable=True)

    # -- baseline ocular examination (per eye) ----------------------------
    va_od = Column(String(16), nullable=True)  # best-corrected visual acuity
    va_os = Column(String(16), nullable=True)
    refraction_od = Column(String(64), nullable=True)  # e.g. -2.00 -0.75 x180
    refraction_os = Column(String(64), nullable=True)
    iop_od = Column(Float, nullable=True)  # mmHg
    iop_os = Column(Float, nullable=True)
    lens_status_od = Column(String(16), nullable=True)  # phakic/pseudophakic/aphakic
    lens_status_os = Column(String(16), nullable=True)
    pupil_od = Column(String(32), nullable=True)  # e.g. 8mm (dilated)
    pupil_os = Column(String(32), nullable=True)

    note = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    exams = relationship(
        "Exam", back_populates="patient", cascade="all, delete-orphan"
    )

    @property
    def age(self):
        """Age in whole years from birth_date, or None."""
        if not self.birth_date:
            return None
        today = date.today()
        return today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )
