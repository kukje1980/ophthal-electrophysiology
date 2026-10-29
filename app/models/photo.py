"""Clinical photo ORM model - one ophthalmic image (fundus, OCT, ...) of a
patient. The image bytes live on disk (see app.crud.photo); this row holds
the metadata and the random storage key the files are named by."""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base

# Imaging modality key -> display label.
MODALITIES = {
    "fundus": "안저 (Color fundus)",
    "redfree": "Red-free",
    "faf": "자가형광 (FAF)",
    "fag": "형광안저조영 (FAG)",
    "icga": "ICGA",
    "oct": "OCT",
    "octa": "OCT-A",
    "anterior": "전안부 (Anterior)",
    "topography": "각막지형도",
    "vf": "시야 (Visual field)",
    "other": "기타",
}

EYES = ("OD", "OS", "OU")


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(
        Integer, ForeignKey("patients.id"), nullable=False, index=True
    )

    eye = Column(String(2), nullable=True)        # OD / OS / OU
    modality = Column(String(16), nullable=True)  # key of MODALITIES
    taken_at = Column(DateTime, nullable=True)    # acquisition time
    title = Column(String(128), nullable=True)
    note = Column(String(512), nullable=True)

    original_name = Column(String(256), nullable=True)
    content_type = Column(String(32), nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    # Random file stem under PHOTO_DIR (never contains patient data).
    storage_key = Column(String(64), unique=True, nullable=False)
    # Set on an edited copy saved from the viewer: the photo it came from.
    source_id = Column(Integer, nullable=True)

    uploaded_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="photos")

    @property
    def patient_name(self):
        return self.patient.name if self.patient else None

    @property
    def patient_mrn(self):
        return self.patient.mrn if self.patient else None

    @property
    def modality_label(self):
        return MODALITIES.get(self.modality, self.modality)
